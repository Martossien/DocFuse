"""Extracteur XLSX : .xlsx.

CdC §8.3 — Chaque feuille, cellules non vides, ordre A1…
Feuille vide signalée. Nom de feuille en titre.
"""

from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result, is_ole_encrypted
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)

_MERGE_CELL_REF_RE = re.compile(r'<mergeCell ref="([^"]+)"')


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
            # D-089 : un .xlsx protégé par mot de passe à l'ouverture est un
            # conteneur OLE2, plus un ZIP — sans cette détection, openpyxl
            # échoue avec un `BadZipFile` bas niveau qui ne dit jamais à
            # l'utilisateur que le fichier est protégé.
            if is_ole_encrypted(path):
                return ExtractedFile(
                    path=path,
                    relative_path=relative_path,
                    extension="xlsx",
                    file_type=cls.file_type,
                    size_bytes=path.stat().st_size,
                    status=FileStatus.ERROR,
                    error_message=t("error.encrypted_office"),
                )

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

            with zipfile.ZipFile(str(path)) as zf:
                for sheet in wb.sheetnames:
                    ws = wb[sheet]
                    ws_formulas = wb_formulas[sheet] if sheet in wb_formulas.sheetnames else None

                    # D-084 : en mode read_only, openpyxl fait confiance à
                    # l'élément XML <dimension> déclaré par le fichier
                    # plutôt que de scanner le contenu réel. Certains
                    # générateurs tiers écrivent une dimension incorrecte
                    # (trop petite) — iter_rows() tronque alors
                    # silencieusement les lignes/colonnes en fin de
                    # feuille, sans erreur. On force un vrai recalcul avant
                    # de lire. `calculate_dimension(force=True)` lève
                    # `UnboundLocalError` sur une feuille réellement vide
                    # (bug openpyxl : `cell` jamais assignée dans sa
                    # boucle) — sans conséquence, `has_data` reste `False`.
                    for candidate in (ws, ws_formulas):
                        if candidate is None:
                            continue
                        try:
                            candidate.reset_dimensions()
                            candidate.calculate_dimension(force=True)
                        except UnboundLocalError:
                            pass

                    rows_text: list[str] = []
                    has_data = False

                    formula_rows = (
                        ws_formulas.iter_rows(values_only=True)
                        if ws_formulas is not None
                        else iter(())
                    )
                    grid: list[list[str]] = []
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
                        grid.append(cells)

                    # D-085 : seule la cellule en haut à gauche d'une plage
                    # fusionnée porte une valeur — les autres sont vides
                    # (comportement Excel normal, pas un bug openpyxl).
                    # Sans propager cette valeur, une ligne dont le titre
                    # fusionné s'étale sur plusieurs colonnes/lignes perd
                    # tout contexte pour les cellules "creuses" qui suivent
                    # — très fréquent dans les tableaux "présentables"
                    # (rapports, tableaux de bord).
                    merge_path = getattr(ws, "_worksheet_path", "").lstrip("/")
                    if merge_path and merge_path in zf.namelist():
                        _apply_merged_cells(grid, _merge_ranges(zf, merge_path))

                    for cells in grid:
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


def _merge_ranges(zf: zipfile.ZipFile, worksheet_path: str) -> list[tuple[int, int, int, int]]:
    """Plages fusionnées `(min_col, min_row, max_col, max_row)` d'une feuille.

    Lu directement dans le XML de la feuille : `ReadOnlyWorksheet` (mode
    `read_only=True`, utilisé partout dans cet extracteur) n'expose pas
    `merged_cells` du tout (D-085) — seul le classeur normal l'expose,
    mais le charger entièrement en mémoire annulerait l'intérêt du mode
    `read_only` pour de gros fichiers.
    """
    from openpyxl.utils import range_boundaries

    try:
        xml = zf.read(worksheet_path).decode("utf-8", errors="replace")
    except KeyError:
        return []

    ranges: list[tuple[int, int, int, int]] = []
    for ref in _MERGE_CELL_REF_RE.findall(xml):
        try:
            min_col, min_row, max_col, max_row = range_boundaries(ref)
        except ValueError:
            continue
        if None in (min_col, min_row, max_col, max_row):
            continue
        ranges.append((min_col, min_row, max_col, max_row))
    return ranges


def _apply_merged_cells(grid: list[list[str]], ranges: list[tuple[int, int, int, int]]) -> None:
    """Propage la valeur de la cellule en haut à gauche de chaque plage
    fusionnée à toutes les autres cellules de cette plage, en mutant `grid`
    en place (`grid[ligne][colonne]`, 0-indexé ; `ranges` est 1-indexé,
    convention Excel/openpyxl)."""
    for min_col, min_row, max_col, max_row in ranges:
        r0, c0 = min_row - 1, min_col - 1
        if r0 >= len(grid) or c0 >= len(grid[r0]):
            continue
        top_left_value = grid[r0][c0]
        if not top_left_value:
            continue
        for r in range(min_row - 1, max_row):
            if r >= len(grid):
                break
            row_cells = grid[r]
            for c in range(min_col - 1, max_col):
                if c >= len(row_cells) or (r, c) == (r0, c0):
                    continue
                if not row_cells[c]:
                    row_cells[c] = top_left_value
