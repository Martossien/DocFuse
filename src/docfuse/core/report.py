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
from typing import TYPE_CHECKING

from docfuse import __version__
from docfuse.branding import APP_NAME
from docfuse.constants import BYTES_PER_TOKEN, DEFAULT_TOKENIZER_ENGINE, REPORT_SUFFIX
from docfuse.core.context_counter import TokenEstimate
from docfuse.core.notes import ordered_notes
from docfuse.core.splitter import CorpusPart, part_of_file
from docfuse.i18n import format_number, t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

if TYPE_CHECKING:
    from docfuse.core.orchestrator import OrchestratorResult


def write_report_pair(
    result: OrchestratorResult, base_path: Path, *, parts: list[CorpusPart] | None = None
) -> tuple[Path, Path]:
    """Écrit le rapport Markdown ET le rapport JSON d'un résultat d'analyse.

    Le Markdown va dans `base_path` avec le suffixe `.md`, le JSON avec le
    suffixe `.json` — quel que soit le suffixe reçu (D-096 : `rapport.json`
    choisi dans la GUI écrasait le Markdown). Plafond, marge, totaux et
    moteur viennent du résultat lui-même : une seule source de vérité.
    D-099 : remplace trois copies (CLI, GUI, orchestrateur) de deux appels à
    neuf arguments chacun.

    Args:
        result: Résultat d'analyse.
        base_path: Chemin de base (le suffixe est remplacé).
        parts: Parties écrites en mode découpage (D-101) — le rapport liste
            alors chaque partie et la partie de chaque fichier.

    Returns:
        Tuple (chemin du Markdown, chemin du JSON) écrits.
    """
    markdown_path = base_path.with_suffix(".md")
    json_path = base_path.with_suffix(".json")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    common = (
        result.files,
        result.ignored,
        result.context_limit,
        result.margin,
        result.total.tokens_estimated,
        result.total.tokens_with_margin,
    )
    generate_markdown_report(
        *common,
        markdown_path,
        estimates=result.estimates,
        engine_id=result.engine_id,
        parts=parts,
        split_context=result.split_context,
        corpus_path=base_path.with_name(base_path.stem.removesuffix(REPORT_SUFFIX)),
    )
    generate_json_report(
        *common,
        json_path,
        estimates=result.estimates,
        engine_id=result.engine_id,
        parts=parts,
        split_context=result.split_context,
    )
    return markdown_path, json_path


def _check_aligned(files: list[ExtractedFile], estimates: list[TokenEstimate] | None) -> None:
    """Un `estimates` fourni doit être aligné sur `files` (D-096).

    L'ancien repli silencieux (`i < len(estimates)` sinon octets/4) aurait
    masqué un désalignement en imprimant des chiffres faux pour la fin de la
    liste — on préfère échouer bruyamment, comme `zip(strict=True)` dans les
    writers.
    """
    if estimates is not None and len(estimates) != len(files):
        raise ValueError(
            f"estimates ({len(estimates)}) et files ({len(files)}) ne sont pas alignés"
        )


