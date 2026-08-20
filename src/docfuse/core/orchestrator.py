"""Orchestrateur du pipeline principal.

CdC §13.3 — Pipeline :
  Entrée dossier
    → inventaire (liste blanche, ignores)
    → extraction parallèle (ThreadPoolExecutor, bornée)
    → mesure images + pauvreté texte
    → compteur par fichier
    → agrégation + compteur total
    → décision bloquer / autoriser
    → écriture MD ou PDF + rapport
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from docfuse.config import ScanConfig
from docfuse.constants import (
    DEFAULT_CONTEXT_LIMIT,
    DEFAULT_MARGIN,
    DEFAULT_RECURSIVE,
    LARGE_FILE_THRESHOLD,
    MAX_WORKERS,
    SCAN_MIN_CHARS_FILE,
    SCAN_MIN_CHARS_PER_PAGE,
    SCAN_SPARSE_PAGE_CHARS,
    SCAN_SPARSE_PAGE_RATIO,
)
from docfuse.core.context_counter import (
    TokenEstimate,
    aggregate_tokens,
    check_limit,
    estimate_tokens,
)
from docfuse.core.image_detector import determine_status
from docfuse.core.inventory import list_ignored, scan_directory, scan_files
from docfuse.core.progress import ProgressEmitter, ProgressEvent
from docfuse.core.registry import get_extractor_for
from docfuse.core.report import generate_json_report, generate_markdown_report
from docfuse.i18n import format_number, t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

# Supprimer les warnings bruyants de pypdf/pdfminer en mode normal
logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("pdfminer").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


class OrchestratorResult:
    """Résultat de l'orchestration.

    Attributes:
        files: Liste des fichiers extraits (dans l'ordre du tri).
        ignored: Liste des (chemin, raison) ignorés.
        estimates: Estimation de tokens par fichier.
        total: Estimation totale.
        blocking_files: Fichiers qui dépassent le plafond individuellement.
        is_blocked: True si la génération est bloquée (fichier OU total).
        block_reason: Raison du blocage si is_blocked.
    """

    def __init__(
        self,
        files: list[ExtractedFile],
        ignored: list[tuple[Path, str]],
        estimates: list[TokenEstimate],
        total: TokenEstimate,
        context_limit: int,
    ) -> None:
        self.files = files
        self.ignored = ignored
        self.estimates = estimates
        self.total = total
        self.context_limit = context_limit
        self.blocking_files: list[ExtractedFile] = []
        self.is_blocked = False
        self.block_reason: str | None = None
        self.recompute_blocking(context_limit)

    def recompute_blocking(self, context_limit: int) -> None:
        """Recalcule l'état de blocage avec un nouveau plafond.

        Source unique de vérité pour la logique de blocage.
        Utilisée par __init__ et par la GUI quand l'utilisateur change le plafond.
        """
        self.context_limit = context_limit

        # Restaurer les statuts TOO_LARGE → READY/Images/LOW_TEXT pour recalcul propre
        for f in self.files:
            if f.status is FileStatus.TOO_LARGE:
                f.status = FileStatus.READY

        # Recalculer les fichiers bloquants
        self.blocking_files = [
            f
            for f, e in zip(self.files, self.estimates, strict=True)
            if not check_limit(e.tokens_with_margin, context_limit) and f.status.is_extracted()
        ]
        for f in self.blocking_files:
            f.status = FileStatus.TOO_LARGE

        # Blocage : fichier OU total
        total_blocked = not check_limit(self.total.tokens_with_margin, context_limit)
        self.is_blocked = bool(self.blocking_files) or total_blocked

        if self.blocking_files:
            names = ", ".join(f.relative_path for f in self.blocking_files)
            worst = self.blocking_files[0]
            worst_idx = self.files.index(worst)
            worst_est = self.estimates[worst_idx]
            self.block_reason = t(
                "summary.blocked_file",
                file=worst.relative_path,
                tokens=format_number(worst_est.tokens_with_margin),
                limit=format_number(context_limit),
            )
            if len(self.blocking_files) > 1:
                self.block_reason += f" ({names})"
        elif total_blocked:
            self.block_reason = t(
                "summary.blocked_total",
                total=format_number(self.total.tokens_with_margin),
                limit=format_number(context_limit),
            )
        else:
            self.block_reason = None


def run_analysis(
    input_path: Path,
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
    margin: float = DEFAULT_MARGIN,
    recursive: bool = DEFAULT_RECURSIVE,
    exclude_globs: list[str] | None = None,
    emitter: ProgressEmitter | None = None,
    extensions: frozenset[str] | None = None,
    scan_config: ScanConfig | None = None,
    sort: str = "name",
    max_depth: int = 12,
) -> OrchestratorResult:
    """Lance l'analyse complète : inventaire → extraction → comptage.

    Args:
        input_path: Dossier ou fichier d'entrée.
        context_limit: Plafond de contexte (défaut 128 000).
        margin: Marge (défaut 0.15).
        recursive: Parcourir les sous-dossiers.
        exclude_globs: Patterns d'exclusion.
        emitter: Émetteur de progression (pour GUI/CLI).
        extensions: Surcharge des extensions supportées (liste blanche).
        scan_config: Configuration des seuils de scan (ScanConfig).

    Returns:
        OrchestratorResult avec les fichiers, estimations, statut de blocage.
    """
    exclude_globs = exclude_globs or []

    # Extraction des seuils de scan depuis scan_config (C-08)
    if scan_config is not None:
        min_chars_file = scan_config.min_chars_file
        min_chars_per_page = scan_config.min_chars_per_page
        sparse_page_chars = scan_config.sparse_page_chars
        sparse_page_ratio = scan_config.sparse_page_ratio
    else:
        min_chars_file = SCAN_MIN_CHARS_FILE
        min_chars_per_page = SCAN_MIN_CHARS_PER_PAGE
        sparse_page_chars = SCAN_SPARSE_PAGE_CHARS
        sparse_page_ratio = SCAN_SPARSE_PAGE_RATIO

    # 1. Inventaire
    if input_path.is_dir():
        file_paths = scan_directory(
            input_path,
            recursive=recursive,
            exclude_globs=exclude_globs,
            extensions=extensions,
            sort=sort,
            max_depth=max_depth,
        )
        ignored = list_ignored(
            input_path,
            recursive=recursive,
            exclude_globs=exclude_globs,
            extensions=extensions,
        )
    else:
        file_paths = scan_files([input_path], exclude_globs=exclude_globs, extensions=extensions)
        ignored = []

    total_files = len(file_paths)
    logger.info("Inventaire : %d fichiers supportés, %d ignorés", total_files, len(ignored))

    # 2. Extraction parallèle
    files: list[ExtractedFile] = []

    if total_files == 0:
        total = TokenEstimate(0, 0, 0)
        return OrchestratorResult(files, ignored, [], total, context_limit)

    def _extract_one(idx: int, path: Path) -> tuple[int, ExtractedFile]:
        rel = str(path.relative_to(input_path)) if input_path.is_dir() else path.name

        # I-15: Avertissement pour fichier volumineux
        try:
            file_size = path.stat().st_size
            if file_size > LARGE_FILE_THRESHOLD:
                logger.warning(
                    "Fichier volumineux (%d Mo): %s — patience", file_size // (1024 * 1024), rel
                )
        except OSError:
            pass

        extractor_cls = get_extractor_for(path)

        if extractor_cls is None:
            result = ExtractedFile(
                path=path,
                relative_path=rel,
                extension=path.suffix.lower().lstrip("."),
                file_type=path.suffix.lower().lstrip("."),
                size_bytes=path.stat().st_size if path.exists() else 0,
                status=FileStatus.IGNORED,
                error_message=t("error.no_extractor", ext=path.suffix),
            )
        else:
            result = extractor_cls.safe_extract(path, rel)

        if emitter:
            emitter.emit(
                ProgressEvent(
                    file_path=rel,
                    current=idx + 1,
                    total=total_files,
                    status=result.status.value,
                    message=result.error_message,
                )
            )

        return idx, result

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_extract_one, i, p): i for i, p in enumerate(file_paths)}
        results_map: dict[int, ExtractedFile] = {}
        for future in as_completed(futures):
            if emitter and emitter.is_cancelled:
                executor.shutdown(wait=False, cancel_futures=True)
                break
            idx, result = future.result()
            results_map[idx] = result

    # Remettre dans l'ordre original (tri par inventaire)
    files = [results_map[i] for i in range(total_files) if i in results_map]

    # 3. Détermination du statut (images / low_text) avec seuils de config (C-08)
    for f in files:
        if f.status.is_extracted():  # M-03: simplifié, is_extracted suffit
            f.status = determine_status(
                text=f.text,
                image_count=f.image_count,
                chars_per_page=f.chars_per_page or None,
                min_chars_file=min_chars_file,
                min_chars_per_page=min_chars_per_page,
                sparse_page_chars=sparse_page_chars,
                sparse_page_ratio=sparse_page_ratio,
            )

    # 4. Compteur par fichier (en-têtes SOURCE comprises, CdC §8.2 §10.1)
    from docfuse.output.source_header import build_source_header

    estimates: list[TokenEstimate] = []
    for f in files:
        if f.status.is_extracted():
            # I-01: Le total inclut l'en-tête SOURCE + le texte
            full_text = build_source_header(f, margin) + f.text
            estimates.append(estimate_tokens(full_text, margin))
        else:
            estimates.append(TokenEstimate(0, 0, 0))

    # 5. Agrégation
    total = aggregate_tokens(estimates)

    # 6. Décision de blocage
    orchestrator_result = OrchestratorResult(files, ignored, estimates, total, context_limit)

    logger.info(
        "Analyse terminée : %d fichiers, %d tokens estimés, %d avec marge, blocage=%s",
        len(files),
        total.tokens_estimated,
        total.tokens_with_margin,
        orchestrator_result.is_blocked,
    )

    return orchestrator_result


def generate_corpus(
    result: OrchestratorResult,
    output_path: Path,
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
    margin: float = DEFAULT_MARGIN,
) -> bool:
    """Génère le corpus final (Markdown ou PDF) + rapport.

    Args:
        result: Résultat de l'analyse.
        output_path: Chemin du fichier de sortie.
        context_limit: Plafond de contexte.
        margin: Marge appliquée.

    Returns:
        True si le corpus a été généré, False si bloqué.
    """
    if result.is_blocked:
        logger.warning("Génération bloquée : %s", result.block_reason)
        _write_report_only(result, output_path, context_limit, margin)
        return False

    ext = output_path.suffix.lower()
    if ext == ".md":
        from docfuse.output.markdown_writer import write_markdown_corpus

        write_markdown_corpus(result, output_path, margin)
    elif ext == ".pdf":
        from docfuse.output.pdf_writer import write_pdf_corpus

        write_pdf_corpus(result, output_path, margin)
    else:
        raise ValueError(f"Format de sortie non supporté : {ext}")

    _write_report_only(result, output_path, context_limit, margin)
    logger.info("Corpus généré : %s", output_path)
    return True


def _write_report_only(
    result: OrchestratorResult,
    output_path: Path,
    context_limit: int,
    margin: float,
) -> None:
    """Écrit les rapports MD et JSON à côté de la sortie."""
    report_md = output_path.with_name(output_path.stem + "_rapport.md")
    report_json = output_path.with_name(output_path.stem + "_rapport.json")
    generate_markdown_report(
        result.files,
        result.ignored,
        context_limit,
        margin,
        result.total.tokens_estimated,
        result.total.tokens_with_margin,
        report_md,
    )
    generate_json_report(
        result.files,
        result.ignored,
        context_limit,
        margin,
        result.total.tokens_estimated,
        result.total.tokens_with_margin,
        report_json,
    )
