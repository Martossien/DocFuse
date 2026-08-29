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
            # D-076 : data_only=True renvoie None pour une formule jamais
            # calculée (fichier généré par script, jamais ouvert dans
            # Excel/LibreOffice — pas de valeur en cache dans le fichier).
            # Sans ce second classeur (data_only=False, qui donne le TEXTE
            # de la formule), la cellule paraît vide sans aucune trace
            # qu'un calcul existait — perte silencieuse de colonnes de
            # totaux entières sur des exports automatisés (ERP/BI).
            wb_formulas = load_workbook(str(path), read_only=True, data_only=False)
            parts: list[str] = []

            for sheet in wb.sheetnames:
                ws = wb[sheet]
                ws_formulas = wb_formulas[sheet] if sheet in wb_formulas.sheetnames else None
                rows_text: list[str] = []
                has_data = False

                formula_rows = (
                    ws_formulas.iter_rows(values_only=True) if ws_formulas is not None else iter(())
                )
                for row in ws.iter_rows(values_only=True):
                    formula_row = next(formula_rows, ())
                    cells: list[str] = []
                    for idx, c in enumerate(row):
                        if c is not None:
                            cells.append(str(c))
                            continue
                        formula = formula_row[idx] if idx < len(formula_row) else None
                        if isinstance(formula, str) and formula.startswith("="):
                            cells.append(f"[formule non calculée: {formula}]")
                        else:
                            # BUG FIX: data_only=True retourne aussi None pour une
                            # cellule réellement vide. On la marque comme vide.
                            cells.append("")
                    if any(c.strip() for c in cells):
                        has_data = True
                        rows_text.append(" | ".join(cells))

                if has_data:
                    parts.append(f"### Feuille : {sheet}\n\n" + "\n".join(rows_text))
                else:
                    parts.append(f"### Feuille : {sheet}\n\n[Feuille vide]")

            sheet_count = len(wb.sheetnames)
            wb.close()
            wb_formulas.close()
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
