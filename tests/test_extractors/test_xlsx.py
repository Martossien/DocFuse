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
