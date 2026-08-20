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
