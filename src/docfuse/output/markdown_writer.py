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
from docfuse.constants import VERBATIM_EXTENSIONS
from docfuse.core.context_counter import TokenEstimate
from docfuse.core.orchestrator import OrchestratorResult
from docfuse.core.splitter import CorpusPart
from docfuse.i18n import format_number, t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.output.source_header import adaptive_backticks, build_source_header


def write_markdown_corpus(
    result: OrchestratorResult,
    output_path: Path,
    margin: float = 0.15,
    line_ending: str | None = None,
    *,
    part: CorpusPart | None = None,
    parts_total: int = 1,
) -> None:
    """Écrit le corpus Markdown (entier, ou une partie en mode découpage).

    Args:
        result: Résultat de l'orchestration.
        output_path: Chemin du fichier .md à écrire.
        margin: Marge appliquée (pour les en-têtes).
        line_ending: "lf" ou "crlf". Si None, auto-détecté (CRLF sous Windows).
        part: Partie à écrire (D-101) — seuls ses fichiers sont inclus et le
            préambule indique « Partie i/N ». None = corpus entier.
        parts_total: Nombre total de parties (pour le préambule).
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
    if part is None:
        lines.append(f"- **{t('corpus.files')}** : {len(result.files)}")
    else:
        lines.append(f"- **{t('corpus.part_label')}** : {part.index}/{parts_total}")
        lines.append(f"- **{t('corpus.files')}** : {len(part.file_indices)}")
        lines.append(f"- **{t('corpus.part_estimated')}** : {format_number(part.tokens_estimated)}")
        lines.append(
            f"- **{t('corpus.part_with_margin')}** : {format_number(part.tokens_with_margin)}"
        )
        if part.oversized:
            lines.append(f"- **{t('corpus.part_oversized')}**")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Blocs SOURCE pour chaque fichier extrait. `strict=True` (D-096) : un
    # désalignement files/estimates doit échouer bruyamment, jamais tronquer
    # le corpus en silence (le PDF writer était déjà strict).
    for f, est in selected_files(result, part):
        header = build_source_header(f, margin, est.tokens_estimated, est.tokens_with_margin)
        lines.append(header)
        lines.append("")

        # Les formats texte (Markdown, texte brut, CSV, XML/JSON, e-mails)
        # sont inclus tels quels (CdC §7.3). Les autres formats qui
        # contiennent des ``` sont encapsulés dans des backticks adaptatifs.
        # D-099 : la condition comparait `file_type` à des noms de famille
        # ("markdown", "text"…) alors que M-08 y met l'extension ("md",
        # "txt") — un .md contenant des ``` était encapsulé malgré le CdC.
        if f.extension in VERBATIM_EXTENSIONS:
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

    # CdC §11.1 — LF ou CRLF (conf, défaut CRLF sous Windows).
    # D-096 : seules les jointures entre blocs prenaient `sep` ; l'en-tête
    # SOURCE (déjà joint en `\n`) et le texte des fichiers (LF, ou CR/CRLF
    # hérités de la source) gardaient leurs fins de ligne d'origine → fichier
    # à fins de ligne mélangées en mode CRLF. On normalise tout en `\n`
    # d'abord, puis une seule conversion vers le séparateur demandé.
    # Utiliser write_bytes pour éviter la conversion automatique \n → \r\n sur Windows
    sep = "\r\n" if line_ending == "crlf" else "\n"
    content = "\n".join(_normalize_newlines(block) for block in lines)
    if sep != "\n":
        content = content.replace("\n", sep)
    output_path.write_bytes(content.encode("utf-8"))


def selected_files(
    result: OrchestratorResult, part: CorpusPart | None
) -> list[tuple[ExtractedFile, TokenEstimate]]:
    """Fichiers extraits à écrire, avec leur estimation — tout le corpus ou
    une partie (D-101). `strict=True` : un désalignement files/estimates
    échoue bruyamment (D-096)."""
    pairs = list(zip(result.files, result.estimates, strict=True))
    if part is None:
        return [(f, est) for f, est in pairs if f.status.is_extracted()]
    return [pairs[i] for i in part.file_indices if pairs[i][0].status.is_extracted()]


def _normalize_newlines(text: str) -> str:
    """Ramène CRLF et CR isolés à LF (idempotent sur du LF pur)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")
