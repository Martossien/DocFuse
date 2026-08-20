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
