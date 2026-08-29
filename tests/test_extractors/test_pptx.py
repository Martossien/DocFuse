"""Tests de l'extracteur PPTX.

CdC §8.3 — Texte des shapes, tableaux, notes d'orateur.
Diapo sans texte → [[DIAPO N: aucun texte extractible]].
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from docfuse.core.ocr.tesseract import TesseractEngine
from docfuse.extractors.pptx import PptxExtractor
from docfuse.models.file_status import FileStatus

_OCR_AVAILABLE = TesseractEngine().is_available()


def _pptx_with_image(tmp_path: Path, name: str, image_bytes: bytes) -> Path:
    from pptx import Presentation
    from pptx.util import Inches

    f = tmp_path / name
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(io.BytesIO(image_bytes), Inches(1), Inches(1), Inches(2), Inches(2))
    prs.save(str(f))
    return f


def _red_square_png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (50, 50), "red").save(buf, format="PNG")
    return buf.getvalue()


class TestPptxExtractor:
    def test_extract_basic_slide(self, tmp_path: Path) -> None:
        from pptx import Presentation

        f = tmp_path / "test.pptx"
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = "Titre Diapo"
        slide.placeholders[1].text = (
            "Contenu de la diapo avec suffisamment de texte "
            "pour depasser le seuil de quatre-vingt caracteres."
        )
        prs.save(str(f))

        result = PptxExtractor.extract(f, "test.pptx")
        assert result.status is FileStatus.READY
        assert "Titre Diapo" in result.text
        assert result.page_count == 1

    def test_empty_slide_marker(self, tmp_path: Path) -> None:
        from pptx import Presentation

        f = tmp_path / "empty.pptx"
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[5])  # Blank slide
        prs.save(str(f))

        result = PptxExtractor.extract(f, "empty.pptx")
        assert "[[DIAPO 1: aucun texte extractible]]" in result.text

    def test_accepts(self) -> None:
        assert PptxExtractor.accepts(Path("test.pptx")) is True
        assert PptxExtractor.accepts(Path("test.docx")) is False

    def test_safe_extract_no_crash(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.pptx"
        result = PptxExtractor.safe_extract(f, "nonexistent.pptx")
        assert result.status is FileStatus.ERROR

    def test_password_protected_gives_clear_error(self, tmp_path: Path) -> None:
        """D-089 : un .pptx protégé par mot de passe à l'ouverture (conteneur
        OLE2, plus un ZIP) donnait un `PackageNotFoundError` bas niveau,
        jamais un message disant à l'utilisateur que le fichier est protégé."""
        f = tmp_path / "protected.pptx"
        f.write_bytes(bytes((0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1)) + b"\x00" * 500)

        result = PptxExtractor.extract(f, "protected.pptx")
        assert result.status is FileStatus.ERROR
        assert result.error_message is not None
        assert "mot de passe" in result.error_message.lower()

    def test_fixture_file(self) -> None:
        fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample.pptx"
        if fixture.exists():
            result = PptxExtractor.extract(fixture, "sample.pptx")
            assert result.status is FileStatus.READY
            assert "Diapo" in result.text

    def test_grouped_shapes_text_is_extracted(self, tmp_path: Path) -> None:
        """D-074 : le texte dans une forme groupée (GroupShape — schémas,
        diagrammes annotés) ne doit pas disparaître. shape.has_text_frame
        renvoie False pour le conteneur groupe lui-même ; sans récursion
        dans shape.shapes, tout son contenu est invisible."""
        from pptx import Presentation
        from pptx.util import Inches

        f = tmp_path / "grouped.pptx"
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        tb1 = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
        tb1.text_frame.text = "TEXTE_DANS_GROUPE_1"
        tb2 = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(2), Inches(1))
        tb2.text_frame.text = "TEXTE_DANS_GROUPE_2"
        slide.shapes.add_group_shape([tb1, tb2])
        prs.save(str(f))

        result = PptxExtractor.extract(f, "grouped.pptx")
        assert result.status is FileStatus.READY
        assert "TEXTE_DANS_GROUPE_1" in result.text
        assert "TEXTE_DANS_GROUPE_2" in result.text

    def test_embedded_image_export_creates_embedded_images(self, tmp_path: Path) -> None:
        """D-091 : export actif -> l'image est capturée avec un nom explicite
        (incluant le numéro de diapo) et un tag `[[IMAGE: ...]]` est inséré
        au point d'apparition."""
        f = _pptx_with_image(tmp_path, "with_image.pptx", _red_square_png())

        result = PptxExtractor.extract(f, "with_image.pptx", extract_images=True)
        assert result.status is FileStatus.READY
        assert len(result.embedded_images) == 1
        image = result.embedded_images[0]
        assert image.filename.startswith("with_image__slide1__img1")
        assert image.data
        assert f"[[IMAGE: {image.filename}]]" in result.text

    def test_embedded_image_export_disabled_by_default(self, tmp_path: Path) -> None:
        """D-091 : sans `extract_images`, aucune image capturée, texte inchangé
        (non-régression stricte vis-à-vis du comportement pré-D-091)."""
        f = _pptx_with_image(tmp_path, "with_image2.pptx", _red_square_png())

        result = PptxExtractor.extract(f, "with_image2.pptx")
        assert result.embedded_images == []
        assert "[[IMAGE" not in result.text

    @pytest.mark.skipif(not _OCR_AVAILABLE, reason="Tesseract non installé")
    def test_embedded_image_ocr_extracts_text_automatically(self, tmp_path: Path) -> None:
        """D-091 : corrige le bug signalé par l'utilisateur (PPTX où le texte
        est dans une image) — OCR automatique, sans avoir besoin d'activer
        l'export."""
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (600, 150), "white")
        draw = ImageDraw.Draw(img)
        draw.text((10, 50), "Bonjour le monde", fill="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        f = _pptx_with_image(tmp_path, "with_text_image.pptx", buf.getvalue())

        result = PptxExtractor.extract(f, "with_text_image.pptx")
        assert "onjour" in result.text or "monde" in result.text
        assert result.embedded_images == []
