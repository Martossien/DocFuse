"""Extracteur PDF : .pdf.

CdC §8.3 — Texte de chaque page, dans l'ordre des pages.
Page vide → marqueur [[PAGE N: aucun texte extractible]].
CdC §9.4 — Détection images via XObject /Subtype /Image + LTImage/LTFigure.
CdC §14.3 — pdfminer.six (MIT) pour extraction + détection images ;
            pypdf (BSD) pour inventaire pages + détection encryption.

Inspiré de MarkItDown PdfConverter :
- extract_pages() pour traiter page-par-page (libération mémoire).
- extract_text() en fallback si le rendu est trop pauvre.

OCR (v1, PDF scannés) — voir `core/ocr/` : chaque page est classée
native/ocr/blank/mixed à partir du texte déjà extrait par pdfminer (pas de
seconde passe d'extraction). Seules les pages classées ocr/mixed sont
rastérisées (pypdfium2) puis passées à Tesseract, si disponible — sinon le
comportement est strictement identique à avant l'ajout de cette
fonctionnalité (voir `core/ocr/registry.py::resolve_ocr_engine`).
"""

from __future__ import annotations

import io
import logging
import math
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from enum import StrEnum
from pathlib import Path
from typing import Any

from docfuse.branding import OCR_VARIANT_NAME
from docfuse.constants import (
    OCR_DPI,
    OCR_LANG,
    OCR_MAX_CONCURRENCY,
    OCR_MAX_PAGES_PER_FILE,
    OCR_MAX_PIXELS_PER_PAGE,
    OCR_MIN_DPI,
    PDF_BOILERPLATE_MAX_LINE_LEN,
    PDF_BOILERPLATE_MIN_OCCURRENCES,
    PDF_BOILERPLATE_MIN_PAGES,
    PDF_BOILERPLATE_MIN_RATIO,
    PDF_OCR_GARBAGE_MARKERS,
    PDF_OCR_MIN_CHARS_PER_PAGE,
)
from docfuse.core.ocr.base import OcrEngine
from docfuse.core.ocr.registry import ocr_with_slot, resolve_ocr_engine
from docfuse.core.registry import register
from docfuse.extractors.base import (
    Extractor,
    error_result,
    error_result_message,
    file_type_for,
)
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)

# D-078 : PDFium (pypdfium2) n'est pas thread-safe entre PdfDocument
# distincts chargés depuis des threads différents — voir le docstring de
# `_ocr_pages`. Verrou global au niveau du processus (pas par fichier :
# c'est justement l'accès concurrent ENTRE fichiers différents qui corrompt
# le tas natif de PDFium).
_PDFIUM_LOCK = threading.Lock()


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


def _structural_page_count(path: Path) -> int | None:
    """Nombre de pages du PDF réel, vu par pypdf (D-107).

    pypdf sert ici d'**autorité structurelle** : il parcourt `/Kids` sans
    déduplication, comme PDFium (le moteur de rendu OCR) et comme n'importe
    quel lecteur PDF — c'est donc ce nombre-là que voit l'auditeur qui ouvre
    le fichier, et c'est celui que le rapport doit annoncer.

    Returns:
        Le nombre de pages, ou `None` si pypdf ne peut pas lire le fichier —
        auquel cas aucune vérification n'est possible à ce stade et c'est la
        garde de `_ocr_pages` (PDFium) qui reste seule en ligne.
    """
    try:
        from pypdf import PdfReader

        # D-098 : objet fichier et non chemin — pypdf recopierait sinon tout
        # le fichier en mémoire.
        with path.open("rb") as fh:
            reader = PdfReader(fh)
            if reader.is_encrypted:
                reader.decrypt("")
            return len(reader.pages)
    except Exception:
        logger.warning("Nombre de pages pypdf illisible pour %s", path, exc_info=True)
        return None


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


