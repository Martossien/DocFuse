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
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from docfuse.config import ScanConfig
from docfuse.constants import (
    DEFAULT_CONTEXT_LIMIT,
    DEFAULT_MARGIN,
    DEFAULT_RECURSIVE,
    DEFAULT_TOKENIZER_ENGINE,
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
)
from docfuse.core.duplicate_detector import detect_duplicates
from docfuse.core.image_detector import determine_status
from docfuse.core.inventory import collect_inputs
from docfuse.core.progress import ProgressEmitter, ProgressEvent
from docfuse.core.registry import get_extractor_for
from docfuse.core.report import generate_json_report, generate_markdown_report
from docfuse.core.secret_scanner import scan_for_secrets
from docfuse.core.tokenizers.base import TokenizerEngine
from docfuse.core.tokenizers.registry import resolve_engine
from docfuse.i18n import format_number, t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus
from docfuse.models.input_selection import InputSelection, path_key

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
        margin: float = DEFAULT_MARGIN,
        engine: TokenizerEngine | None = None,
    ) -> None:
        self.files = files
        self.ignored = ignored
        self.estimates = estimates
        self.total = total
        self.context_limit = context_limit
        self.margin = margin
        self.engine = engine
        self._base_statuses = [file.status for file in files]
        self.blocking_files: list[ExtractedFile] = []
        self.is_blocked = False
        self.block_reason: str | None = None
        self.recompute_blocking(context_limit)

    @property
    def engine_id(self) -> str:
        """Identifiant du moteur de comptage utilisé ("approx" si aucun)."""
        return self.engine.info.id if self.engine is not None else DEFAULT_TOKENIZER_ENGINE

    def recompute_blocking(self, context_limit: int) -> None:
        """Recalcule l'état de blocage avec un nouveau plafond.

        Source unique de vérité pour la logique de blocage.
        Utilisée par __init__ et par la GUI quand l'utilisateur change le plafond.
        """
        self.context_limit = context_limit

        # Restaurer exactement les alertes d'extraction avant chaque recalcul.
        for file, base_status in zip(self.files, self._base_statuses, strict=True):
            file.status = base_status

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

    def recompute_engine(self, engine_id: str) -> None:
        """Recalcule les estimations avec un nouveau moteur, sans ré-extraction.

        Réutilise les textes déjà extraits (self.files[i].text) — même principe
        que recompute_blocking() pour le plafond : la GUI peut changer de moteur
        de comptage et voir le résultat instantanément, sans relancer l'analyse.
        """
        from docfuse.output.source_header import estimate_source_context

        engine = resolve_engine(engine_id)
        new_estimates: list[TokenEstimate] = []
        for file, base_status in zip(self.files, self._base_statuses, strict=True):
            if base_status.is_extracted():
                new_estimates.append(estimate_source_context(file, self.margin, engine))
            else:
                new_estimates.append(TokenEstimate(0, 0, 0))

        self.engine = engine
        self.estimates = new_estimates
        self.total = aggregate_tokens(self.estimates, self.margin, engine)
        self.recompute_blocking(self.context_limit)

    def count_base_status(self, status: FileStatus) -> int:
        """Compte un statut d'analyse sans masquer les alertes par le blocage."""

        return self._base_statuses.count(status)

    def remove_file(self, path: Path, reason: str | None = None) -> bool:
        """Retire un fichier et recalcule immédiatement total et blocage.

        Returns:
            True si le fichier appartenait au résultat, False sinon.
        """

        key = path_key(path)
        index = next(
            (i for i, file in enumerate(self.files) if path_key(file.path) == key),
            None,
        )
        if index is None:
            return False

        removed = self.files.pop(index)
        self.estimates.pop(index)
        self._base_statuses.pop(index)
        if reason is not None and all(path_key(item) != key for item, _ in self.ignored):
            self.ignored.append((removed.path, reason))

        self.total = aggregate_tokens(self.estimates, self.margin, self.engine)
        self.recompute_blocking(self.context_limit)
        return True


