"""Extracteur XLSX : .xlsx.

CdC §8.3 — Chaque feuille, cellules non vides, ordre A1…
Feuille vide signalée. Nom de feuille en titre.
"""

from __future__ import annotations

import logging
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from contextlib import closing
from pathlib import Path

from docfuse.constants import OCR_LANG
from docfuse.core.embedded_images import build_image_marker, build_image_tag
from docfuse.core.ocr.base import OcrEngine
from docfuse.core.ocr.registry import resolve_ocr_engine
from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result, is_ole_encrypted, is_zip_bomb
from docfuse.i18n import t
from docfuse.models.extraction_result import EmbeddedImage, ExtractedFile
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
    def extract(cls, path: Path, relative_path: str, extract_images: bool = False) -> ExtractedFile:
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

            # D-093 : garde-fou "bombe zip" avant tout parsing du conteneur.
            if is_zip_bomb(path):
                return ExtractedFile(
                    path=path,
                    relative_path=relative_path,
                    extension="xlsx",
                    file_type=cls.file_type,
                    size_bytes=path.stat().st_size,
                    status=FileStatus.ERROR,
                    error_message=t("error.zip_bomb_suspected"),
                )

            # D-093 : OCR/export des images intégrées, seulement si utile
            # (export demandé ou OCR disponible) — sinon zéro coût ajouté.
            engine = resolve_ocr_engine()
            want_export = extract_images
            embedded_images: list[EmbeddedImage] = []

            from openpyxl import load_workbook

            # D-096 : `closing()` — les classeurs read_only gardent l'archive
            # ZIP ouverte jusqu'à `.close()`, qui n'était atteint que sur le
            # chemin nominal : toute exception dans la boucle des feuilles
            # laissait deux archives ouvertes jusqu'au GC.
            wb = closing(load_workbook(str(path), read_only=True, data_only=True))
            # D-076 : data_only=True renvoie None pour une formule jamais
            # calculée (fichier généré par script, jamais ouvert dans
            # Excel/LibreOffice — pas de valeur en cache dans le fichier).
            # Sans ce second classeur (data_only=False, qui donne le TEXTE
            # de la formule), la cellule paraît vide sans aucune trace
            # qu'un calcul existait — perte silencieuse de colonnes de
            # totaux entières sur des exports automatisés (ERP/BI).
            wb_formulas = closing(load_workbook(str(path), read_only=True, data_only=False))
            parts: list[str] = []

            with wb as wb_values, wb_formulas as wb_f, zipfile.ZipFile(str(path)) as zf:
                sheet_count = len(wb_values.sheetnames)
                for sheet in wb_values.sheetnames:
                    ws = wb_values[sheet]
                    # D-096 : une feuille graphique (`Chartsheet`, onglet
                    # "Graphique1") est listée dans `sheetnames` mais n'a ni
                    # cellules ni `reset_dimensions` → `AttributeError` qui
                    # mettait TOUT le classeur en ERROR, données perdues.
                    # Signalée explicitement, jamais silencieuse.
                    if not hasattr(ws, "iter_rows"):
                        parts.append(
                            f"### Feuille : {sheet}\n\n[Feuille graphique — pas de cellules]"
                        )
                        continue
                    ws_formulas = wb_f[sheet] if sheet in wb_f.sheetnames else None
                    if ws_formulas is not None and not hasattr(ws_formulas, "iter_rows"):
                        ws_formulas = None

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

                    sheet_text = "\n".join(rows_text) if has_data else "[Feuille vide]"

                    # D-093 : images intégrées ancrées sur cette feuille —
                    # regroupées en fin de feuille plutôt qu'à la cellule
                    # d'ancrage exacte (voir docstring de `_extract_sheet_images`).
                    if merge_path and merge_path in zf.namelist():
                        sheet_markers, sheet_images = _extract_sheet_images(
                            zf, merge_path, sheet, relative_path, engine, want_export
                        )
                        if sheet_markers:
                            sheet_text += "\n\n" + "\n\n".join(sheet_markers)
                        embedded_images.extend(sheet_images)

                    parts.append(f"### Feuille : {sheet}\n\n{sheet_text}")

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
                embedded_images=embedded_images,
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


