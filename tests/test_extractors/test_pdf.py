"""Tests de l'extracteur PDF.

CdC §8.3 — Texte de chaque page, dans l'ordre des pages.
Page vide → [[PAGE N: aucun texte extractible]].
CdC §9.4 — Détection images via LTImage/LTFigure.
"""

from __future__ import annotations

import math
import time
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


def _raw_pdf(objects: list[tuple[int, bytes]], root: int = 1) -> bytes:
    """Assemble un PDF minimal (table xref classique) à partir d'objets bruts.

    Nécessaire pour D-107 : aucune bibliothèque de génération (reportlab…) ne
    produit un arbre `/Pages` qui référence deux fois le même objet page —
    c'est justement la structure à reproduire.
    """
    import io

    out = io.BytesIO()
    out.write(b"%PDF-1.7\n")
    offsets: dict[int, int] = {}
    for num, body in objects:
        offsets[num] = out.tell()
        out.write(f"{num} 0 obj\n".encode())
        out.write(body)
        out.write(b"\nendobj\n")
    xref_offset = out.tell()
    size = max(offsets) + 1
    out.write(f"xref\n0 {size}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for i in range(1, size):
        out.write(f"{offsets.get(i, 0):010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {size} /Root {root} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return out.getvalue()


def _make_duplicate_kids_pdf(tmp_path: Path) -> Path:
    """PDF de 4 pages dont l'arbre `/Pages` référence DEUX FOIS l'objet de la
    page A — cas courant d'un PDF fusionné qui réutilise un objet page.

    pdfminer déduplique son parcours de l'arbre (`visited`, `pdfpage.py`) et
    n'en voit donc que 3 ; pypdf et PDFium en voient 4. Les trois pages vues
    par pdfminer portent volontairement des contenus très différents (dont un
    « dossier médical » et des « salaires ») : si les indices de page se
    décalent, le décalage est visible dans le texte produit.
    """

    def _page(num: int, text: str) -> list[tuple[int, bytes]]:
        content = f"BT /F1 24 Tf 50 700 Td ({text}) Tj ET".encode()
        return [
            (
                num,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources "
                b"<< /Font << /F1 99 0 R >> >> /Contents %d 0 R >>" % (num + 50),
            ),
            (num + 50, b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"),
        ]

    objects: list[tuple[int, bytes]] = [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, b"<< /Type /Pages /Kids [3 0 R 4 0 R 3 0 R 5 0 R] /Count 4 >>"),
        (99, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
    ]
    objects += _page(3, "PAGE A - dossier medical patient DUPONT")
    objects += _page(4, "PAGE B - note de service anodine")
    objects += _page(5, "PAGE C - salaires nominatifs")

    pdf_path = tmp_path / "dup_kids.pdf"
    pdf_path.write_bytes(_raw_pdf(objects))
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

            # D-107 : `_ocr_pages` vérifie désormais que PDFium compte le même
            # nombre de pages que l'appelant avant de rendre quoi que ce soit ;
            # le faux document doit donc répondre à `len()`, sinon le test ne
            # traverse plus le code qu'il prétend vérifier.
            def __len__(self) -> int:
                return 1

            def __getitem__(self, idx: int) -> None:
                raise AssertionError("pas besoin d'aller plus loin pour ce test")

        fake_pdfium = type("FakeModule", (), {"PdfDocument": _FakePdfDocument})
        monkeypatch.setitem(__import__("sys").modules, "pypdfium2", fake_pdfium)

        pdf_module._ocr_pages(tmp_path / "x.pdf", [0], "fra", TesseractEngine(), 1)

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


class TestOcrLockScopeAndMemory:
    """D-108 — étendue du verrou PDFium et pic mémoire de la rastérisation.

    Mesures sur un PDF scanné de 200 pages A4 à 200 dpi, moteur OCR factice
    instantané (la question porte sur la rastérisation, pas sur Tesseract) :

    * avant : RSS 16 Mo → **2 023 Mo**, verrou détenu **95,7 s / 96,2 s (99 %)** ;
    * après : RSS 16 Mo → **96 Mo**, verrou détenu **21,0 s / 101,8 s (21 %)**.

    Et sur 4 fichiers de 20 pages OCRisés en parallèle (Tesseract réel) :
    55,9 s / 1,43 page/s / pic RSS 1 411 Mo → 48,1 s / 1,66 page/s / 627 Mo.
    """

    @staticmethod
    def _fake_pdfium(lock_state_at: dict[str, list[bool]], pages: int) -> object:
        """Faux module `pypdfium2` qui note si `_PDFIUM_LOCK` est tenu à
        chaque étape (rendu / encodage PNG)."""
        import docfuse.extractors.pdf as pdf_module

        class _FakeImage:
            def copy(self) -> _FakeImage:
                return self

            def save(self, buf: object, format: str) -> None:  # noqa: A002, ARG002
                lock_state_at["png"].append(pdf_module._PDFIUM_LOCK.locked())
                buf.write(b"\x89PNG-factice")  # type: ignore[attr-defined]

        class _FakeBitmap:
            def to_pil(self) -> _FakeImage:
                return _FakeImage()

            def close(self) -> None:
                pass

        class _FakePage:
            def get_size(self) -> tuple[float, float]:
                return (595.0, 842.0)

            def render(self, scale: float) -> _FakeBitmap:  # noqa: ARG002
                lock_state_at["render"].append(pdf_module._PDFIUM_LOCK.locked())
                return _FakeBitmap()

        class _FakePdfDocument:
            def __init__(self, path: str) -> None:  # noqa: ARG002
                lock_state_at["open"].append(pdf_module._PDFIUM_LOCK.locked())

            def __len__(self) -> int:
                return pages

            def __getitem__(self, idx: int) -> _FakePage:  # noqa: ARG002
                return _FakePage()

            def close(self) -> None:
                pass

        return type("FakeModule", (), {"PdfDocument": _FakePdfDocument})

    def test_png_encoding_runs_outside_the_pdfium_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L'encodage PNG n'appelle jamais PDFium ; le garder sous le verrou
        plafonnait le débit OCR de tout le processus (~83 % du temps tenu
        pour rien). Le rendu, lui, doit rester protégé (D-078)."""
        import docfuse.extractors.pdf as pdf_module

        states: dict[str, list[bool]] = {"open": [], "render": [], "png": []}
        monkeypatch.setitem(__import__("sys").modules, "pypdfium2", self._fake_pdfium(states, 3))

        def _instant_ocr(engine: object, png: bytes, lang: str) -> str:  # noqa: ARG001
            return "texte"

        monkeypatch.setattr(pdf_module, "ocr_with_slot", _instant_ocr)

        results = pdf_module._ocr_pages(tmp_path / "x.pdf", [0, 1, 2], "fra", TesseractEngine(), 3)

        assert states["open"] == [True, True, True], "ouverture PDFium hors verrou (D-078)"
        assert states["render"] == [True, True, True], "rendu PDFium hors verrou (D-078)"
        assert states["png"] == [False, False, False], "encodage PNG encore sous verrou (D-108)"
        assert not pdf_module._PDFIUM_LOCK.locked()
        assert all(ok for _, ok in results.values())

    def test_rendered_pngs_are_not_all_kept_in_memory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Avant : `pngs: dict[int, bytes]` gardait le PDF entier rendu en
        mémoire jusqu'à la fin de l'OCR (2 Go pour 200 pages). Le rendu doit
        maintenant se bloquer dès que les PNG déjà produits saturent la file
        de l'OCR, quelle que soit la lenteur de celui-ci.

        Borne seulement majorée : le test ne dépend pas de la vitesse relative
        des threads, seulement du sémaphore `in_flight`.
        """
        import threading

        import docfuse.extractors.pdf as pdf_module
        from docfuse.constants import OCR_MAX_CONCURRENCY

        total_pages = 60
        rendered = []
        rendered_lock = threading.Lock()
        release = threading.Event()

        def _fake_render(path: Path, idx: int, expected: int) -> object:  # noqa: ARG001
            with rendered_lock:
                rendered.append(idx)

            class _Img:
                def save(self, buf: object, format: str) -> None:  # noqa: A002, ARG002
                    buf.write(b"png")  # type: ignore[attr-defined]

            return _Img()

        def _blocking_ocr(engine: object, png: bytes, lang: str) -> str:  # noqa: ARG001
            release.wait(timeout=30)
            return "texte"

        monkeypatch.setattr(pdf_module, "_render_page_image", _fake_render)
        monkeypatch.setattr(pdf_module, "ocr_with_slot", _blocking_ocr)

        done = threading.Event()

        def _run() -> None:
            pdf_module._ocr_pages(
                tmp_path / "x.pdf",
                list(range(total_pages)),
                "fra",
                TesseractEngine(),
                total_pages,
            )
            done.set()

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        # Laisse largement le temps au rendu de s'emballer s'il le peut.
        time.sleep(1.0)
        with rendered_lock:
            rendered_while_blocked = len(rendered)
        release.set()
        assert done.wait(timeout=30), "_ocr_pages ne se termine pas"
        worker.join(timeout=5)

        workers = min(OCR_MAX_CONCURRENCY, total_pages)
        # workers + 2 PNG autorisés en vol, + 1 page rendue et bloquée sur
        # `in_flight.acquire()`.
        assert rendered_while_blocked <= workers + 3
        assert rendered_while_blocked < total_pages
        assert len(rendered) == total_pages, "toutes les pages doivent finir par être rendues"


class TestPdfPageDesync:
    """D-107 — CRITIQUE : le texte OCR d'une page attribué à une AUTRE page.

    Les indices de page viennent de pdfminer (qui déduplique son parcours de
    l'arbre `/Pages`), le rendu OCR de PDFium (qui ne déduplique pas). Quand
    les deux ne comptent pas le même nombre de pages, `new_pages[idx] = ...`
    écrit le texte reconnu sur une page qui n'est pas la bonne — et comme le
    genre est `OCR`, le texte natif réel est écrasé, pas concaténé.
    """

    def test_pdfminer_and_pypdf_disagree_on_duplicate_kids(self, tmp_path: Path) -> None:
        """Le désaccord existe bel et bien : c'est le socle du test suivant.

        Si un jour pdfminer cesse de dédupliquer, ce test tombe et signale que le
        scénario a changé.

        Le désaccord prend **deux formes** selon la version de pypdf, et les deux
        content ce test : pypdf 6.16.2 compte 4 pages là où pdfminer en voit 3 ;
        pypdf 6.16.1 refuse carrément l'arbre (« Detected cyclic page references »).
        Exiger la première forme faisait échouer la suite sur l'autre version — et
        le refus est, si l'on y tient, un désaccord plus franc encore. Ce qui doit
        rester vrai, c'est que les deux bibliothèques ne voient pas la même chose ;
        c'est le test suivant qui vérifie ce que DocFuse en fait.
        """
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        from docfuse.extractors.pdf import _extract_pages_pdfminer

        pdf_path = _make_duplicate_kids_pdf(tmp_path)
        _, _, pdfminer_pages, _ = _extract_pages_pdfminer(pdf_path)
        try:
            with pdf_path.open("rb") as fh:
                pypdf_pages: int | None = len(PdfReader(fh).pages)
        except PdfReadError:
            pypdf_pages = None  # l'arbre de pages est refusé : désaccord, en plus net

        assert pdfminer_pages == 3
        assert pypdf_pages != 3, "sans désaccord, le scénario du test suivant n'existe plus"

    def test_page_desync_is_refused_instead_of_misattributing_text(self, tmp_path: Path) -> None:
        """Avant D-107 : statut `ready`, `page_count = 3` pour un PDF de
        4 pages, la page 3 portant le texte OCR de la page 1 (« dossier
        medical ») tandis que « salaires nominatifs » disparaissait du corpus.
        Aucun avertissement.

        Après : refus explicite, et le nombre de pages annoncé est celui du
        vrai PDF.
        """
        pdf_path = _make_duplicate_kids_pdf(tmp_path)
        result = PdfExtractor.safe_extract(pdf_path, "dup_kids.pdf")

        assert result.status is FileStatus.ERROR
        assert result.page_count == 4, "page_count doit décrire le PDF réel, pas la vue pdfminer"
        assert result.error_message is not None
        assert "3" in result.error_message
        assert "4" in result.error_message
        # Aucun contenu ne peut être attribué à la mauvaise page : il n'y a
        # pas de contenu du tout, et le fichier est signalé pour examen.
        assert "dossier medical" not in result.text
        assert result.text == ""

    def test_ocr_pages_refuses_when_pdfium_disagrees(self, tmp_path: Path) -> None:
        """Deuxième garde, au point exact où les deux bibliothèques se
        croisent : même si pypdf était illisible (ou d'accord à tort),
        `_ocr_pages` ne rend aucune page tant que PDFium ne compte pas comme
        l'appelant. Pas besoin de Tesseract : le refus précède le rendu.
        """
        from docfuse.extractors.pdf import PdfPageCountMismatchError, _ocr_pages

        pdf_path = _make_duplicate_kids_pdf(tmp_path)
        with pytest.raises(PdfPageCountMismatchError) as excinfo:
            _ocr_pages(pdf_path, [0, 1, 2], "fra+eng", TesseractEngine(), 3)

        assert excinfo.value.expected_pages == 3
        assert excinfo.value.observed_pages == 4

    def test_agreeing_pdf_is_not_refused(self, tmp_path: Path) -> None:
        """Non-régression : un PDF normal (les deux bibliothèques d'accord)
        passe exactement comme avant."""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

        f = tmp_path / "normal.pdf"
        doc = SimpleDocTemplate(str(f), pagesize=A4)
        styles = getSampleStyleSheet()
        doc.build(
            [
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
        )

        result = PdfExtractor.extract(f, "normal.pdf")
        assert result.status is FileStatus.READY
        assert result.page_count == 2


class TestOcrRenderScale:
    """D-105 : une page hors plafond mémoire n'est plus abandonnée
    (« trop grande pour l'OCR, ignorée ») mais rendue à l'échelle réduite."""

    def test_normal_page_keeps_nominal_dpi(self) -> None:
        from docfuse.constants import OCR_DPI
        from docfuse.extractors.pdf import _ocr_render_scale

        assert _ocr_render_scale(595, 842) == pytest.approx(OCR_DPI / 72)  # A4

    def test_oversized_page_is_scaled_down_not_dropped(self) -> None:
        from docfuse.constants import OCR_MAX_PIXELS_PER_PAGE, OCR_MIN_DPI
        from docfuse.extractors.pdf import _ocr_render_scale

        width, height = 3370.0, 2384.0  # A0 paysage, ~62 Mpx à 200 dpi
        scale = _ocr_render_scale(width, height)
        assert scale is not None
        assert (width * scale) * (height * scale) <= OCR_MAX_PIXELS_PER_PAGE
        assert scale * 72 >= OCR_MIN_DPI

    def test_scaled_page_uses_the_whole_budget(self) -> None:
        """L'échelle réduite est la plus grande qui tienne — pas de perte de
        lisibilité gratuite."""
        from docfuse.constants import OCR_MAX_PIXELS_PER_PAGE
        from docfuse.extractors.pdf import _ocr_render_scale

        scale = _ocr_render_scale(2000.0, 2000.0)
        assert scale is not None
        assert (2000.0 * scale) ** 2 == pytest.approx(OCR_MAX_PIXELS_PER_PAGE)

    def test_page_below_readability_floor_is_still_skipped(self) -> None:
        """Le garde-fou mémoire (D-096) reste : sous ~100 dpi le résultat
        serait illisible, la page est ignorée comme avant."""
        from docfuse.extractors.pdf import _ocr_render_scale

        assert _ocr_render_scale(20000.0, 20000.0) is None

    def test_degenerate_size_is_skipped(self) -> None:
        from docfuse.extractors.pdf import _ocr_render_scale

        assert _ocr_render_scale(0.0, 800.0) is None


class TestOcrRenderScaleBounds:
    """D-106 : bornes dégénérées et portée réelle du sauvetage D-105."""

    def test_negative_dimensions_are_rejected(self) -> None:
        """`(-595, -842)` donne une aire **positive** : la garde `area <= 0`
        laissait passer la page à l'échelle nominale, dimensions négatives
        transmises telles quelles à `page.render()`."""
        from docfuse.extractors.pdf import _ocr_render_scale

        assert _ocr_render_scale(-595.0, -842.0) is None
        assert _ocr_render_scale(-595.0, 842.0) is None
        assert _ocr_render_scale(595.0, -842.0) is None

    def test_nan_dimensions_are_rejected(self) -> None:
        """`NaN` est faux dans toutes les comparaisons : il traversait la
        fonction entière et ressortait en `NaN` vers `page.render(scale=NaN)`."""
        from docfuse.extractors.pdf import _ocr_render_scale

        assert _ocr_render_scale(math.nan, 842.0) is None
        assert _ocr_render_scale(595.0, math.nan) is None
        assert _ocr_render_scale(math.nan, math.nan) is None

    def test_infinite_dimensions_are_rejected(self) -> None:
        from docfuse.extractors.pdf import _ocr_render_scale

        assert _ocr_render_scale(math.inf, 842.0) is None

    def test_documented_formats_match_the_docstring(self) -> None:
        """Les chiffres annoncés par la docstring (et par `OCR_MIN_DPI`) sont
        ceux que la fonction produit réellement — un A0 sort à 101,6 dpi, pas
        à « 120 dpi »."""
        from docfuse.extractors.pdf import _ocr_render_scale

        a0 = _ocr_render_scale(2384.0, 3370.0)
        assert a0 is not None
        assert a0 * 72 == pytest.approx(101.6, abs=0.1)

        ansi_e = _ocr_render_scale(34 * 72, 44 * 72)
        assert ansi_e is not None
        assert ansi_e * 72 == pytest.approx(103.4, abs=0.1)

        # ARCH E (96,2 dpi) et B0 tombent sous le plancher : ignorés.
        assert _ocr_render_scale(36 * 72, 48 * 72) is None
        assert _ocr_render_scale(2835.0, 4008.0) is None

    @pytest.mark.skipif(not _OCR_AVAILABLE, reason="Tesseract non installé")
    def test_giant_scanned_page_is_ocred_not_ignored(self, tmp_path: Path) -> None:
        """Bout en bout : une page géante (hors plafond à 200 dpi) doit sortir
        du texte, là où l'ancien `continue` la perdait entièrement."""
        from PIL import Image, ImageDraw
        from reportlab.pdfgen import canvas

        from docfuse.constants import OCR_DPI, OCR_MAX_PIXELS_PER_PAGE
        from docfuse.extractors.pdf import _ocr_pages

        width = height = 2000.0  # ~31 Mpx à 200 dpi, au-dessus du plafond
        assert (width * OCR_DPI / 72) * (height * OCR_DPI / 72) > OCR_MAX_PIXELS_PER_PAGE

        img = Image.new("RGB", (2000, 2000), "white")
        draw = ImageDraw.Draw(img)
        draw.text((100, 900), "FACTURE 4711", fill="black")
        big = img.resize((4000, 4000), Image.LANCZOS)
        png_path = tmp_path / "_giant.png"
        big.save(png_path)

        pdf_path = tmp_path / "giant.pdf"
        c = canvas.Canvas(str(pdf_path), pagesize=(width, height))
        c.drawImage(str(png_path), 0, 0, width=width, height=height)
        c.showPage()
        c.save()

        # D-107 : dernier argument = nombre de pages attendu (le PDF en a 1).
        results = _ocr_pages(pdf_path, [0], "fra+eng", TesseractEngine(), 1)
        text, ok = results[0]
        assert ok is True, f"page géante toujours ignorée : {results}"
        assert "4711" in text
