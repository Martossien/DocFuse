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

    def test_dedupe_repeated_footer(self, tmp_path: Path) -> None:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate

        f = tmp_path / "multi_page.pdf"
        doc = SimpleDocTemplate(str(f), pagesize=A4)

        def _footer(canvas: object, _doc: object) -> None:
            canvas.saveState()  # type: ignore[attr-defined]
            canvas.drawString(50, 30, "CONFIDENTIEL - Usage interne uniquement")  # type: ignore[attr-defined]
            canvas.restoreState()  # type: ignore[attr-defined]

        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import PageBreak, Paragraph

        styles = getSampleStyleSheet()
        story: list[object] = []
        for i in range(6):
            story.append(
                Paragraph(
                    f"Contenu unique de la page {i} avec suffisamment de texte pour "
                    "depasser le seuil de detection de pauvrete de contenu ici.",
                    styles["Normal"],
                )
            )
            story.append(PageBreak())

        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)

        result = PdfExtractor.extract(f, "multi_page.pdf")
        assert result.status is FileStatus.READY
        assert result.page_count >= 6
        occurrences = result.text.count("CONFIDENTIEL - Usage interne uniquement")
        assert occurrences == 1
        assert "pdf_dedup" in result.extra_metadata

    def test_no_dedupe_on_few_pages(self, tmp_path: Path) -> None:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate

        f = tmp_path / "two_pages.pdf"
        doc = SimpleDocTemplate(str(f), pagesize=A4)
        styles = getSampleStyleSheet()

        def _footer(canvas: object, _doc: object) -> None:
            canvas.saveState()  # type: ignore[attr-defined]
            canvas.drawString(50, 30, "Pied de page repete")  # type: ignore[attr-defined]
            canvas.restoreState()  # type: ignore[attr-defined]

        from reportlab.platypus import PageBreak

        story: list[object] = [
            Paragraph(
                "Premiere page avec un texte suffisamment long pour le seuil requis.",
                styles["Normal"],
            ),
            PageBreak(),
            Paragraph(
                "Deuxieme page avec un texte suffisamment long pour le seuil requis.",
                styles["Normal"],
            ),
        ]
        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)

        result = PdfExtractor.extract(f, "two_pages.pdf")
        assert "pdf_dedup" not in result.extra_metadata
        assert result.text.count("Pied de page repete") == 2
