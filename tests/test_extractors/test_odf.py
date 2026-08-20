"""Tests de l'extracteur ODF (OpenDocument).

CdC §7.3 — Si ZIP/XML trivial (OpenDocument).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from docfuse.extractors.odf import OdfExtractor
from docfuse.models.file_status import FileStatus


class TestOdfExtractor:
    def test_extract_basic_odt(self, tmp_path: Path) -> None:
        f = tmp_path / "test.odt"
        content_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<office:document-content "
            'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
            "<office:body><office:text>"
            "<text:p>Ceci est un texte ODF de test avec suffisamment de caracteres.</text:p>"
            "</office:text></office:body>"
            "</office:document-content>"
        )
        with zipfile.ZipFile(str(f), "w") as zf:
            zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")
            zf.writestr("content.xml", content_xml)

        result = OdfExtractor.extract(f, "test.odt")
        assert result.status is FileStatus.READY
        assert "Ceci est un texte ODF" in result.text

    def test_accepts(self) -> None:
        assert OdfExtractor.accepts(Path("test.odt")) is True
        assert OdfExtractor.accepts(Path("test.ods")) is True
        assert OdfExtractor.accepts(Path("test.odp")) is True
        assert OdfExtractor.accepts(Path("test.docx")) is False

    def test_safe_extract_no_crash(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.odt"
        result = OdfExtractor.safe_extract(f, "nonexistent.odt")
        assert result.status is FileStatus.ERROR

    def test_missing_content_xml(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.odt"
        with zipfile.ZipFile(str(f), "w") as zf:
            zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")
            # Pas de content.xml

        result = OdfExtractor.extract(f, "bad.odt")
        assert result.status is FileStatus.ERROR

    def test_fixture_file(self) -> None:
        fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample.odt"
        if fixture.exists():
            result = OdfExtractor.extract(fixture, "sample.odt")
            assert result.status is FileStatus.READY
            assert "Ceci" in result.text or "texte" in result.text
