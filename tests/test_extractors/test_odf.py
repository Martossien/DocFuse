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

    def test_master_page_header_footer_is_extracted(self, tmp_path: Path) -> None:
        """D-072 : les en-têtes/pieds de page ODT vivent dans styles.xml
        (office:master-styles), jamais dans content.xml — invisibles sans
        un second passage dédié."""
        f = tmp_path / "headers.odt"
        content_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<office:document-content "
            'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
            "<office:body><office:text>"
            "<text:p>CORPS_DU_DOCUMENT_NORMAL</text:p>"
            "</office:text></office:body>"
            "</office:document-content>"
        )
        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<office:document-styles "
            'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
            "<office:master-styles>"
            '<style:master-page style:name="Standard" style:page-layout-name="Mpm1">'
            "<style:header><text:p>EN_TETE_CONFIDENTIEL_PROJET_X</text:p></style:header>"
            "<style:footer><text:p>PIED_DE_PAGE_REFERENCE_ABC</text:p></style:footer>"
            "</style:master-page>"
            "</office:master-styles>"
            "</office:document-styles>"
        )
        with zipfile.ZipFile(str(f), "w") as zf:
            zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")
            zf.writestr("content.xml", content_xml)
            zf.writestr("styles.xml", styles_xml)

        result = OdfExtractor.extract(f, "headers.odt")
        assert result.status is FileStatus.READY
        assert "CORPS_DU_DOCUMENT_NORMAL" in result.text
        assert "EN_TETE_CONFIDENTIEL_PROJET_X" in result.text
        assert "PIED_DE_PAGE_REFERENCE_ABC" in result.text
