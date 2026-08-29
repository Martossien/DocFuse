"""Tests de l'extracteur XLSX.

CdC §8.3 — Chaque feuille, cellules non vides, ordre A1.
Feuille vide signalée. Nom de feuille en titre.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.extractors.xlsx import XlsxExtractor
from docfuse.models.file_status import FileStatus


class TestXlsxExtractor:
    def test_extract_basic_sheet(self, tmp_path: Path) -> None:
        import openpyxl

        f = tmp_path / "test.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Data"
        ws["A1"] = "Nom"
        ws["B1"] = "Valeur"
        ws["A2"] = "Test avec du texte"
        ws["B2"] = "42"
        wb.save(str(f))

        result = XlsxExtractor.extract(f, "test.xlsx")
        assert result.status is FileStatus.READY
        assert "Nom" in result.text
        assert "Valeur" in result.text
        assert "Data" in result.text  # Nom de feuille

    def test_empty_sheet_signaled(self, tmp_path: Path) -> None:
        import openpyxl

        f = tmp_path / "empty.xlsx"
        wb = openpyxl.Workbook()
        wb.active.title = "Vide"
        wb.save(str(f))

        result = XlsxExtractor.extract(f, "empty.xlsx")
        assert "[Feuille vide]" in result.text

    def test_accepts(self) -> None:
        assert XlsxExtractor.accepts(Path("test.xlsx")) is True
        assert XlsxExtractor.accepts(Path("test.csv")) is False

    def test_safe_extract_no_crash(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.xlsx"
        result = XlsxExtractor.safe_extract(f, "nonexistent.xlsx")
        assert result.status is FileStatus.ERROR

    def test_fixture_file(self) -> None:
        fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xlsx"
        if fixture.exists():
            result = XlsxExtractor.extract(fixture, "sample.xlsx")
            assert result.status is FileStatus.READY
            assert "Feuille1" in result.text

    def test_uncalculated_formula_text_is_recovered(self, tmp_path: Path) -> None:
        """D-076 : une formule jamais calculée (fichier généré par script,
        jamais ouvert dans Excel/LibreOffice — pas de valeur en cache dans
        le fichier) ne doit pas disparaître silencieusement. `data_only=True`
        renvoie None pour ces cellules, indistinguable d'une cellule
        réellement vide sans relire le classeur en data_only=False."""
        import openpyxl

        f = tmp_path / "formulas.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "Total"
        ws["B1"] = "=1+1"  # jamais "calculée" : openpyxl n'évalue jamais les formules
        wb.save(str(f))

        result = XlsxExtractor.extract(f, "formulas.xlsx")
        assert result.status is FileStatus.READY
        assert "=1+1" in result.text

    def test_incorrect_declared_dimension_does_not_truncate_rows(self, tmp_path: Path) -> None:
        """D-084 : en mode read_only, openpyxl fait confiance à l'élément XML
        <dimension> déclaré par le fichier plutôt que de scanner le contenu
        réel. Un générateur tiers qui écrit une dimension trop petite (bug
        connu et documenté par openpyxl lui-même) faisait tronquer
        silencieusement les lignes en fin de feuille."""
        import zipfile

        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        for i in range(1, 11):
            ws.cell(row=i, column=1, value=f"Row{i}")
        f = tmp_path / "lied_dimension.xlsx"
        wb.save(str(f))

        # Mentir sur la dimension déclarée : A1:A10 -> A1:A3.
        with zipfile.ZipFile(str(f)) as zin:
            items = zin.infolist()
            contents = {item.filename: zin.read(item.filename) for item in items}
        sheet_xml = contents["xl/worksheets/sheet1.xml"].decode("utf-8")
        sheet_xml = sheet_xml.replace('<dimension ref="A1:A10"/>', '<dimension ref="A1:A3"/>')
        contents["xl/worksheets/sheet1.xml"] = sheet_xml.encode("utf-8")
        with zipfile.ZipFile(str(f), "w", zipfile.ZIP_DEFLATED) as zout:
            for item in items:
                zout.writestr(item, contents[item.filename])

        result = XlsxExtractor.extract(f, "lied_dimension.xlsx")
        assert result.status is FileStatus.READY
        for i in range(1, 11):
            assert f"Row{i}" in result.text

    def test_merged_cells_value_is_propagated(self, tmp_path: Path) -> None:
        """D-085 : seule la cellule en haut à gauche d'une plage fusionnée
        porte une valeur (comportement Excel normal) — `ReadOnlyWorksheet`
        n'expose même pas `merged_cells`. Sans propagation, une ligne dont
        le titre fusionné s'étale sur plusieurs colonnes perd tout contexte
        pour les cellules "creuses" qui suivent."""
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "Titre fusionne"
        ws.merge_cells("A1:C1")
        ws["A2"] = "Alpha"
        ws["B2"] = "Beta"
        ws["C2"] = "Gamma"
        f = tmp_path / "merged_horizontal.xlsx"
        wb.save(str(f))

        result = XlsxExtractor.extract(f, "merged_horizontal.xlsx")
        assert result.status is FileStatus.READY
        assert "Titre fusionne | Titre fusionne | Titre fusionne" in result.text

    def test_merged_cells_vertical_value_is_propagated(self, tmp_path: Path) -> None:
        """D-085, fusion verticale (sur plusieurs lignes plutôt que colonnes)."""
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "Section"
        ws.merge_cells("A1:A3")
        ws["B1"] = "L1"
        ws["B2"] = "L2"
        ws["B3"] = "L3"
        f = tmp_path / "merged_vertical.xlsx"
        wb.save(str(f))

        result = XlsxExtractor.extract(f, "merged_vertical.xlsx")
        assert result.status is FileStatus.READY
        assert "Section | L1" in result.text
        assert "Section | L2" in result.text
        assert "Section | L3" in result.text

    def test_truly_empty_cell_stays_empty(self, tmp_path: Path) -> None:
        """Non-régression : une cellule réellement vide (pas une formule non
        calculée) ne doit pas récupérer de faux marqueur de formule."""
        import openpyxl

        f = tmp_path / "blank_cell.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "Label"
        ws["A3"] = "AfterGap"
        wb.save(str(f))

        result = XlsxExtractor.extract(f, "blank_cell.xlsx")
        assert result.status is FileStatus.READY
        assert "formule" not in result.text