def run_analysis(
    input_path: Path | Sequence[Path] | InputSelection,
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
    margin: float = DEFAULT_MARGIN,
    recursive: bool = DEFAULT_RECURSIVE,
    exclude_globs: list[str] | None = None,
    emitter: ProgressEmitter | None = None,
    extensions: frozenset[str] | None = None,
    scan_config: ScanConfig | None = None,
    sort: str = "name",
    max_depth: int = 12,
    tokenizer_engine: str = DEFAULT_TOKENIZER_ENGINE,
    extract_embedded_images: bool = False,
) -> OrchestratorResult:
    """Lance l'analyse complète : inventaire → extraction → comptage.

    Args:
        input_path: Sélection, dossier, fichier ou liste de chemins d'entrée.
        context_limit: Plafond de contexte (défaut 128 000).
        margin: Marge (défaut 0.15).
        recursive: Parcourir les sous-dossiers.
        exclude_globs: Patterns d'exclusion.
        emitter: Émetteur de progression (pour GUI/CLI).
        extensions: Surcharge des extensions supportées (liste blanche).
        scan_config: Configuration des seuils de scan (ScanConfig).
        tokenizer_engine: Identifiant du moteur de comptage ("approx" par
            défaut). Un id inconnu ou indisponible retombe sur "approx"
            (voir core/tokenizers/registry.py) — n'échoue jamais.
        extract_embedded_images: Exporter les images intégrées (DOCX/PPTX,
            D-091) en fichiers séparés, avec un tag de position dans le
            texte. Désactivé par défaut (écrit des fichiers en plus).

    Returns:
        OrchestratorResult avec les fichiers, estimations, statut de blocage.
    """
    exclude_globs = exclude_globs or []
    selection = InputSelection.from_value(input_path)
    engine = resolve_engine(tokenizer_engine)

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

    # 1. Inventaire : les fichiers explicites restent une liste figée.
    inventory_entries, ignored = collect_inputs(
        selection,
        recursive,
        exclude_globs,
        extensions,
        sort,
        max_depth,
    )

    total_files = len(inventory_entries)
    logger.info("Inventaire : %d fichiers supportés, %d ignorés", total_files, len(ignored))

    if emitter:
        for entry in inventory_entries:
            emitter.emit(
                ProgressEvent(
                    file_path=entry.relative_path,
                    current=0,
                    total=total_files,
                    status="pending",
                )
            )

    # 2. Extraction parallèle
    files: list[ExtractedFile] = []

    if total_files == 0:
        total = TokenEstimate(0, 0, 0)
        return OrchestratorResult(files, ignored, [], total, context_limit, margin, engine)

    def _extract_one(idx: int, path: Path, relative_path: str) -> tuple[int, ExtractedFile]:
        # I-15: Avertissement pour fichier volumineux
        try:
            file_size = path.stat().st_size
            if file_size > LARGE_FILE_THRESHOLD:
                logger.warning(
                    "Fichier volumineux (%d Mo): %s — patience",
                    file_size // (1024 * 1024),
                    relative_path,
                )
        except OSError:
            pass

        extractor_cls = get_extractor_for(path)

        if extractor_cls is None:
            result = ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=path.suffix.lower().lstrip("."),
                file_type=path.suffix.lower().lstrip("."),
                size_bytes=path.stat().st_size if path.exists() else 0,
                status=FileStatus.IGNORED,
                error_message=t("error.no_extractor", ext=path.suffix),
            )
        else:
            result = extractor_cls.safe_extract(
                path, relative_path, extract_images=extract_embedded_images
            )

        if emitter:
            emitter.emit(
                ProgressEvent(
                    file_path=relative_path,
                    current=idx + 1,
                    total=total_files,
                    status=result.status.value,
                    message=result.error_message,
                )
            )

        return idx, result

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_extract_one, i, entry.path, entry.relative_path): i
            for i, entry in enumerate(inventory_entries)
        }
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

    # 3b. Alerte secrets potentiels (non bloquant, ne modifie jamais le texte).
    for f in files:
        if not f.status.is_extracted():
            continue
        findings = scan_for_secrets(f.text)
        if findings:
            kinds = ", ".join(
                t("secret.finding", kind=t(kind_key), line=line) for kind_key, line in findings
            )
            f.extra_metadata["secrets_detected"] = kinds

    # 3c. Détection de doublons de contenu entre fichiers (avant comptage :
    # le texte d'un doublon est remplacé par une note, donc compté correctement).
    detect_duplicates(files)

    # 4. Compteur par fichier (en-têtes SOURCE comprises, CdC §8.2 §10.1)
    from docfuse.output.source_header import estimate_source_context

    estimates: list[TokenEstimate] = []
    for f in files:
        if f.status.is_extracted():
            # I-01: Le compteur inclut exactement l'en-tête SOURCE + le texte.
            estimates.append(estimate_source_context(f, margin, engine))
        else:
            estimates.append(TokenEstimate(0, 0, 0))

    # 5. Agrégation
    total = aggregate_tokens(estimates, margin, engine)

    # 6. Décision de blocage
    orchestrator_result = OrchestratorResult(
        files,
        ignored,
        estimates,
        total,
        context_limit,
        margin,
        engine,
    )

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

    from docfuse.output.image_writer import write_embedded_images

    images_written = write_embedded_images(result.files, output_path)
    if images_written:
        logger.info("%d image(s) intégrée(s) exportée(s) à côté de %s", images_written, output_path)

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
        estimates=result.estimates,
        engine_id=result.engine_id,
    )
    generate_json_report(
        result.files,
        result.ignored,
        context_limit,
        margin,
        result.total.tokens_estimated,
        result.total.tokens_with_margin,
        report_json,
        estimates=result.estimates,
        engine_id=result.engine_id,
    )
