"""Extracteur PDF : .pdf.

CdC §8.3 — Texte de chaque page, dans l'ordre des pages.
Page vide → marqueur [[PAGE N: aucun texte extractible]].
CdC §9.4 — Détection images via XObject /Subtype /Image + LTImage/LTFigure.
CdC §14.3 — pdfminer.six (MIT) pour extraction + détection images ;
            pypdf (BSD) pour inventaire pages + détection encryption.

Inspiré de MarkItDown PdfConverter :
- extract_pages() pour traiter page-par-page (libération mémoire).
- extract_text() en fallback si le rendu est trop pauvre.
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
from docfuse.extractors.base import Extractor, error_result
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)


@register(".pdf")
class PdfExtractor(Extractor):
    """Extracteur PDF via pdfminer.six + pypdf."""

    file_type = "pdf"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    @classmethod
    def extract(cls, path: Path, relative_path: str) -> ExtractedFile:
        try:
            # 1. Vérifier l'encryption avec pypdf
            encrypted = _check_encrypted(path)
            if encrypted:
                return ExtractedFile(
                    path=path,
                    relative_path=relative_path,
                    extension="pdf",
                    file_type=cls.file_type,
                    size_bytes=path.stat().st_size,
                    status=FileStatus.ERROR,
                    error_message=t("error.encrypted_pdf"),
                )

            # 2. Extraction texte page-par-page avec pdfminer
            pages_text, chars_per_page, image_count, page_count = _extract_pages_pdfminer(path)

            # 2b. Déduplication des en-têtes/pieds de page répétés sur chaque page.
            # Recalcule chars_per_page à partir du texte dédupliqué : la densité de
            # texte utile pour la détection de pauvreté (image_detector.py) doit
            # refléter le contenu réel, pas le bruit répété.
            pages_text, dedup_note = _dedupe_page_boilerplate(pages_text)
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

            extra_metadata: dict[str, str] = {}
            if dedup_note:
                extra_metadata["pdf_dedup"] = dedup_note

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension="pdf",
                file_type=cls.file_type,
                size_bytes=path.stat().st_size,
                text=full_text,
                status=FileStatus.READY,
                image_count=image_count,
                page_count=page_count,
                chars_per_page=chars_per_page,
                extra_metadata=extra_metadata,
            )
        except Exception as exc:
            logger.exception("Erreur extraction PDF %s", path)
            return error_result(path, relative_path, cls.file_type, exc)


def _check_encrypted(path: Path) -> bool:
    """Vérifie si le PDF est chiffré / protégé par mot de passe via pypdf."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return reader.is_encrypted
    except Exception:
        # Si pypdf échoue, on continue avec pdfminer
        return False


def _extract_pages_pdfminer(
    path: Path,
) -> tuple[list[str], list[int], int, int]:
    """Extrait le texte et les images page par page via pdfminer.six.

    Returns:
        Tuple (textes par page, caractères par page, nombre d'images, nombre de pages).
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTFigure, LTImage, LTTextContainer

    pages_text: list[str] = []
    chars_per_page: list[int] = []
    total_images = 0
    page_count = 0

    for page in extract_pages(str(path)):
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

            # Figures (contiennent souvent des images / XObjects Form)
            if isinstance(element, LTFigure):
                page_images += _count_images_in_figure(element)

        total_images += page_images
        page_text = "\n".join(page_text_parts)
        pages_text.append(page_text)
        chars_per_page.append(len(page_text.strip()))

        # Libération mémoire (inspiré de MarkItDown PdfConverter:566)
        # pdfminer gère la mémoire page-par-page avec extract_pages()

    return pages_text, chars_per_page, total_images, page_count


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

    # Compter les occurrences des lignes candidates (première/dernière de chaque page).
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

    min_occurrences = max(
        PDF_BOILERPLATE_MIN_OCCURRENCES, round(PDF_BOILERPLATE_MIN_RATIO * page_count)
    )
    boilerplate = {line for line, count in occurrences.items() if count >= min_occurrences}
    if not boilerplate:
        return pages_text, None

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

    total_occurrences = sum(occurrences[line] for line in boilerplate)
    note = t(
        "pdf.dedup_note",
        count=len(boilerplate),
        occurrences=total_occurrences,
        chars=chars_saved,
    )
    return new_pages, note


def _count_images_in_figure(figure: Any) -> int:
    """M-02: Compte les images dans un LTFigure (récursion profonde sur les sous-figures)."""
    from pdfminer.layout import LTFigure, LTImage

    def _count_recursive(element: Any) -> int:
        count = 0
        for child in element:
            if isinstance(child, LTImage):
                count += 1
            if isinstance(child, LTFigure):
                count += _count_recursive(child)
        return count

    return _count_recursive(figure)
