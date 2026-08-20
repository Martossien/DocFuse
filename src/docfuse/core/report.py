"""Génération du rapport d'exécution (Markdown + JSON).

CdC §11.3 — Rapport toujours émis, à côté de la sortie.
CdC §15 — Toutes les chaînes via i18n.
Contenu : horodatage, version, plafond, marge, totaux, liste de tous les fichiers
(retenus ou non), statuts, erreurs, encodages, nombre d'images, caractères extraits.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

from docfuse import __version__
from docfuse.constants import BYTES_PER_TOKEN
from docfuse.i18n import format_number, t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus


def generate_json_report(
    files: list[ExtractedFile],
    ignored_files: list[tuple[Path, str]],
    context_limit: int,
    margin: float,
    total_tokens_estimated: int,
    total_tokens_with_margin: int,
    output_path: Path,
) -> None:
    """Génère le rapport JSON.

    Args:
        files: Liste des fichiers extraits.
        ignored_files: Liste des (chemin, raison) ignorés.
        context_limit: Plafond de contexte.
        margin: Marge appliquée.
        total_tokens_estimated: Total tokens estimés.
        total_tokens_with_margin: Total tokens avec marge.
        output_path: Chemin du fichier JSON à écrire.
    """
    report: dict[str, object] = {
        "version": __version__,
        "timestamp": datetime.now().isoformat(),
        "context_limit": context_limit,
        "margin": margin,
        "total_tokens_estimated": total_tokens_estimated,
        "total_tokens_with_margin": total_tokens_with_margin,
        "total_files": len(files),
        "total_ignored": len(ignored_files),
        "files": [f.to_dict() for f in files],
        "ignored": [{"path": str(p), "reason": r} for p, r in ignored_files],
    }
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def generate_markdown_report(
    files: list[ExtractedFile],
    ignored_files: list[tuple[Path, str]],
    context_limit: int,
    margin: float,
    total_tokens_estimated: int,
    total_tokens_with_margin: int,
    output_path: Path,
) -> None:
    """Génère le rapport Markdown lisible.

    Args:
        files: Liste des fichiers extraits.
        ignored_files: Liste des (chemin, raison) ignorés.
        context_limit: Plafond de contexte.
        margin: Marge appliquée.
        total_tokens_estimated: Total tokens estimés.
        total_tokens_with_margin: Total tokens avec marge.
        output_path: Chemin du fichier Markdown à écrire.
    """
    lines: list[str] = []
    lines.append(f"# {t('report.title')}")
    lines.append("")
    lines.append(f"- **{t('report.version')}** : {__version__}")
    lines.append(f"- **{t('report.date')}** : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **{t('report.context_limit')}** : {format_number(context_limit)}")
    lines.append(f"- **{t('report.margin')}** : +{margin * 100:.0f} %")
    lines.append(f"- **{t('report.total_estimated')}** : {format_number(total_tokens_estimated)}")
    lines.append(
        f"- **{t('report.total_with_margin')}** : {format_number(total_tokens_with_margin)}"
    )
    lines.append(f"- **{t('report.files_analyzed')}** : {len(files)}")
    lines.append(f"- **{t('report.files_ignored')}** : {len(ignored_files)}")
    lines.append("")

    # Tableau des fichiers extraits
    if files:
        lines.append(f"## {t('report.files_analyzed')}")
        lines.append("")
        lines.append(
            f"| {t('table.file')} | {t('table.type')} | {t('table.text_estimated')} | "
            f"{t('table.context_margin')} | {t('table.status')} |"
        )
        lines.append("|---|---|---|---|---|")
        for f in files:
            # I-02: Formule correcte : ceil(octets/4), ceil(tokens*(1+margin))
            tokens = math.ceil(f.text_bytes_utf8 / BYTES_PER_TOKEN) if f.text else 0
            tokens_margin = math.ceil(tokens * (1 + margin))
            status_label = f.status.label()
            lines.append(
                f"| {f.relative_path} | {f.file_type} | {format_number(tokens)} | "
                f"{format_number(tokens_margin)} | {status_label} |"
            )
        lines.append("")

    # Fichiers ignorés
    if ignored_files:
        lines.append(f"## {t('report.files_ignored')}")
        lines.append("")
        lines.append(f"| {t('table.file')} | {t('report.files_ignored')} |")
        lines.append("|---|---|")
        for path, reason in ignored_files:
            lines.append(f"| {path.name} | {reason} |")
        lines.append("")

    # Erreurs
    error_files = [f for f in files if f.status is FileStatus.ERROR]
    if error_files:
        lines.append(f"## {t('report.errors')}")
        lines.append("")
        for f in error_files:
            lines.append(f"- **{f.relative_path}** : {f.error_message or t('error.unknown')}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
