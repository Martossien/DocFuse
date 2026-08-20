"""Extracteur XLSX : .xlsx.

CdC §8.3 — Chaque feuille, cellules non vides, ordre A1…
Feuille vide signalée. Nom de feuille en titre.
"""

from __future__ import annotations

import logging
from pathlib import Path

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)


@register(".xlsx")
class XlsxExtractor(Extractor):
    """Extracteur XLSX via openpyxl."""

    file_type = "xlsx"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".xlsx"

    @classmethod
    def extract(cls, path: Path, relative_path: str) -> ExtractedFile:
        try:
            from openpyxl import load_workbook

            wb = load_workbook(str(path), read_only=True, data_only=True)
            parts: list[str] = []

            for sheet in wb.sheetnames:
                ws = wb[sheet]
                rows_text: list[str] = []
                has_data = False

                for row in ws.iter_rows(values_only=True):
                    cells: list[str] = []
                    for c in row:
                        if c is None:
                            # BUG FIX: data_only=True retourne None pour les formules
                            # non calculées (jamais ouvertes dans Excel). On marque
                            # la cellule comme vide plutôt que de perdre l'information.
                            cells.append("")
                        else:
                            cells.append(str(c))
                    if any(c.strip() for c in cells):
                        has_data = True
                        rows_text.append(" | ".join(cells))

                if has_data:
                    parts.append(f"### Feuille : {sheet}\n\n" + "\n".join(rows_text))
                else:
                    parts.append(f"### Feuille : {sheet}\n\n[Feuille vide]")

            sheet_count = len(wb.sheetnames)
            wb.close()
            text = "\n\n".join(parts)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension="xlsx",
                file_type=cls.file_type,
                size_bytes=path.stat().st_size,
                text=text,
                status=FileStatus.READY,
                page_count=sheet_count,
            )
        except Exception as exc:
            logger.exception("Erreur extraction XLSX %s", path)
            return error_result(path, relative_path, cls.file_type, exc)
