"""Tests de l'extracteur PDF.

CdC §8.3 — Texte de chaque page, dans l'ordre des pages.
Page vide → [[PAGE N: aucun texte extractible]].
CdC §9.4 — Détection images via LTImage/LTFigure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docfuse.core.ocr.tesseract import TesseractEngine
from docfuse.extractors.pdf import PageKind, PdfExtractor, classify_page
from docfuse.models.file_status import FileStatus

_OCR_AVAILABLE = TesseractEngine().is_available()


def _make_image_only_pdf(tmp_path: Path, lines: list[str]) -> Path:
    """Construit un PDF « scanné » : une image de texte, aucune couche texte."""
    from PIL import Image, ImageDraw
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    img = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(img)
    y = 100
    for line in lines:
        draw.text((80, y), line, fill="black")
        y += 60
    png_path = tmp_path / "_scan_source.png"
    img.save(png_path)

    pdf_path = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    w, h = A4
    c.drawImage(str(png_path), 0, 0, width=w, height=h)
    c.showPage()
    c.save()
    return pdf_path


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

    def test_text_nested_in_form_xobject_is_extracted(self, tmp_path: Path) -> None:
        """D-068 : du texte placé dans un Form XObject (LTFigure) — filigrane,
        tampon, contenu fusionné, courant avec TCPDF et d'autres générateurs —
        ne doit pas être silencieusement ignoré. Repro minimale d'un vrai bug
        trouvé en session sur un PDF réel (TCPDF), où jusqu'à ~2500
        caractères par page étaient perdus."""
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        f = tmp_path / "form_xobject.pdf"
        c = canvas.Canvas(str(f), pagesize=A4)
        c.beginForm("monform")
        c.setFont("Helvetica", 12)
        c.drawString(50, 700, "Texte imbrique dans un Form XObject de test.")
        c.drawString(50, 680, "Deuxieme ligne pour depasser le seuil de detection.")
        c.endForm()
        c.doForm("monform")
        c.showPage()
        c.save()

        result = PdfExtractor.extract(f, "form_xobject.pdf")
        assert result.status is FileStatus.READY
        assert "Texte imbrique dans un Form XObject" in result.text
        assert "Deuxieme ligne" in result.text
        assert "ocr" not in result.extra_metadata

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


class TestClassifyPage:
    """Classification par page (native/ocr/blank/mixed) — pure, sans Tesseract."""

    def test_enough_native_text_no_image_is_native(self) -> None:
        assert classify_page("x" * 200, 200, has_image=False) is PageKind.NATIVE

    def test_no_text_no_image_is_blank(self) -> None:
        assert classify_page("", 0, has_image=False) is PageKind.BLANK

    def test_no_text_with_image_is_ocr(self) -> None:
        assert classify_page("", 0, has_image=True) is PageKind.OCR

    def test_sparse_text_is_ocr(self) -> None:
        assert classify_page("court", 5, has_image=False) is PageKind.OCR

    def test_enough_text_with_image_is_mixed(self) -> None:
        assert classify_page("x" * 200, 200, has_image=True) is PageKind.MIXED

    def test_garbage_markers_force_ocr_even_with_many_chars(self) -> None:
        text = "(cid:12)" * 30
        assert classify_page(text, len(text), has_image=False) is PageKind.OCR


class TestPdfOcr:
    """OCR des PDF scannés — CorpusOne-OCR (moteur optionnel, jamais bloquant)."""

    def test_scan_without_engine_falls_back_to_unchanged_behavior(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sans moteur OCR disponible, comportement identique à avant la fonctionnalité."""
        import docfuse.extractors.pdf as pdf_module

        monkeypatch.setattr(pdf_module, "resolve_ocr_engine", lambda: None)

        pdf_path = _make_image_only_pdf(tmp_path, ["Texte scanne de test"])
        result = PdfExtractor.extract(pdf_path, "scan.pdf")

        assert "[[PAGE 1: aucun texte extractible]]" in result.text
        assert "ocr" in result.extra_metadata
        assert "pas disponible" in result.extra_metadata["ocr"]

    def test_garbage_text_cleaned_when_ocr_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D-086 : sans moteur OCR, le texte natif "poubelle" (glyphes non
        mappés, `(cid:...)`) qui a déclenché la classification OCR ne doit
        pas rester tel quel dans le corpus — ça pollue le texte de bruit
        inutilisable. Une page classée `ocr` pour texte simplement trop
        court (mais réel) doit, elle, rester inchangée."""
        import docfuse.extractors.pdf as pdf_module

        monkeypatch.setattr(pdf_module, "resolve_ocr_engine", lambda: None)

        garbage_page = "(cid:12)(cid:12)(cid:12)" * 10
        short_real_page = "court"
        pages = [garbage_page, short_real_page]
        chars = [len(p) for p in pages]
        images = [0, 0]

        new_pages, note = pdf_module._apply_ocr(Path("/fake.pdf"), pages, chars, images)

        assert new_pages[0] == ""
        assert new_pages[1] == short_real_page
        assert note is not None
        assert "pas disponible" in note

    @pytest.mark.skipif(not _OCR_AVAILABLE, reason="Tesseract non installé")
    def test_scan_with_engine_recovers_text(self, tmp_path: Path) -> None:
        pdf_path = _make_image_only_pdf(
            tmp_path,
            [
                "Ceci est un document scanne de test.",
                "Il ne contient aucune couche de texte native.",
                "Ligne supplementaire pour depasser le seuil de caracteres.",
            ],
        )
        result = PdfExtractor.extract(pdf_path, "scan.pdf")

        assert "texte OCR" in result.text
        assert "scanne" in result.text or "document" in result.text
        assert "ocr" in result.extra_metadata
        assert "reconnue" in result.extra_metadata["ocr"]

    def test_ocr_pages_holds_pdfium_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D-078 : PDFium (pypdfium2) n'est pas thread-safe entre PdfDocument
        distincts chargés depuis des threads différents — vérifié en
        conditions réelles : un dossier avec plusieurs PDF nécessitant l'OCR
        traités en parallèle (ThreadPoolExecutor de l'orchestrateur)
        provoquait une corruption de tas native puis un SIGSEGV qui tuait
        tout le processus. `_ocr_pages` doit tenir `_PDFIUM_LOCK` pendant
        tout accès à PDFium — vérifié ici en observant l'état du verrou
        depuis l'intérieur d'un `PdfDocument` factice, plutôt que de
        dépendre d'une vraie course native (non déterministe en test)."""
        import docfuse.extractors.pdf as pdf_module
        from docfuse.core.ocr.tesseract import TesseractEngine

        lock_was_held: list[bool] = []

        class _FakePdfDocument:
            def __init__(self, path: str) -> None:  # noqa: ARG002
                lock_was_held.append(pdf_module._PDFIUM_LOCK.locked())

            def close(self) -> None:
                pass

            def __getitem__(self, idx: int) -> None:
                raise AssertionError("pas besoin d'aller plus loin pour ce test")

        fake_pdfium = type("FakeModule", (), {"PdfDocument": _FakePdfDocument})
        monkeypatch.setitem(__import__("sys").modules, "pypdfium2", fake_pdfium)

        pdf_module._ocr_pages(tmp_path / "x.pdf", [0], "fra", TesseractEngine())

        assert lock_was_held == [True]
        assert not pdf_module._PDFIUM_LOCK.locked()  # relâché après l'appel

    @pytest.mark.skipif(not _OCR_AVAILABLE, reason="Tesseract non installé")
    def test_native_pdf_is_not_touched_by_ocr(self, tmp_path: Path) -> None:
        """Un PDF avec du texte natif suffisant ne déclenche jamais l'OCR."""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate

        f = tmp_path / "native.pdf"
        doc = SimpleDocTemplate(str(f), pagesize=A4)
        styles = getSampleStyleSheet()
        doc.build(
            [
                Paragraph(
                    "Paragraphe natif avec largement assez de caracteres pour "
                    "ne jamais etre classe comme une page a OCRiser ici.",
                    styles["Normal"],
                )
            ]
        )

        result = PdfExtractor.extract(f, "native.pdf")
        assert "ocr" not in result.extra_metadata
        assert "texte OCR" not in result.text
