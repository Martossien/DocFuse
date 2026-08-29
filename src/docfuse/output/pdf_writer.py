"""Writer PDF : génère un PDF texte avec ReportLab.

CdC §8.4, §11.2 — PDF :
- PDF texte généré (pas un merge des PDF sources).
- Police Unicode embarquée (DejaVu Sans, licence SIL/OFL).
- En-tête de page : nom du corpus, fichier source courant et sa position
  (D-100), n° de page.
- Saut de page entre sources.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from docfuse.constants import PDF_PAGE_HEADER_MAX_CHARS
from docfuse.core.orchestrator import OrchestratorResult
from docfuse.i18n import t
from docfuse.output.source_header import build_source_header

logger = logging.getLogger(__name__)

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def _escape(text: str) -> str:
    """Échappe une ligne pour le mini-langage XML de `reportlab.Paragraph`."""
    return escape(text)


def _register_fonts() -> tuple[str, str]:
    """Enregistre les polices DejaVu Sans (Unicode complet) dans ReportLab.

    CdC §8.4 — Police Unicode embarquée (DejaVu/Noto, licence SIL/OFL).
    Pas de dépendance à Arial ou aux polices Windows.

    Returns:
        Tuple (nom police normale, nom police gras).
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    normal_path = _ASSETS_DIR / "DejaVuSans.ttf"
    bold_path = _ASSETS_DIR / "DejaVuSans-Bold.ttf"

    if normal_path.exists():
        pdfmetrics.registerFont(TTFont("DejaVuSans", str(normal_path)))
    if bold_path.exists():
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold_path)))

    normal = "DejaVuSans" if normal_path.exists() else "Helvetica"
    bold = "DejaVuSans-Bold" if bold_path.exists() else "Helvetica-Bold"
    return normal, bold


def source_position_label(relative_path: str, index: int, total: int) -> str:
    """Libellé « fichier (i/N) » inscrit en en-tête de chaque page (D-100).

    Un chemin relatif trop long est raccourci par la gauche : c'est le nom
    du fichier, à droite, qui identifie la source.
    """
    label = relative_path
    if len(label) > PDF_PAGE_HEADER_MAX_CHARS:
        label = "…" + label[-(PDF_PAGE_HEADER_MAX_CHARS - 1) :]
    return t("corpus.source_position", file=label, index=index, total=total)


class _SourceMarker(Flowable):  # type: ignore[misc]
    """Flowable invisible posé avant l'en-tête de chaque fichier source :
    signale au gabarit de document quel fichier occupe la page (D-100)."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label

    def wrap(self, _available_width: float, _available_height: float) -> tuple[float, float]:
        return 0.0, 0.0

    def draw(self) -> None:
        return None


class _CorpusDocTemplate(SimpleDocTemplate):  # type: ignore[misc]
    """Gabarit A4 dont l'en-tête de page porte le fichier source courant.

    D-100 : les assistants qui indexent un PDF le découpent page par page ;
    chaque page doit donc dire d'elle-même de quel fichier elle provient.
    Comme chaque source commence sur une nouvelle page, une page ne
    contient jamais qu'un seul fichier — le dernier marqueur rencontré est
    le bon. L'en-tête est dessiné en fin de page (`afterPage`), une fois le
    marqueur de la page traité.
    """

    def __init__(self, filename: str, font_name: str, **kwargs: Any) -> None:
        super().__init__(filename, **kwargs)
        self._font_name = font_name
        self._current_source = ""

    def afterFlowable(self, flowable: Any) -> None:  # noqa: N802 — nom imposé par ReportLab
        if isinstance(flowable, _SourceMarker):
            self._current_source = flowable.label

    def afterPage(self) -> None:  # noqa: N802 — nom imposé par ReportLab
        canvas = self.canv
        canvas.saveState()
        canvas.setFont(self._font_name, 8)
        left = t("corpus.title")
        if self._current_source:
            left = f"{left} — {self._current_source}"
        canvas.drawString(20 * mm, A4[1] - 12 * mm, left)
        canvas.drawRightString(
            A4[0] - 20 * mm, A4[1] - 12 * mm, t("corpus.page", num=canvas.getPageNumber())
        )
        canvas.restoreState()


def write_pdf_corpus(
    result: OrchestratorResult,
    output_path: Path,
    margin: float = 0.15,
) -> None:
    """Écrit le corpus en PDF texte généré.

    Args:
        result: Résultat de l'orchestration.
        output_path: Chemin du fichier .pdf à écrire.
        margin: Marge appliquée.
    """
    font_normal, font_bold = _register_fonts()

    doc = _CorpusDocTemplate(
        str(output_path),
        font_normal,
        pagesize=A4,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        title=t("corpus.title"),
        author="DocFuse / CorpusOne",
    )

    body_style = ParagraphStyle(
        name="Body",
        fontName=font_normal,
        fontSize=9,
        leading=12,
        spaceAfter=6,
    )
    header_style = ParagraphStyle(
        name="SourceHeader",
        fontName=font_bold,
        fontSize=9,
        leading=12,
        spaceAfter=4,
        textColor="#333333",
    )

    included = [
        (f, est)
        for f, est in zip(result.files, result.estimates, strict=True)
        if f.status.is_extracted()
    ]
    story: list[object] = []

    for index, (f, est) in enumerate(included, 1):
        story.append(_SourceMarker(source_position_label(f.relative_path, index, len(included))))

        header = build_source_header(f, margin, est.tokens_estimated, est.tokens_with_margin)
        # D-096 : l'en-tête SOURCE passait à `Paragraph` sans échappement
        # (seul le corps l'était) — un nom de fichier ou une note contenant
        # `<`/`>`/`&` (ex. `a<b>.txt`, titre EPUB `<Untitled>`) faisait
        # échouer toute la génération PDF (`Parse error` ReportLab).
        for line in header.split("\n"):
            if line.strip():
                story.append(Paragraph(_escape(line), header_style))
        story.append(Spacer(1, 6))

        for paragraph in f.text.split("\n"):
            if paragraph.strip():
                story.append(Paragraph(_escape(paragraph), body_style))

        story.append(PageBreak())

    doc.build(story)
    logger.info("PDF généré : %s", output_path)
