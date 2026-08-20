"""Extracteur Markdown : .md, .markdown.

CdC §7.3 — Tel quel (pas de transformation, le Markdown est déjà du texte structuré).
"""

from __future__ import annotations

from pathlib import Path

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.extractors.text import detect_encoding
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus


@register(".md", ".markdown")
class MarkdownExtractor(Extractor):
    """Extracteur pour les fichiers Markdown (tel quel)."""

    file_type = "markdown"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in (".md", ".markdown")

    @classmethod
    def extract(cls, path: Path, relative_path: str) -> ExtractedFile:
        try:
            raw = path.read_bytes()
            encoding, data = detect_encoding(raw)
            text = data.decode(encoding, errors="replace")

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=path.suffix.lower().lstrip("."),
                file_type=path.suffix.lower().lstrip("."),
                size_bytes=len(raw),
                text=text,
                status=FileStatus.READY,
                encoding=encoding,
            )
        except Exception as exc:
            return error_result(path, relative_path, cls.file_type, exc)