def _extract_sheet_images(
    zf: zipfile.ZipFile,
    sheet_path: str,
    sheet_name: str,
    relative_path: str,
    engine: OcrEngine | None,
    want_export: bool,
) -> tuple[list[str], list[EmbeddedImage]]:
    """Images intégrées ancrées sur une feuille XLSX (D-093).

    `openpyxl` en mode `read_only=True` (obligatoire ici pour supporter de
    gros classeurs) n'expose pas du tout les dessins/images — on lit donc
    le XML brut du ZIP directement, en suivant la même chaîne de relations
    OOXML que python-pptx/python-docx font automatiquement pour DOCX/PPTX :
    `sheetN.xml` → `_rels/sheetN.xml.rels` (relation "drawing") →
    `drawingM.xml` (ancres `oneCellAnchor`/`twoCellAnchor`, chacune avec un
    `<a:blip r:embed="rIdY">`) → `_rels/drawingM.xml.rels` (relation
    "image") → fichier média réel.

    Les marqueurs sont regroupés en fin de feuille plutôt qu'ancrés à la
    cellule exacte : la position (ligne, colonne) de l'ancre XML ne
    correspond pas forcément à une ligne "avec données" au sens du texte
    déjà généré (tableau pipe par ligne non vide) — une fausse précision
    d'ancrage serait trompeuse.

    Returns:
        Tuple (marqueurs à ajouter au texte de la feuille, images à
        exporter). N'échoue jamais : toute relation manquante ou XML
        illisible donne simplement une liste vide.
    """
    markers: list[str] = []
    images: list[EmbeddedImage] = []
    if not want_export and engine is None:
        return markers, images

    sheet_rels_path = posixpath.join(
        posixpath.dirname(sheet_path), "_rels", posixpath.basename(sheet_path) + ".rels"
    )
    if sheet_rels_path not in zf.namelist():
        return markers, images

    try:
        drawing_target = _find_target_by_type(zf.read(sheet_rels_path), "/drawing")
    except Exception:
        return markers, images
    if not drawing_target:
        return markers, images

    drawing_path = _resolve_rel_target(sheet_path, drawing_target)
    if drawing_path not in zf.namelist():
        return markers, images

    drawing_rels_path = posixpath.join(
        posixpath.dirname(drawing_path), "_rels", posixpath.basename(drawing_path) + ".rels"
    )
    try:
        drawing_rels = (
            _parse_relationships(zf.read(drawing_rels_path))
            if drawing_rels_path in zf.namelist()
            else {}
        )
        image_rids = _parse_drawing_images(zf.read(drawing_path))
    except Exception:
        logger.warning("Lecture du dessin %s échouée", drawing_path, exc_info=True)
        return markers, images

    count = 0
    for rid in image_rids:
        target = drawing_rels.get(rid)
        if not target:
            continue
        media_path = _resolve_rel_target(drawing_path, target)
        try:
            data = zf.read(media_path)
        except KeyError:
            continue

        count += 1
        ext = media_path.rsplit(".", 1)[-1] if "." in media_path else "png"
        tag = build_image_tag(relative_path, f"sheet_{sheet_name}", count, ext)

        ocr_text = ""
        if engine is not None:
            try:
                ocr_text = engine.ocr_image(data, OCR_LANG)
            except Exception:
                logger.warning("Échec OCR image %s", tag, exc_info=True)

        marker = build_image_marker(tag if want_export else None, ocr_text, OCR_LANG)
        if not marker:
            continue
        markers.append(marker)
        if want_export:
            images.append(EmbeddedImage(filename=tag, data=data))

    return markers, images


def _resolve_rel_target(owner_part: str, target: str) -> str:
    """Résout un `Target` de relation OOXML (absolu `/xl/...` ou relatif
    `../drawings/...`) en chemin ZIP sans slash initial."""
    if target.startswith("/"):
        return target.lstrip("/")
    base_dir = posixpath.dirname(owner_part)
    return posixpath.normpath(posixpath.join(base_dir, target))


def _find_target_by_type(rels_xml: bytes, type_suffix: str) -> str | None:
    """Premier `Target` d'un fichier `.rels` dont le `Type` se termine par
    `type_suffix` (ex: "/drawing")."""
    try:
        root = ET.fromstring(rels_xml)
    except ET.ParseError:
        return None
    for rel in root:
        if (rel.get("Type") or "").endswith(type_suffix):
            return rel.get("Target")
    return None


def _parse_relationships(rels_xml: bytes) -> dict[str, str]:
    """Table `Id -> Target` complète d'un fichier `.rels`."""
    try:
        root = ET.fromstring(rels_xml)
    except ET.ParseError:
        return {}
    return {rel.get("Id", ""): rel.get("Target", "") for rel in root}


def _parse_drawing_images(drawing_xml: bytes) -> list[str]:
    """`rId` (attribut `r:embed`) de chaque image d'un `drawingN.xml`, dans
    l'ordre d'apparition des ancres (`oneCellAnchor`/`twoCellAnchor`)."""
    try:
        root = ET.fromstring(drawing_xml)
    except ET.ParseError:
        return []
    rids: list[str] = []
    for anchor in root:
        if not (anchor.tag.endswith("}oneCellAnchor") or anchor.tag.endswith("}twoCellAnchor")):
            continue
        for el in anchor.iter():
            if el.tag.endswith("}blip"):
                rid = next((v for k, v in el.attrib.items() if k.endswith("}embed")), None)
                if rid:
                    rids.append(rid)
    return rids


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
