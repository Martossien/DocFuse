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

    def test_odp_speaker_notes_are_separated_not_mixed(self, tmp_path: Path) -> None:
        """D-087 : .odp (office:presentation) tombait dans le fallback
        générique document-wide (aucun office:text dans une présentation),
        qui mélangeait indistinctement les notes d'orateur
        (presentation:notes, jamais affichées à l'écran) avec le contenu
        visible des diapos — risque de fuite de contenu non destiné à la
        diffusion, en plus de l'absence totale de séparation entre diapos."""
        f = tmp_path / "notes.odp"
        content_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<office:document-content "
            'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
            'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
            'xmlns:presentation="urn:oasis:names:tc:opendocument:xmlns:presentation:1.0">'
            "<office:body><office:presentation>"
            '<draw:page draw:name="page1">'
            "<draw:frame><draw:text-box><text:p>TITRE_VISIBLE_DIAPO_1</text:p></draw:text-box></draw:frame>"
            "<presentation:notes><draw:frame><draw:text-box>"
            "<text:p>NOTE_ORATEUR_SECRETE_PAS_VISIBLE</text:p>"
            "</draw:text-box></draw:frame></presentation:notes>"
            "</draw:page>"
            '<draw:page draw:name="page2">'
            "<draw:frame><draw:text-box><text:p>TITRE_VISIBLE_DIAPO_2</text:p></draw:text-box></draw:frame>"
            "</draw:page>"
            "</office:presentation></office:body>"
            "</office:document-content>"
        )
        with zipfile.ZipFile(str(f), "w") as zf:
            zf.writestr("mimetype", "application/vnd.oasis.opendocument.presentation")
            zf.writestr("content.xml", content_xml)

        result = OdfExtractor.extract(f, "notes.odp")
        assert result.status is FileStatus.READY
        assert "TITRE_VISIBLE_DIAPO_1" in result.text
        assert "TITRE_VISIBLE_DIAPO_2" in result.text
        assert "[notes orateur diapo 1]" in result.text
        assert "NOTE_ORATEUR_SECRETE_PAS_VISIBLE" in result.text
        # La note n'est pas mélangée au texte visible de la diapo 1 : elle
        # apparaît après l'étiquette dédiée, pas avant/dans le bloc "Diapo 1".
        slide1 = result.text.split("## Diapo 2")[0]
        assert slide1.index("TITRE_VISIBLE_DIAPO_1") < slide1.index("[notes orateur diapo 1]")

    def test_odp_table_in_slide_is_extracted(self, tmp_path: Path) -> None:
        """D-087 : un tableau dans une diapo tombait dans le même fallback
        non structuré que le reste (cellules aplaties sans séparateur)."""
        f = tmp_path / "table.odp"
        content_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<office:document-content "
            'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
            'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
            'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
            'xmlns:presentation="urn:oasis:names:tc:opendocument:xmlns:presentation:1.0">'
            "<office:body><office:presentation>"
            '<draw:page draw:name="page1">'
            "<draw:frame><draw:text-box><text:p>TITRE_DIAPO</text:p></draw:text-box></draw:frame>"
            "<table:table><table:table-row>"
            "<table:table-cell><text:p>Alpha</text:p></table:table-cell>"
            "<table:table-cell><text:p>Beta</text:p></table:table-cell>"
            "</table:table-row></table:table>"
            "</draw:page>"
            "</office:presentation></office:body>"
            "</office:document-content>"
        )
        with zipfile.ZipFile(str(f), "w") as zf:
            zf.writestr("mimetype", "application/vnd.oasis.opendocument.presentation")
            zf.writestr("content.xml", content_xml)

        result = OdfExtractor.extract(f, "table.odp")
        assert result.status is FileStatus.READY
        assert "TITRE_DIAPO" in result.text
        assert "Alpha | Beta" in result.text
