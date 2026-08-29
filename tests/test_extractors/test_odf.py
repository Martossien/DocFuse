"""Tests de l'extracteur ODF (OpenDocument).

CdC §7.3 — Si ZIP/XML trivial (OpenDocument).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from docfuse.core.ocr.tesseract import TesseractEngine
from docfuse.extractors.odf import OdfExtractor
from docfuse.models.file_status import FileStatus

_OCR_AVAILABLE = TesseractEngine().is_available()

_ODT_NS = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
    'xmlns:xlink="http://www.w3.org/1999/xlink"'
)

_ODP_NS = _ODT_NS + (' xmlns:presentation="urn:oasis:names:tc:opendocument:xmlns:presentation:1.0"')


def _red_square_png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (50, 50), "red").save(buf, format="PNG")
    return buf.getvalue()


def _odt_with_image(tmp_path: Path, name: str, image_bytes: bytes) -> Path:
    f = tmp_path / name
    content_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {_ODT_NS}>'
        "<office:body><office:text>"
        "<text:p>Texte avant image.</text:p>"
        '<text:p><draw:frame><draw:image xlink:href="Pictures/img1.png"/></draw:frame></text:p>'
        "<text:p>Texte apres image.</text:p>"
        "</office:text></office:body></office:document-content>"
    )
    with zipfile.ZipFile(str(f), "w") as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        zf.writestr("content.xml", content_xml)
        zf.writestr("Pictures/img1.png", image_bytes)
    return f


def _odp_with_image(tmp_path: Path, name: str, image_bytes: bytes) -> Path:
    f = tmp_path / name
    content_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {_ODP_NS}>'
        "<office:body><office:presentation>"
        '<draw:page draw:name="page1">'
        '<draw:frame><draw:image xlink:href="Pictures/slide1.png"/></draw:frame>'
        "<text:p>Titre diapo 1</text:p>"
        "</draw:page>"
        "</office:presentation></office:body></office:document-content>"
    )
    with zipfile.ZipFile(str(f), "w") as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.presentation")
        zf.writestr("content.xml", content_xml)
        zf.writestr("Pictures/slide1.png", image_bytes)
    return f


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

    def test_odt_embedded_image_export_creates_embedded_images(self, tmp_path: Path) -> None:
        """D-093 : export actif -> l'image ODT est capturée et un tag
        `[[IMAGE: ...]]` inséré au point d'apparition."""
        f = _odt_with_image(tmp_path, "with_image.odt", _red_square_png())

        result = OdfExtractor.extract(f, "with_image.odt", extract_images=True)
        assert result.status is FileStatus.READY
        assert len(result.embedded_images) == 1
        image = result.embedded_images[0]
        assert image.filename.startswith("with_image__img1")
        assert f"[[IMAGE: {image.filename}]]" in result.text

    def test_odt_embedded_image_export_disabled_by_default(self, tmp_path: Path) -> None:
        f = _odt_with_image(tmp_path, "with_image2.odt", _red_square_png())

        result = OdfExtractor.extract(f, "with_image2.odt")
        assert result.embedded_images == []
        assert "[[IMAGE" not in result.text

    @pytest.mark.skipif(not _OCR_AVAILABLE, reason="Tesseract non installé")
    def test_odt_embedded_image_ocr_extracts_text_automatically(self, tmp_path: Path) -> None:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (300, 80), "white")
        draw = ImageDraw.Draw(img)
        draw.text((10, 30), "Bonjour ODT", fill="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        f = _odt_with_image(tmp_path, "with_text_image.odt", buf.getvalue())

        result = OdfExtractor.extract(f, "with_text_image.odt")
        assert "onjour" in result.text or "ODT" in result.text
        assert result.embedded_images == []

    def test_odp_embedded_image_export_creates_embedded_images(self, tmp_path: Path) -> None:
        """D-093 : export actif -> l'image ODP est capturée avec le numéro
        de diapo dans le nom."""
        f = _odp_with_image(tmp_path, "with_image.odp", _red_square_png())

        result = OdfExtractor.extract(f, "with_image.odp", extract_images=True)
        assert result.status is FileStatus.READY
        assert len(result.embedded_images) == 1
        image = result.embedded_images[0]
        assert image.filename.startswith("with_image__slide1__img1")
        assert f"[[IMAGE: {image.filename}]]" in result.text

    def test_odp_embedded_image_export_disabled_by_default(self, tmp_path: Path) -> None:
        f = _odp_with_image(tmp_path, "with_image2.odp", _red_square_png())

        result = OdfExtractor.extract(f, "with_image2.odp")
        assert result.embedded_images == []
        assert "[[IMAGE" not in result.text
