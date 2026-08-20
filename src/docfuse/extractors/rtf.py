"""Extracteur RTF : .rtf.

Utilise la bibliothèque striprtf (MIT) pour extraire le texte.
"""

from __future__ import annotations

import logging
from pathlib import Path

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)


@register(".rtf")
class RtfExtractor(Extractor):
    """Extracteur RTF via striprtf."""

    file_type = "rtf"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".rtf"

    @classmethod
    def extract(cls, path: Path, relative_path: str) -> ExtractedFile:
        try:
            from striprtf.striprtf import rtf_to_text

            raw = path.read_bytes()
            rtf_text = raw.decode("latin-1", errors="replace")
            text = str(rtf_to_text(rtf_text))  # type: ignore[no-untyped-call]

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension="rtf",
                file_type=path.suffix.lower().lstrip("."),
                size_bytes=len(raw),
                text=text,
                status=FileStatus.READY,
                encoding="latin-1",
            )
        except Exception as exc:
            logger.exception("Erreur extraction RTF %s", path)
            return error_result(path, relative_path, cls.file_type, exc)
