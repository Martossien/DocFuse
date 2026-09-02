"""Pages d'un PDF : erreur de comptage, genre de page et règle « texte poubelle ».

Partagé par l'extracteur (`docfuse.extractors.pdf`) et l'OCR (`docfuse.extractors.pdf_ocr`) ;
n'importe ni l'un ni l'autre.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from docfuse.constants import (
    PDF_OCR_GARBAGE_MARKERS,
    PDF_OCR_MIN_CHARS_PER_PAGE,
)

logger = logging.getLogger(__name__)


class PdfPageCountMismatchError(Exception):
    """Deux bibliothèques indépendantes ne comptent pas le même nombre de pages.

    **Pourquoi c'est grave (D-107).** Dans cet extracteur, l'indice de page
    est la *clé de jointure* entre deux bibliothèques : le texte et sa
    numérotation viennent de pdfminer (`_extract_pages_pdfminer`, énumération
    de `extract_pages()`), le rendu OCR vient de PDFium
    (`_ocr_pages`, `page = pdf[idx]`). `_apply_ocr` réécrit ensuite
    `new_pages[idx]`. Si les deux ne parcourent pas la même suite de pages,
    la page N reçoit le texte d'une autre page — et pour une page classée
    `OCR`, ce texte **écrase** le texte natif réel au lieu de s'y ajouter.
    Le contenu de la page perdue disparaît du corpus, celui d'une autre y
    figure deux fois, et le résultat sort en statut `ready` sans un mot.

    **Cause prouvée.** pdfminer déduplique son parcours de l'arbre `/Pages`
    avec un ensemble `visited` (`pdfminer/pdfpage.py`) : un objet page
    référencé deux fois dans `/Kids` — cas courant d'un PDF fusionné qui
    réutilise un objet — n'est vu qu'une fois par pdfminer, mais deux fois
    par pypdf et par PDFium. Reproduit sur un PDF de 4 pages dont pdfminer
    n'en voit que 3.

    **Choix retenu : refuser, plutôt qu'aligner.** L'autre option était
    d'aligner les deux sources sur une seule autorité : reconstruire la vraie
    suite de pages en appariant les identifiants d'objet PDF
    (`pypdf : page.indirect_reference.idnum` ↔ `pdfminer : PDFPage.pageid`),
    puis dupliquer le texte pdfminer pour chaque référence répétée. Ce qu'elle
    aurait coûté :

    * abandonner `pdfminer.high_level.extract_pages()` pour recopier sa
      boucle interne (`PDFPage.get_pages` + `PDFPageInterpreter` +
      `PDFPageAggregator`) — seul moyen d'accéder à l'identifiant d'objet de
      chaque page, `LTPage.pageid` n'étant qu'un compteur séquentiel ;
    * parier que pypdf et pdfminer numérotent les objets à l'identique, pour
      un gain limité au seul scénario « objet page dupliqué » ;
    * et **ne rien régler** pour les autres causes possibles de désaccord
      (arbre `/Pages` partiellement illisible, `/Count` menteur, page que
      pdfminer abandonne) : l'appariement échouerait, et il faudrait de toute
      façon ce refus en dernier recours.

    Le refus coûte, lui, le retrait du fichier du corpus : un document
    contenant des données personnelles pourrait ne pas être signalé du tout,
    faute d'être résumé. C'est assumé — le fichier apparaît en statut
    `ERROR` dans le rapport avec les deux comptes, donc à examiner à la main,
    là où un résumé faux se lit comme un résumé vrai et sert à décider une
    suppression.

    Attributes:
        expected_pages: Nombre de pages attendu (celui de pdfminer, qui
            numérote le texte).
        observed_pages: Nombre de pages vu par l'autre bibliothèque.
        observed_by: Nom de cette autre bibliothèque (`pypdf`, `PDFium`).
    """

    def __init__(self, expected_pages: int, observed_pages: int, observed_by: str) -> None:
        self.expected_pages = expected_pages
        self.observed_pages = observed_pages
        self.observed_by = observed_by
        super().__init__(
            f"pdfminer voit {expected_pages} page(s), {observed_by} en voit {observed_pages}"
        )


class PageKind(StrEnum):
    """Classification d'une page PDF pour décider si l'OCR est utile.

    Simplification assumée par rapport à une détection par couverture
    d'image (ratio surface image / surface page) : DocFuse ne dispose que
    d'un compte d'images par page (pdfminer), pas de leurs dimensions —
    même logique booléenne que `core/image_detector.py` (image_count > 0).
    """

    NATIVE = "native"
    OCR = "ocr"
    BLANK = "blank"
    MIXED = "mixed"


def _has_garbage_text(text: str) -> bool:
    """Détecte un texte natif « poubelle » (polices cassées, glyphes non mappés)."""
    return any(marker in text for marker in PDF_OCR_GARBAGE_MARKERS)


def _blank_if_garbage(kind: PageKind, text: str) -> str:
    """Texte de page à conserver quand l'OCR n'a rien donné (D-086, D-096).

    Une page classée `OCR` à cause de texte natif « poubelle » (glyphes non
    mappés — `(cid:...)`, `�`) ne doit pas garder ce bruit dans le corpus :
    c'est inutilisable, et une page sans contenu extractible est déjà
    signalée proprement par le marqueur `[[PAGE N: aucun texte extractible]]`.
    Une page `OCR` avec du texte réel mais trop court reste inchangée : ce
    texte, bien que sous le seuil, ne doit pas disparaître.
    """
    if kind is PageKind.OCR and _has_garbage_text(text):
        return ""
    return text


def classify_page(text: str, char_count: int, has_image: bool) -> PageKind:
    """Classe une page pour décider si l'OCR lui serait utile.

    Args:
        text: Texte natif de la page (avant dédup, peu importe ici).
        char_count: Caractères utiles déjà comptés (`chars_per_page[i]`).
        has_image: Au moins une image détectée sur cette page (pdfminer).

    Returns:
        `NATIVE` (texte natif suffisant, rien à faire), `BLANK` (page
        réellement vide — pas de texte fantôme), `OCR` (pas de texte natif
        utile, qu'il n'y en ait jamais eu ou qu'il soit illisible/poubelle),
        ou `MIXED` (texte natif utile + une image sur la page).

    Une page « poubelle » (glyphes non mappés) a du contenu visible même si
    rien n'est extractible : ce n'est jamais `BLANK`, seulement une page
    sans image (`char_count == 0` et pas de glyphes poubelle) l'est.
    """
    useful_chars = 0 if _has_garbage_text(text) else char_count
    if useful_chars == 0:
        if char_count == 0 and not has_image:
            return PageKind.BLANK
        return PageKind.OCR
    if useful_chars < PDF_OCR_MIN_CHARS_PER_PAGE:
        return PageKind.OCR
    return PageKind.MIXED if has_image else PageKind.NATIVE
