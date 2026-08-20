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
                extension="pdf",
                file_type=cls.file_type,
                size_bytes=path.stat().st_size,
                text=full_text,
                status=FileStatus.READY,
                image_count=image_count,
                page_count=page_count,
                chars_per_page=chars_per_page,
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
