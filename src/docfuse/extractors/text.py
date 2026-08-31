"""Extracteur texte brut : .txt, .text, .log.

CdC §7.2 — Encodage : BOM, puis UTF-8, puis cp1252, latin-1 en dernier.
Signalé au rapport.

D-106 : la détection d'encodage et la réparation de mojibake vivent
désormais dans `core/encoding.py` (service transverse, six modules en
dépendent). Les noms restent réexportés ici : c'est l'adresse historique de
cette API, et un extracteur n'a pas à être importé pour décoder du texte.
"""

from __future__ import annotations

import logging
from pathlib import Path

from docfuse.constants import CODE_EXTENSIONS
from docfuse.core.encoding import (
    decode_text,
    decode_text_with_note,
    detect_encoding,
    mojibake_metadata,
    repair_mojibake,
)
from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result, file_type_for
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)

__all__ = [
    "TextExtractor",
    "decode_text",
    "decode_text_with_note",
    "detect_encoding",
    "mojibake_metadata",
    "repair_mojibake",
]

# .txt/.text/.log (CdC §7.2) + fichiers de développement (CODE_EXTENSIONS,
# §7.3) : même traitement, un texte brut est un texte brut.
_TEXT_LIKE_EXTENSIONS: frozenset[str] = frozenset({".txt", ".text", ".log"}) | CODE_EXTENSIONS


@register(*_TEXT_LIKE_EXTENSIONS)
class TextExtractor(Extractor):
    """Extracteur pour les fichiers texte brut (dont les fichiers de développement)."""

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in _TEXT_LIKE_EXTENSIONS

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            raw = path.read_bytes()
            encoding, text, extra_metadata = decode_text_with_note(raw)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=file_type_for(path),
                file_type=file_type_for(path),
                size_bytes=len(raw),
                text=text,
                status=FileStatus.READY,
                encoding=encoding,
                extra_metadata=extra_metadata,
            )
        except Exception as exc:
            logger.exception("Erreur extraction texte %s", path)
            return error_result(path, relative_path, exc)
