"""Extracteur Office legacy binaire : .doc, .xls, .ppt (Word/Excel/
PowerPoint 97-2003).

CdC §7.3 — texte intégral, sans dépendance externe.

D-094 : après une première analyse (D-093) concluant qu'aucune
bibliothèque Python légère et conforme licence n'existait pour ces
formats (`extract-msg` GPL, `olefile` seul insuffisant), une recherche
complémentaire a trouvé `office_oxide` (Rust, double licence
MIT/Apache-2.0, ~1,3 Mo par plateforme, aucun binaire externe ni JVM) —
testé directement sur des fichiers `.doc`/`.xls`/`.ppt` réels avant
adoption (voir journal-decisions.md).
"""

from __future__ import annotations

import logging
from pathlib import Path

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)

_LEGACY_EXTENSIONS: frozenset[str] = frozenset({".doc", ".xls", ".ppt"})


@register(".doc", ".xls", ".ppt")
class LegacyOfficeExtractor(Extractor):
    """Extracteur Word/Excel/PowerPoint 97-2003 (binaire) via office_oxide."""

    file_type = "legacy_office"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in _LEGACY_EXTENSIONS

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        ext = path.suffix.lower().lstrip(".")
        try:
            from office_oxide import OfficeOxideError, extract_text

            try:
                text = extract_text(str(path))
            except OfficeOxideError as exc:
                # D-094 : message clair plutôt que l'erreur Rust brute
                # ("CFB error: ...", "I/O error: ...") — même principe que
                # error.corrupt_file pour JSON/XML (D-092).
                return ExtractedFile(
                    path=path,
                    relative_path=relative_path,
                    extension=ext,
                    file_type=ext,
                    size_bytes=path.stat().st_size,
                    status=FileStatus.ERROR,
                    error_message=f"{t('error.corrupt_file')} : {exc}",
                )

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=ext,
                file_type=ext,
                size_bytes=path.stat().st_size,
                text=text,
                status=FileStatus.READY,
            )
        except Exception as exc:
            logger.exception("Erreur extraction Office legacy %s", path)
            return error_result(path, relative_path, ext, exc)
