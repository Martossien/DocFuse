"""Tests de l'extracteur PPTX.

CdC §8.3 — Texte des shapes, tableaux, notes d'orateur.
Diapo sans texte → [[DIAPO N: aucun texte extractible]].
"""

from __future__ import annotations

from pathlib import Path

from docfuse.extractors.pptx import PptxExtractor
from docfuse.models.file_status import FileStatus


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