@register(".pdf")
class PdfExtractor(Extractor):
    """Extracteur PDF via pdfminer.six + pypdf, avec OCR optionnel des pages scannées."""

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            # 1. Vérifier l'encryption avec pypdf
            encrypted = _check_encrypted(path)
            if encrypted:
                return ExtractedFile(
                    path=path,
                    relative_path=relative_path,
                    extension=file_type_for(path),
                    file_type=file_type_for(path),
                    size_bytes=path.stat().st_size,
                    status=FileStatus.ERROR,
                    error_message=t("error.encrypted_pdf"),
                )

            # 2. Extraction texte page-par-page avec pdfminer
            pages_text, image_count, page_count, image_count_per_page = _extract_pages_pdfminer(
                path
            )

            # 2a. D-107 : l'indice de page est la clé de jointure entre le
            # texte (pdfminer) et le rendu OCR (PDFium). Si pypdf — qui compte
            # les pages comme PDFium et comme n'importe quel lecteur — n'est
            # pas d'accord avec pdfminer, cette clé est fausse : on refuse
            # plutôt que de risquer d'attribuer le texte d'une page à une
            # autre. Voir `PdfPageCountMismatchError` pour le raisonnement complet.
            structural_page_count = _structural_page_count(path)
            if structural_page_count is not None and structural_page_count != page_count:
                raise PdfPageCountMismatchError(page_count, structural_page_count, "pypdf")

            # 2b. Déduplication des en-têtes/pieds de page répétés sur chaque page.
            # Recalcule chars_per_page à partir du texte dédupliqué : la densité de
            # texte utile pour la détection de pauvreté (image_detector.py) doit
            # refléter le contenu réel, pas le bruit répété.
            pages_text, dedup_note = _dedupe_page_boilerplate(pages_text)
            chars_per_page = [len(p.strip()) for p in pages_text]

            extra_metadata: dict[str, str] = {}
            if dedup_note:
                extra_metadata["pdf_dedup"] = dedup_note

            # 2c. OCR des pages scannées (moteur optionnel, jamais bloquant).
            pages_text, ocr_note = _apply_ocr(
                path, pages_text, chars_per_page, image_count_per_page
            )
            if ocr_note:
                extra_metadata["ocr"] = ocr_note
            chars_per_page = [len(p.strip()) for p in pages_text]

            # 3. Construction du texte avec marqueurs de pages vides
            parts: list[str] = []
            for i, (text, char_count) in enumerate(
                zip(pages_text, chars_per_page, strict=False), 1
            ):
                if char_count == 0:
                    parts.append(f"[[PAGE {i}: aucun texte extractible]]")
                else:
                    parts.append(text)

            full_text = "\n\n".join(parts)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=file_type_for(path),
                file_type=file_type_for(path),
                size_bytes=path.stat().st_size,
                text=full_text,
                status=FileStatus.READY,
                image_count=image_count,
                page_count=page_count,
                chars_per_page=chars_per_page,
                extra_metadata=extra_metadata,
            )
        except PdfPageCountMismatchError as exc:
            # D-107 : refus explicite, jamais un résultat silencieusement faux.
            logger.error("Structure de pages incohérente dans %s : %s", path, exc)
            result = error_result_message(
                path,
                relative_path,
                t(
                    "error.pdf_page_count_mismatch",
                    pdfminer_pages=exc.expected_pages,
                    real_pages=exc.observed_pages,
                    library=exc.observed_by,
                ),
            )
            # Le rapport doit annoncer le nombre de pages du PDF réel, pas
            # celui de la vue tronquée de pdfminer.
            result.page_count = exc.observed_pages
            return result
        except Exception as exc:
            logger.exception("Erreur extraction PDF %s", path)
            return error_result(path, relative_path, exc)


