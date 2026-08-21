"""Writer Markdown : assemble le corpus en un fichier .md unique.

CdC §11.1 — Markdown (défaut, recommandé IA) :
- UTF-8, LF ou CRLF (conf, défaut CRLF sous Windows).
- Structure : titre du corpus, date, plafond, puis blocs SOURCE.
- Pas de binaire encodé en base64.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from docfuse import __version__
from docfuse.core.orchestrator import OrchestratorResult
from docfuse.i18n import format_number, t
from docfuse.output.source_header import adaptive_backticks, build_source_header


def write_markdown_corpus(
    result: OrchestratorResult,
    output_path: Path,
    margin: float = 0.15,
    line_ending: str | None = None,
) -> None:
    """Écrit le corpus Markdown.

    Args:
        result: Résultat de l'orchestration.
        output_path: Chemin du fichier .md à écrire.
        margin: Marge appliquée (pour les en-têtes).
        line_ending: "lf" ou "crlf". Si None, auto-détecté (CRLF sous Windows).
    """
    # I-06: CRLF par défaut sous Windows (CdC §11.1)
    if line_ending is None:
        import sys

        line_ending = "crlf" if sys.platform == "win32" else "lf"
    lines: list[str] = []

    # En-tête du corpus
    lines.append(f"# {t('corpus.title')}")
    lines.append("")
    lines.append(f"- **{t('corpus.generated')}** : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **{t('corpus.version_label')}** : {__version__}")
    lines.append(
        f"- **{t('report.context_limit')}** : {format_number(result.context_limit)} tokens"
    )
    lines.append(f"- **{t('report.margin')}** : +{margin * 100:.0f} %")
    lines.append(f"- **{t('report.tokenizer_engine')}** : {t(f'tokenizer.{result.engine_id}')}")
    lines.append(
        f"- **{t('report.total_estimated')}** : {format_number(result.total.tokens_estimated)}"
    )
    lines.append(
        f"- **{t('report.total_with_margin')}** : {format_number(result.total.tokens_with_margin)}"
    )
    lines.append(f"- **{t('corpus.files')}** : {len(result.files)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Blocs SOURCE pour chaque fichier extrait
    for f, est in zip(result.files, result.estimates, strict=False):
        if not f.status.is_extracted():
            continue

        header = build_source_header(f, margin, est.tokens_estimated, est.tokens_with_margin)
        lines.append(header)
        lines.append("")

        # BUG FIX: Les fichiers Markdown (.md, .markdown) sont inclus "tel quel"
        # (CdC §7.3) — pas d'encapsulation dans des backticks.
        # Pour les autres formats qui contiennent des ``` dans leur texte,
        # on utilise des backticks adaptatifs (inspiré de files-to-prompt).
        if f.file_type in ("markdown", "text", "csv_tsv", "xml_json", "eml", "mhtml"):
            lines.append(f.text)
        elif "```" in f.text:
            bt = adaptive_backticks(f.text)
            lines.append(bt)
            lines.append(f.text)
            lines.append(bt)
        else:
            lines.append(f.text)

        lines.append("")
        lines.append("---")
        lines.append("")

    # CdC §11.1 — LF ou CRLF (conf, défaut CRLF sous Windows)
    # Utiliser write_bytes pour éviter la conversion automatique \n → \r\n sur Windows
    sep = "\r\n" if line_ending == "crlf" else "\n"
    output_path.write_bytes(sep.join(lines).encode("utf-8"))
