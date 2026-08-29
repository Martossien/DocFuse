"""Tests de l'extracteur Office legacy binaire (.doc, .xls, .ppt).

CdC §7.3 — Word/Excel/PowerPoint 97-2003, via `office_oxide` (D-094).
"""

from __future__ import annotations

from pathlib import Path

from docfuse.extractors.legacy_office import LegacyOfficeExtractor
from docfuse.models.file_status import FileStatus

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class TestLegacyOfficeExtractor:
    def test_accepts(self) -> None:
        assert LegacyOfficeExtractor.accepts(Path("rapport.doc")) is True
        assert LegacyOfficeExtractor.accepts(Path("classeur.xls")) is True
        assert LegacyOfficeExtractor.accepts(Path("diaporama.ppt")) is True
        assert LegacyOfficeExtractor.accepts(Path("moderne.docx")) is False

    def test_safe_extract_no_crash(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.doc"
        result = LegacyOfficeExtractor.safe_extract(f, "nonexistent.doc")
        assert result.status is FileStatus.ERROR

    def test_corrupt_doc_gives_clear_error(self, tmp_path: Path) -> None:
        f = tmp_path / "broken.doc"
        f.write_bytes(b"ceci n'est pas un fichier .doc valide")

        result = LegacyOfficeExtractor.extract(f, "broken.doc")
        assert result.status is FileStatus.ERROR
        assert result.error_message is not None
        assert "corrompu" in result.error_message.lower()

    def test_extract_doc_fixture(self) -> None:
        fixture = _FIXTURES / "sample.doc"
        if not fixture.exists():
            return
        result = LegacyOfficeExtractor.extract(fixture, "sample.doc")
        assert result.status is FileStatus.READY
        assert "Titre Test Document" in result.text
        assert result.file_type == "doc"

    def test_extract_xls_fixture(self) -> None:
        fixture = _FIXTURES / "sample.xls"
        if not fixture.exists():
            return
        result = LegacyOfficeExtractor.extract(fixture, "sample.xls")
        assert result.status is FileStatus.READY
        assert "Feuille1" in result.text
        assert "Feuille2" in result.text
        assert result.file_type == "xls"

    def test_extract_ppt_fixture(self) -> None:
        fixture = _FIXTURES / "sample.ppt"
        if not fixture.exists():
            return
        result = LegacyOfficeExtractor.extract(fixture, "sample.ppt")
        assert result.status is FileStatus.READY
        assert "Titre Diapo" in result.text
        assert result.file_type == "ppt"