def _check_encrypted(path: Path) -> bool:
    """Vérifie si le PDF est verrouillé par un VRAI mot de passe utilisateur.

    D-071 : `reader.is_encrypted` reste `True` même pour un PDF chiffré avec
    un mot de passe utilisateur VIDE — cas très courant (documents
    juridiques/financiers protégés en copie/impression, mais lisibles par
    n'importe quel lecteur). `is_encrypted` seul bloquait donc à tort des
    fichiers 100 % lisibles. `reader.decrypt("")` (et pdfminer, qui essaie
    déjà un mot de passe vide par défaut) permettent de faire la différence :
    on ne bloque que si le mot de passe vide échoue réellement.
    """
    try:
        from pypdf import PasswordType, PdfReader

        # D-098 : avec un chemin, pypdf recopie TOUT le fichier en mémoire
        # (`BytesIO(fh.read())`, vérifié dans pypdf 6.16) rien que pour lire
        # `/Encrypt` — un scan de 500 Mo × MAX_WORKERS fichiers en parallèle.
        # Avec un objet fichier, pypdf navigue par `seek`, sans copie.
        with path.open("rb") as fh:
            reader = PdfReader(fh)
            if not reader.is_encrypted:
                return False
            return reader.decrypt("") == PasswordType.NOT_DECRYPTED
    except Exception:
        # pypdf n'a pas su lire la structure : pdfminer tranchera — mais la cause
        # doit rester lisible dans le journal (un PDF corrompu se diagnostique ici).
        logger.debug("Contrôle de chiffrement pypdf impossible pour %s", path, exc_info=True)
        return False


