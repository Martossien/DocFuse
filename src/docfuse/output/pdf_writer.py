"""Writer PDF : génère un PDF texte avec ReportLab.

CdC §8.4, §11.2 — PDF :
- PDF texte généré (pas un merge des PDF sources).
- Police Unicode embarquée (DejaVu Sans, licence SIL/OFL).
- En-tête de page : nom du corpus + n° de page.
- Saut de page entre sources si possible.
"""

from __future__ import annotations

import logging
from pathlib import Path
from xml.sax.saxutils import escape

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
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    font_normal, font_bold = _register_fonts()

    doc = SimpleDocTemplate(
        str(output_path),
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

    story: list[object] = []

    for f, est in zip(result.files, result.estimates, strict=True):
        if not f.status.is_extracted():
            continue

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

    # CdC §11.2 — En-tête de page : nom du corpus + n° de page
    def _on_page(canvas: object, _doc: object) -> None:
        canvas.saveState()  # type: ignore[attr-defined]
        canvas.setFont(font_normal, 8)  # type: ignore[attr-defined]
        canvas.drawString(  # type: ignore[attr-defined]
            20 * mm,
            A4[1] - 12 * mm,
            t("corpus.title"),
        )
        page_num = canvas.getPageNumber()  # type: ignore[attr-defined]
        canvas.drawRightString(  # type: ignore[attr-defined]
            A4[0] - 20 * mm,
            A4[1] - 12 * mm,
            t("corpus.page", num=page_num),
        )
        canvas.restoreState()  # type: ignore[attr-defined]

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    logger.info("PDF généré : %s", output_path)
