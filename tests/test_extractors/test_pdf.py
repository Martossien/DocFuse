"""Tests de l'extracteur PDF.

CdC §8.3 — Texte de chaque page, dans l'ordre des pages.
Page vide → [[PAGE N: aucun texte extractible]].
CdC §9.4 — Détection images via LTImage/LTFigure.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.extractors.pdf import PdfExtractor
from docfuse.models.file_status import FileStatus


class TestPdfExtractor:
    def test_extract_text_pdf(self, tmp_path: Path) -> None:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate

        f = tmp_path / "test.pdf"
        doc = SimpleDocTemplate(str(f), pagesize=A4)
        styles = getSampleStyleSheet()
        story = [
            Paragraph(
                "Ceci est un paragraphe PDF de test avec suffisamment de "
                "caracteres pour depasser le seuil de quatre-vingt.",
                styles["Normal"],
            ),
        ]
        doc.build(story)

        result = PdfExtractor.extract(f, "test.pdf")
        assert result.status is FileStatus.READY
        assert "Ceci est un paragraphe PDF" in result.text or "paragraphe" in result.text
        assert result.page_count >= 1

    def test_accepts(self) -> None:
        assert PdfExtractor.accepts(Path("test.pdf")) is True
        assert PdfExtractor.accepts(Path("test.docx")) is False

    def test_safe_extract_no_crash(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.pdf"
        result = PdfExtractor.safe_extract(f, "nonexistent.pdf")
        assert result.status is FileStatus.ERROR

    def test_corrupt_pdf_returns_error(self, tmp_path: Path) -> None:
        f = tmp_path / "corrupt.pdf"
        f.write_bytes(b"Not a real PDF file content")
        result = PdfExtractor.extract(f, "corrupt.pdf")
        assert result.status is FileStatus.ERROR

    def test_fixture_file(self) -> None:
        fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample.pdf"
        if fixture.exists():
            result = PdfExtractor.extract(fixture, "sample.pdf")
            assert result.status is FileStatus.READY
            assert "texte PDF" in result.text or "texte" in result.text.lower()