def generate_json_report(
    files: list[ExtractedFile],
    ignored_files: list[tuple[Path, str]],
    context_limit: int,
    margin: float,
    total_tokens_estimated: int,
    total_tokens_with_margin: int,
    output_path: Path,
    *,
    estimates: list[TokenEstimate] | None = None,
    engine_id: str = DEFAULT_TOKENIZER_ENGINE,
    parts: list[CorpusPart] | None = None,
    split_context: bool = False,
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
        estimates: Estimations par fichier (même ordre que `files`), pour
            détailler les tokens de chaque fichier avec le moteur réellement
            utilisé. Si `None`, ce détail est omis.
        engine_id: Identifiant du moteur de comptage utilisé pour ce rapport.
        parts: Parties du corpus en mode découpage (D-101) ; chaque fichier
            reçoit alors sa clé `part` (None s'il n'est dans aucune partie).
        split_context: Mode découpage actif ou non.
    """
    _check_aligned(files, estimates)
    files_data: list[dict[str, object]] = []
    for i, f in enumerate(files):
        data = f.to_dict()
        if estimates is not None:
            data["tokens_estimated"] = estimates[i].tokens_estimated
            data["tokens_with_margin"] = estimates[i].tokens_with_margin
        if parts is not None:
            data["part"] = part_of_file(parts, i)
        files_data.append(data)

    report: dict[str, object] = {
        "version": __version__,
        "timestamp": datetime.now().isoformat(),
        "context_limit": context_limit,
        "margin": margin,
        "tokenizer_engine": engine_id,
        "total_tokens_estimated": total_tokens_estimated,
        "total_tokens_with_margin": total_tokens_with_margin,
        "total_files": len(files),
        "total_ignored": len(ignored_files),
        "split_context": split_context,
        "files": files_data,
        "ignored": [{"path": str(p), "reason": r} for p, r in ignored_files],
    }
    if parts is not None:
        report["parts"] = [
            {
                "index": part.index,
                "files": [files[i].relative_path for i in part.file_indices],
                "tokens_estimated": part.tokens_estimated,
                "tokens_with_margin": part.tokens_with_margin,
                "oversized": part.oversized,
            }
            for part in parts
        ]
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
    *,
    estimates: list[TokenEstimate] | None = None,
    engine_id: str = DEFAULT_TOKENIZER_ENGINE,
    parts: list[CorpusPart] | None = None,
    split_context: bool = False,
    corpus_path: Path | None = None,
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
        estimates: Estimations par fichier (même ordre que `files`). Si
            fourni, le tableau par fichier utilise le moteur réellement
            utilisé au lieu de recalculer une approximation octets/4.
        engine_id: Identifiant du moteur de comptage utilisé pour ce rapport.
        parts: Parties du corpus en mode découpage (D-101) → section
            « Parties » avec, pour chacune, son fichier et ses totaux.
        split_context: Mode découpage actif ou non.
        corpus_path: Chemin de base du corpus, pour nommer les parties
            (`<stem>_001.<ext>`) ; sans lui, seul le numéro est affiché.
    """
    lines: list[str] = []
    lines.append(f"# {t('report.title', app=APP_NAME)}")
    lines.append("")
    lines.append(f"- **{t('report.version')}** : {__version__}")
    lines.append(f"- **{t('report.date')}** : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **{t('report.context_limit')}** : {format_number(context_limit)}")
    lines.append(f"- **{t('report.margin')}** : +{margin * 100:.0f} %")
    lines.append(f"- **{t('report.tokenizer_engine')}** : {t(f'tokenizer.{engine_id}')}")
    lines.append(f"- **{t('report.total_estimated')}** : {format_number(total_tokens_estimated)}")
    lines.append(
        f"- **{t('report.total_with_margin')}** : {format_number(total_tokens_with_margin)}"
    )
    lines.append(f"- **{t('report.files_analyzed')}** : {len(files)}")
    lines.append(f"- **{t('report.files_ignored')}** : {len(ignored_files)}")
    if split_context:
        lines.append(f"- **{t('report.split_context')}** : {len(parts or [])}")
    lines.append("")

    # Parties du corpus (mode découpage, D-101)
    if parts:
        lines.append(f"## {t('report.parts')}")
        lines.append("")
        lines.append(
            f"| {t('table.part')} | {t('table.file')} | {t('corpus.files')} | "
            f"{t('table.text_estimated')} | {t('table.context_margin')} | {t('table.status')} |"
        )
        lines.append("|---|---|---|---|---|---|")
        for part in parts:
            name = (
                f"{corpus_path.stem}_{part.index:03d}"
                if corpus_path is not None
                else str(part.index)
            )
            status = t("report.part_oversized") if part.oversized else t("status.ready")
            lines.append(
                f"| {part.index} | {name} | {len(part.file_indices)} | "
                f"{format_number(part.tokens_estimated)} | "
                f"{format_number(part.tokens_with_margin)} | {status} |"
            )
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
        _check_aligned(files, estimates)
        for i, f in enumerate(files):
            if estimates is not None:
                tokens = estimates[i].tokens_estimated
                tokens_margin = estimates[i].tokens_with_margin
            else:
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

    # Notes de transparence (secrets potentiels, doublons, dédup PDF, images
    # base64 retirées) — CdC §8, sans perte silencieuse.
    notes_by_file = [(f, ordered_notes(f)) for f in files]
    notes_by_file = [(f, notes) for f, notes in notes_by_file if notes]
    if notes_by_file:
        lines.append(f"## {t('report.notes')}")
        lines.append("")
        for f, notes in notes_by_file:
            for note in notes:
                lines.append(f"- **{f.relative_path}** : {note}")
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
