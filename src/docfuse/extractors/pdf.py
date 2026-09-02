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

import logging
from pathlib import Path
from typing import Any

from docfuse.constants import (
    PDF_BOILERPLATE_MAX_LINE_LEN,
    PDF_BOILERPLATE_MIN_OCCURRENCES,
    PDF_BOILERPLATE_MIN_PAGES,
    PDF_BOILERPLATE_MIN_RATIO,
)
from docfuse.core.registry import register
from docfuse.extractors.base import (
    Extractor,
    error_result,
    error_result_message,
    file_type_for,
)

# Réexports : l'API historique de ce module (tests, appelants) reste valable.
from docfuse.extractors.pdf_ocr import (
    _apply_ocr as _apply_ocr,
)
from docfuse.extractors.pdf_ocr import (
    _ocr_pages as _ocr_pages,
)
from docfuse.extractors.pdf_ocr import (
    _ocr_render_scale as _ocr_render_scale,
)
from docfuse.extractors.pdf_ocr import (
    _render_page_image as _render_page_image,
)
from docfuse.extractors.pdf_pages import (
    PageKind as PageKind,
)
from docfuse.extractors.pdf_pages import (
    PdfPageCountMismatchError as PdfPageCountMismatchError,
)
from docfuse.extractors.pdf_pages import (
    _blank_if_garbage as _blank_if_garbage,
)
from docfuse.extractors.pdf_pages import (
    _has_garbage_text as _has_garbage_text,
)
from docfuse.extractors.pdf_pages import (
    classify_page as classify_page,
)
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)

__all__ = [
    "PageKind",
    "PdfExtractor",
    "PdfPageCountMismatchError",
    "classify_page",
]


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
