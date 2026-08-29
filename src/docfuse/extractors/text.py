"""Extracteur texte brut : .txt, .text, .log.

CdC §7.2 — Encodage : BOM, puis UTF-8, puis cp1252, latin-1 en dernier.
Signalé au rapport.
"""

from __future__ import annotations

import logging
from pathlib import Path

from docfuse.constants import CODE_EXTENSIONS
from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)

# .txt/.text/.log (CdC §7.2) + fichiers de développement (CODE_EXTENSIONS,
# §7.3) : même traitement, un texte brut est un texte brut.
_TEXT_LIKE_EXTENSIONS: frozenset[str] = frozenset({".txt", ".text", ".log"}) | CODE_EXTENSIONS


def detect_encoding(data: bytes) -> tuple[str, bytes]:
    """Détecte l'encodage d'un fichier texte.

    Ordre de tentative (CdC §7.2) :
    1. BOM UTF-8/UTF-16 → encodage correspondant
    2. UTF-8 strict
    3. cp1252 (Windows Latin-1, très fréquent)
    4. charset-normalizer (fallback encodages exotiques)
    5. latin-1 (dernier recours, ne rate jamais)

    Returns:
        Tuple (encodage détecté, données sans BOM si applicable).
    """
    # 1. BOM
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", data[3:]
    if data.startswith(b"\xff\xfe"):
        return "utf-16", data  # M-01: "utf-16" strippe le BOM automatiquement
    if data.startswith(b"\xfe\xff"):
        return "utf-16", data  # M-01: "utf-16" strippe le BOM automatiquement

    # 2. UTF-8 strict
    try:
        data.decode("utf-8")
        return "utf-8", data
    except UnicodeDecodeError:
        pass

    # 3. cp1252 (Windows Latin-1 étendu — très fréquent sous Windows)
    # Essayer cp1252 AVANT charset-normalizer car ce dernier peut
    # retourner des encodages improbables (ex: mac_latin2) pour les fichiers courts.
    try:
        data.decode("cp1252")
        return "cp1252", data
    except UnicodeDecodeError:
        pass

    # 4. charset-normalizer (fallback pour les encodages exotiques)
    try:
        from charset_normalizer import from_bytes

        result = from_bytes(data).best()
        if result and result.encoding:
            return result.encoding, data
    except Exception:
        pass

    # 5. latin-1 (ne rate jamais)
    return "latin-1", data


@register(*_TEXT_LIKE_EXTENSIONS)
class TextExtractor(Extractor):
    """Extracteur pour les fichiers texte brut (dont les fichiers de développement)."""

    file_type = "text"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in _TEXT_LIKE_EXTENSIONS

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
            logger.exception("Erreur extraction texte %s", path)
            return error_result(path, relative_path, cls.file_type, exc)