def _extract_pages_pdfminer(path: Path) -> tuple[list[str], int, int, list[int]]:
    """Extrait le texte et les images page par page via pdfminer.six.

    ``LAParams(all_texts=True)`` : sans ce réglage, pdfminer ne regroupe pas
    en lignes/paragraphes le texte situé dans un Form XObject (``LTFigure``
    imbriqué — filigranes, tampons, contenu fusionné, courant avec des
    générateurs comme TCPDF). Ce texte reste alors de simples ``LTChar``
    épars, invisibles pour `isinstance(element, LTTextContainer)` — une page
    entière de texte réel peut ainsi être vue comme vide. Constaté
    concrètement en session (2026-08-29, D-068) : jusqu'à ~2500 caractères
    de texte natif silencieusement ignorés sur certaines pages.

    Returns:
        Tuple (textes par page, nombre d'images total, nombre de pages,
        nombre d'images par page). Les caractères par page sont recalculés
        par l'appelant après déduplication/OCR (D-099 : l'ancienne valeur
        renvoyée ici était écrasée sans jamais être lue).
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTFigure, LTImage, LTTextContainer

    pages_text: list[str] = []
    image_count_per_page: list[int] = []
    total_images = 0
    page_count = 0

    for page in extract_pages(str(path), laparams=LAParams(all_texts=True)):
        page_count += 1
        page_text_parts: list[str] = []
        page_images = 0

        for element in page:
            # Texte
            if isinstance(element, LTTextContainer):
                text = element.get_text()
                if text.strip():
                    page_text_parts.append(text.strip())

            # Images directes
            if isinstance(element, LTImage):
                page_images += 1

            # Figures (contiennent souvent des images ET/OU du texte imbriqué
            # via un Form XObject — voir le docstring de la fonction)
            if isinstance(element, LTFigure):
                figure_images, figure_text = _walk_figure(element)
                page_images += figure_images
                page_text_parts.extend(figure_text)

        total_images += page_images
        image_count_per_page.append(page_images)
        page_text = "\n".join(page_text_parts)
        pages_text.append(page_text)

        # Libération mémoire (inspiré de MarkItDown PdfConverter:566)
        # pdfminer gère la mémoire page-par-page avec extract_pages()

    return pages_text, total_images, page_count, image_count_per_page


def _dedupe_page_boilerplate(pages_text: list[str]) -> tuple[list[str], str | None]:
    """Retire les en-têtes/pieds de page répétés à l'identique sur plusieurs pages.

    Un en-tête/pied de page PDF est extrait par pdfminer comme la première ou
    la dernière ligne du texte de chaque page (les blocs de texte y sont
    physiquement positionnés). On ne regarde donc que ces deux positions par
    page — jamais le corps du texte — pour ne pas risquer de retirer un
    paragraphe légitimement répété.

    Une ligne candidate n'est retirée que si elle apparaît identique sur au
    moins ``PDF_BOILERPLATE_MIN_OCCURRENCES`` pages ET sur au moins
    ``PDF_BOILERPLATE_MIN_RATIO`` des pages du document — un simple "Page 1"
    répété deux fois dans un document de 40 pages ne déclenche rien.

    Toutes les occurrences sauf la première sont supprimées ; la première
    reste visible une fois dans le corpus (CdC §8 — sans perte silencieuse :
    le contenu répété disparaît du texte, mais son existence est signalée
    dans l'en-tête SOURCE via la note retournée).

    Returns:
        Tuple (pages de texte mises à jour, note descriptive ou None si rien
        n'a été dédupliqué).
    """
    page_count = len(pages_text)
    if page_count < PDF_BOILERPLATE_MIN_PAGES:
        return pages_text, None
    pages_lines = [p.split("\n") for p in pages_text]
    occurrences = _edge_line_occurrences(pages_lines)
    min_occurrences = max(
        PDF_BOILERPLATE_MIN_OCCURRENCES, round(PDF_BOILERPLATE_MIN_RATIO * page_count)
    )
    boilerplate = {line for line, count in occurrences.items() if count >= min_occurrences}
    if not boilerplate:
        return pages_text, None
    new_pages, chars_saved = _strip_repeated_edges(pages_lines, boilerplate)
    note = t(
        "pdf.dedup_note",
        count=len(boilerplate),
        occurrences=sum(occurrences[line] for line in boilerplate),
        chars=chars_saved,
    )
    return new_pages, note


def _edge_line_occurrences(pages_lines: list[list[str]]) -> dict[str, int]:
    """Nombre de pages où chaque première/dernière ligne (courte) apparaît."""
    occurrences: dict[str, int] = {}
    for lines in pages_lines:
        candidates = set()
        if lines and lines[0].strip():
            candidates.add(lines[0].strip())
        if lines and lines[-1].strip():
            candidates.add(lines[-1].strip())
        for candidate in candidates:
            if len(candidate) <= PDF_BOILERPLATE_MAX_LINE_LEN:
                occurrences[candidate] = occurrences.get(candidate, 0) + 1
    return occurrences


def _strip_repeated_edges(
    pages_lines: list[list[str]], boilerplate: set[str]
) -> tuple[list[str], int]:
    """Retire les occurrences suivantes de chaque ligne répétée (la première reste).

    Returns:
        (pages de texte, caractères retirés).
    """
    seen_once: set[str] = set()
    chars_saved = 0
    new_pages: list[str] = []
    for lines in pages_lines:
        kept_lines = []
        for j, line in enumerate(lines):
            stripped = line.strip()
            is_edge = j == 0 or j == len(lines) - 1
            if is_edge and stripped in boilerplate:
                if stripped in seen_once:
                    chars_saved += len(line)
                    continue
                seen_once.add(stripped)
            kept_lines.append(line)
        new_pages.append("\n".join(kept_lines))
    return new_pages, chars_saved


def _walk_figure(figure: Any) -> tuple[int, list[str]]:
    """Images et texte imbriqués dans un LTFigure, en un seul parcours
    récursif (D-099 : fusion de deux parcours symétriques, M-02 + D-068).

    Le texte n'est regroupé en `LTTextContainer` que grâce à
    `LAParams(all_texts=True)` — voir `_extract_pages_pdfminer`.
    """
    from pdfminer.layout import LTFigure, LTImage, LTTextContainer

    images = 0
    parts: list[str] = []
    for child in figure:
        if isinstance(child, LTImage):
            images += 1
        elif isinstance(child, LTTextContainer):
            text = child.get_text()
            if text.strip():
                parts.append(text.strip())
        elif isinstance(child, LTFigure):
            child_images, child_parts = _walk_figure(child)
            images += child_images
            parts.extend(child_parts)
    return images, parts


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


def _apply_ocr(
    path: Path,
    pages_text: list[str],
    chars_per_page: list[int],
    image_count_per_page: list[int],
) -> tuple[list[str], str | None]:
    """Classe chaque page et lance l'OCR sur celles qui en ont besoin.

    Ne modifie jamais une page classée `native` ou `blank`. Si aucun moteur
    OCR n'est disponible, le texte n'est pas modifié — seule une note de
    transparence est ajoutée si des pages semblaient scannées.

    Returns:
        Tuple (pages de texte éventuellement enrichies de texte OCR, note
        de transparence ou None si rien à signaler).
    """
    page_count = len(pages_text)
    if page_count == 0:
        return pages_text, None

    kinds = [
        classify_page(text, chars, images > 0)
        for text, chars, images in zip(
            pages_text, chars_per_page, image_count_per_page, strict=True
        )
    ]

    ocr_indices = [i for i, k in enumerate(kinds) if k in (PageKind.OCR, PageKind.MIXED)]
    if not ocr_indices:
        return pages_text, None

    engine = resolve_ocr_engine()
    if engine is None:
        cleaned_pages = [
            _blank_if_garbage(kinds[i], page) if i in ocr_indices else page
            for i, page in enumerate(pages_text)
        ]
        return cleaned_pages, t(
            "ocr.unavailable_note", pages=len(ocr_indices), variant=OCR_VARIANT_NAME
        )

    # D-107 : `page_count` est le nombre de pages que pdfminer a numérotées ;
    # `_ocr_pages` refuse de rendre quoi que ce soit si PDFium n'en compte pas
    # autant (`PdfPageCountMismatchError`, laissée remonter jusqu'à `extract`).
    ocr_results = _ocr_pages(path, ocr_indices, OCR_LANG, engine, page_count)

    new_pages = list(pages_text)
    pages_ocr = pages_mixed = pages_failed = 0
    for idx in ocr_indices:
        text, ok = ocr_results.get(idx, ("", False))
        kind = kinds[idx]
        if not ok or not text.strip():
            pages_failed += 1
            # D-096 : l'OCR a échoué (raster impossible, page hors plafond,
            # timeout, résultat vide) — la règle D-086 s'applique exactement
            # comme sans moteur : ne pas laisser le texte poubelle.
            new_pages[idx] = _blank_if_garbage(kind, new_pages[idx])
            continue
        marker = f"[[PAGE {idx + 1} — texte OCR (tesseract, {OCR_LANG})]]\n{text.strip()}"
        if kind is PageKind.MIXED and new_pages[idx].strip():
            new_pages[idx] = f"{new_pages[idx]}\n\n{marker}"
            pages_mixed += 1
        else:
            new_pages[idx] = marker
            pages_ocr += 1

    note = t(
        "ocr.applied_note",
        pages_ocr=pages_ocr,
        pages_mixed=pages_mixed,
        pages_failed=pages_failed,
        pages_total=page_count,
        lang=OCR_LANG,
    )
    return new_pages, note


def _ocr_render_scale(width_pt: float, height_pt: float) -> float | None:
    """Facteur d'échelle de rastérisation d'une page, ou `None` si elle doit
    être ignorée (D-105).

    Fonction pure, testable sans moteur OCR ni PDF : c'est elle qui remplace
    l'ancien `continue` qui perdait purement et simplement toute page dont la
    surface dépassait `OCR_MAX_PIXELS_PER_PAGE` à `OCR_DPI` — souvent
    justement les documents qui comptent (plan A0, scan haute résolution,
    facture numérisée à 600 dpi).

    Portée réelle du sauvetage (D-106 — la docstring précédente et celle de
    `constants.OCR_MIN_DPI` étaient inexactes). Avec `OCR_DPI = 200` et
    `OCR_MIN_DPI = 100`, la réduction autorisée est d'un facteur 2 en
    résolution, donc **4 en surface** : une page est rendue tant que son aire
    ne dépasse pas `OCR_MAX_PIXELS_PER_PAGE / (OCR_MIN_DPI/72)²`, soit
    8 294 400 pt². Chiffres mesurés (voir
    `tests/test_extractors/test_pdf.py::TestOcrRenderScaleBounds`) :

    * A4 (595 × 842 pt) → 200 dpi, plein tarif ;
    * ARCH E1 (2160 × 3024 pt) → 112,7 dpi ;
    * ANSI E (2448 × 3168 pt) → 103,4 dpi ;
    * **A0 (2384 × 3370 pt) → 101,6 dpi** — et non « 120 dpi » comme
      l'affirmait `constants.py` ;
    * ARCH E (2592 × 3456 pt) → 96,2 dpi, **sous le plancher : ignorée** ;
    * B0 (2835 × 4008 pt) → ignorée.

    Les très grands formats restent donc hors de portée. Le découpage de la
    page en bandes (`crop=` de `pypdfium2`) permettrait de garder 200 dpi,
    mais **n'a pas été retenu** (D-106) : une bande horizontale coupe les
    lignes de texte en deux, et Tesseract rend alors du bruit des deux côtés
    de la coupure — une corruption silencieuse du contenu, strictement pire
    que la résolution réduite déjà en place. Le rattraper demanderait un
    recouvrement entre bandes puis une déduplication heuristique des lignes,
    qui perd ou duplique du texte selon le réglage. Le sauvetage reste donc
    une réduction d'échelle honnête, et la page hors de portée est
    journalisée puis traitée par la règle D-086 (`_blank_if_garbage`), jamais
    silencieusement remplie de texte poubelle.

    Args:
        width_pt: Largeur de la page en points PDF (1/72 pouce).
        height_pt: Hauteur de la page en points PDF.

    Returns:
        L'échelle à passer à `page.render(scale=...)` : `OCR_DPI / 72` si la
        page tient déjà sous le plafond, sinon l'échelle réduite qui l'y fait
        tenir exactement. `None` si cette échelle réduite tombe sous
        `OCR_MIN_DPI` (page inexploitable même OCRisée) ou si les dimensions
        sont dégénérées.
    """
    # D-106 : garde explicite sur chaque dimension, et non sur leur produit.
    # `(-595, -842)` donnait une aire **positive** et passait à l'échelle
    # nominale (PDFium recevant des dimensions négatives), et `NaN` traversait
    # toutes les comparaisons (`NaN <= 0` est faux, `NaN < x` aussi) pour
    # ressortir en `NaN` vers `page.render(scale=NaN)`. `not (x > 0)` rejette
    # à la fois zéro, le négatif et `NaN`.
    if not (width_pt > 0 and height_pt > 0):
        return None
    base_scale = OCR_DPI / 72
    area_pt = width_pt * height_pt
    if area_pt * base_scale * base_scale <= OCR_MAX_PIXELS_PER_PAGE:
        return base_scale
    reduced = math.sqrt(OCR_MAX_PIXELS_PER_PAGE / area_pt)
    if reduced < OCR_MIN_DPI / 72:
        return None
    return reduced


def _render_page_image(path: Path, idx: int, expected_page_count: int) -> Any:
    """Rastérise UNE page et rend une image PIL détachée de PDFium (D-108).

    Le verrou `_PDFIUM_LOCK` (D-078) est pris et relâché ici, autour du seul
    code qui appelle réellement PDFium. À la sortie, **plus aucun objet
    PDFium n'est vivant** : le document est rouvert et refermé à chaque page
    plutôt que maintenu ouvert entre deux prises du verrou. Garder un
    `PdfDocument` vivant pendant qu'un autre thread charge le sien est
    précisément la situation que D-078 décrit comme corruptrice ;
    l'invariant « aucun état PDFium ne survit au verrou » est donc conservé
    à l'identique. Coût mesuré de la réouverture : **5,2 ms par page** (PDF
    scanné de 200 pages A4, 200 dpi), contre ~77 ms de rendu, et à comparer
    aux ~400 ms d'encodage PNG que ce découpage sort du verrou.

    L'appelant encode ensuite le PNG hors du verrou. `to_pil()` peut partager
    le tampon natif du bitmap (documenté par pypdfium2 : « for RGBA, RGBX and
    L bitmaps, PIL is supposed to share memory with the original buffer ») :
    `.copy()` détache l'image, sans quoi sortir du verrou reviendrait à lire
    de la mémoire PDFium pendant qu'un autre thread s'en sert. Coût mesuré :
    **5,0 ms par page** — le format rendu par défaut ici est `BGR`, que PIL
    recopie déjà, mais l'appel ne dépend alors d'aucun réglage de rendu.

    Args:
        path: Chemin du PDF.
        idx: Index 0-indexé de la page, dans la numérotation de l'appelant.
        expected_page_count: Nombre de pages attendu — vérifié contre PDFium
            (D-107) avant tout `pdf[idx]`.

    Returns:
        Une image `PIL.Image.Image` indépendante, ou `None` si la page n'a
        pas pu être rendue (PDF illisible, page hors plafond mémoire,
        rastérisation en échec). Ces cas sont journalisés, jamais silencieux.

    Raises:
        PdfPageCountMismatchError: PDFium ne compte pas `expected_page_count`
            pages (D-107).
    """
    import pypdfium2 as pdfium

    with _PDFIUM_LOCK:
        pdf = None
        bitmap = None
        try:
            pdf = pdfium.PdfDocument(str(path))
            # D-107 : garde avant tout `pdf[idx]`.
            pdfium_page_count = len(pdf)
            if pdfium_page_count != expected_page_count:
                raise PdfPageCountMismatchError(expected_page_count, pdfium_page_count, "PDFium")

            page = pdf[idx]
            # D-096 : le plafond de pixels est vérifié AVANT le rendu — sinon
            # la bitmap complète est déjà allouée (une page A0 à 200 dpi
            # ≈ 250 Mo RGBA, une page hostile plusieurs Go) : un OOM est un
            # SIGKILL, pas une exception rattrapable, et tue tout le processus
            # (même classe que D-078).
            # D-105 : le calcul se fait toujours avant allocation, mais une
            # page hors plafond n'est plus perdue — elle est rendue à
            # l'échelle réduite qui la fait tenir.
            width, height = page.get_size()
            page_scale = _ocr_render_scale(width, height)
            if page_scale is None:
                logger.warning("Page %d de %s trop grande pour l'OCR, ignorée", idx + 1, path)
                return None
            if page_scale < OCR_DPI / 72:
                logger.info(
                    "Page %d de %s rendue en résolution réduite (%d dpi au lieu de %d)"
                    " pour tenir sous le plafond mémoire OCR",
                    idx + 1,
                    path,
                    round(page_scale * 72),
                    OCR_DPI,
                )
            bitmap = page.render(scale=page_scale)
            return bitmap.to_pil().copy()
        except PdfPageCountMismatchError:
            raise
        except Exception:
            logger.warning("Rastérisation échouée page %d de %s", idx + 1, path, exc_info=True)
            return None
        finally:
            # `bitmap.close()` et `pdf.close()` sont des appels PDFium : ils
            # doivent rester à l'intérieur du verrou.
            if bitmap is not None:
                bitmap.close()
            if pdf is not None:
                pdf.close()


def _ocr_pages(
    path: Path,
    page_indices: list[int],
    lang: str,
    engine: OcrEngine,
    expected_page_count: int,
) -> dict[int, tuple[str, bool]]:
    """Rastérise puis reconnaît une sélection de pages (0-indexées).

    D-107 — **les indices reçus viennent de pdfminer, le rendu vient de
    PDFium** : `page_indices` numérote les pages telles que
    `_extract_pages_pdfminer` les a énumérées, `pdf[idx]` les prend telles
    que PDFium les voit. Ces deux suites ne coïncident pas toujours (pdfminer
    déduplique l'arbre `/Pages`, PDFium non). `expected_page_count` est le
    nombre de pages de l'appelant : s'il ne correspond pas à celui de PDFium,
    aucune page n'est rendue et `PdfPageCountMismatchError` est levée — laisser
    passer reviendrait à coller le texte reconnu d'une page sur une autre,
    en écrasant son vrai texte. C'est la deuxième garde, au point exact où
    les deux bibliothèques se croisent ; la première (pypdf) est dans
    `PdfExtractor.extract`.

    Tout accès à PDFium est **protégé par `_PDFIUM_LOCK`** (D-078) : PDFium
    n'est pas thread-safe entre `PdfDocument` distincts chargés depuis des
    threads différents — vérifié en conditions réelles, un dossier avec
    plusieurs PDF nécessitant l'OCR traités en parallèle
    (`ThreadPoolExecutor` de l'orchestrateur) produit une corruption de tas
    native (`malloc(): unsorted double linked list corrupted`) puis un
    SIGSEGV qui tue tout le processus — pas seulement le fichier en cours.
    Un verrou global sérialise l'accès à PDFium pour tout le processus ; la
    reconnaissance Tesseract, elle, reste parallélisée (chaque appel est déjà
    un process OS isolé via `subprocess`, donc thread-safe côté appelant,
    hors du verrou).

    D-108 — **étendue du verrou et pic mémoire.** Auparavant une seule prise
    du verrou couvrait tout le document, et l'encodage PNG — qui n'appelle
    jamais PDFium — se faisait dedans ; les PNG de toutes les pages étaient
    de plus accumulés jusqu'à la fin du rendu, contrairement à ce que cette
    docstring affirmait (« jamais tout le PDF en mémoire à la fois »). Mesuré
    sur un PDF scanné de 200 pages A4 à 200 dpi : **RSS 16 Mo → 2 023 Mo**,
    verrou détenu **95,7 s sur 96,2 s (99 %)**, dont ~83 % en encodage PNG.
    Avec `MAX_WORKERS` fichiers en parallèle, le débit OCR de tout le
    processus était plafonné par ce verrou.

    Désormais : une page à la fois (`_render_page_image`, verrou pris et
    relâché par page), encodage PNG **hors** du verrou, et soumission à
    l'OCR au fil de l'eau — bornée par `in_flight`, pour que la file des PNG
    ne remplace pas le dictionnaire qu'elle a supprimé.

    Args:
        path: Chemin du PDF.
        page_indices: Indices 0-indexés des pages à OCRiser, dans la
            numérotation de `_extract_pages_pdfminer`.
        lang: Langues Tesseract.
        engine: Moteur OCR résolu.
        expected_page_count: Nombre total de pages dans cette même
            numérotation, pour vérifier que PDFium parcourt bien le même
            document (D-107).

    Returns:
        Dict {index page: (texte reconnu, succès)}. Une page en échec (raster
        impossible, page trop grande, timeout) a `succès=False` et un texte
        vide.

    Raises:
        PdfPageCountMismatchError: PDFium ne compte pas `expected_page_count`
            pages — les indices ne désignent pas les mêmes pages des deux
            côtés. Seule exception que cette fonction laisse remonter.
    """
    results: dict[int, tuple[str, bool]] = {}
    capped = page_indices[:OCR_MAX_PAGES_PER_FILE]
    for skipped in page_indices[OCR_MAX_PAGES_PER_FILE:]:
        results[skipped] = ("", False)
    if not capped:
        return results

    # Défaut : échec. Une page rendue puis reconnue écrase son entrée.
    for idx in capped:
        results[idx] = ("", False)

    # D-098 : borné par le sémaphore global `OCR_SLOTS` (partagé avec les
    # images intégrées), plus de MAX_WORKERS² processus Tesseract.
    workers = min(OCR_MAX_CONCURRENCY, len(capped))
    # D-108 : les PNG ne sont plus tous gardés jusqu'à la fin du rendu, mais
    # la file du pool pourrait reproduire exactement le même pic si le rendu
    # (~85 ms/page) distance l'OCR (~1 s/page). `in_flight` borne le nombre
    # de PNG vivants à la fois : les travailleurs occupés, plus deux en
    # attente pour ne jamais les laisser sans travail.
    in_flight = threading.Semaphore(workers + 2)

    def _recognize(png: bytes) -> str:
        try:
            return ocr_with_slot(engine, png, lang)
        finally:
            in_flight.release()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures: dict[Future[str], int] = {}
        for idx in capped:
            image = _render_page_image(path, idx, expected_page_count)
            if image is None:
                continue
            # D-108 : hors `_PDFIUM_LOCK` — l'encodage PNG n'appelle jamais
            # PDFium et représentait ~83 % du temps passé sous le verrou.
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            del image
            in_flight.acquire()
            futures[executor.submit(_recognize, buf.getvalue())] = idx

        for future in as_completed(futures):
            idx = futures[future]
            text = future.result()
            results[idx] = (text, bool(text.strip()))

    return results
