"""Extracteur PPTX : .pptx.

CdC §8.3 — Texte des shapes, tableaux, notes d'orateur.
Diapo sans texte → [[DIAPO N: aucun texte extractible]].
Détecte les images via ppt/media/* dans le ZIP.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)


@register(".pptx")
class PptxExtractor(Extractor):
    """Extracteur PPTX via python-pptx + détection media."""

    file_type = "pptx"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".pptx"

    @classmethod
    def extract(cls, path: Path, relative_path: str) -> ExtractedFile:
        try:
            from pptx import Presentation

            image_count = _count_media_images(path)

            prs = Presentation(str(path))
            parts: list[str] = []
            slide_count = 0

            for i, slide in enumerate(prs.slides, 1):
                slide_count += 1
                slide_text: list[str] = []

                for shape in slide.shapes:
                    if shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            text = para.text.strip()
                            if text:
                                slide_text.append(text)

                    if shape.has_table:
                        table = shape.table
                        for row in table.rows:
                            cells = [cell.text.strip() for cell in row.cells]
                            slide_text.append(" | ".join(cells))

                # Notes d'orateur
                if slide.has_notes_slide:
                    notes = slide.notes_slide.notes_text_frame
                    if notes and notes.text.strip():
                        slide_text.append(f"[Notes] {notes.text.strip()}")

                if not slide_text:
                    slide_text.append(f"[[DIAPO {i}: aucun texte extractible]]")

                parts.append(f"## Diapo {i}\n\n" + "\n\n".join(slide_text))

            text = "\n\n---\n\n".join(parts)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension="pptx",
                file_type=cls.file_type,
                size_bytes=path.stat().st_size,
                text=text,
                status=FileStatus.READY,
                image_count=image_count,
                page_count=slide_count,
            )
        except Exception as exc:
            logger.exception("Erreur extraction PPTX %s", path)
            return error_result(path, relative_path, cls.file_type, exc)


def _count_media_images(path: Path) -> int:
    """Compte les images dans ppt/media/ du ZIP PPTX."""
    try:
        with zipfile.ZipFile(str(path), "r") as zf:
            return sum(1 for n in zf.namelist() if n.startswith("ppt/media/"))
    except Exception:
        return 0
