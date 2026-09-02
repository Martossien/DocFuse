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
from concurrent.futures import Future, as_completed
from dataclasses import dataclass
from pathlib import Path

from docfuse.config import ScanConfig
from docfuse.constants import (
    DEFAULT_CONTEXT_LIMIT,
    DEFAULT_MARGIN,
    DEFAULT_RECURSIVE,
    DEFAULT_TOKENIZER_ENGINE,
    LARGE_FILE_THRESHOLD,
    MAX_TRAVERSAL_DEPTH,
    SCAN_MIN_CHARS_FILE,
    SCAN_MIN_CHARS_PER_PAGE,
    SCAN_SPARSE_PAGE_CHARS,
    SCAN_SPARSE_PAGE_RATIO,
    SECRETS_NOTE_MAX_LINES_PER_KIND,
)
from docfuse.core.context_counter import (
    TokenEstimate,
    aggregate_tokens,
    check_limit,
)
from docfuse.core.duplicate_detector import detect_duplicates
from docfuse.core.embedded_images import dedupe_image_filenames
from docfuse.core.image_detector import determine_status
from docfuse.core.inventory import InventoryEntry, collect_inputs
from docfuse.core.progress import ProgressEmitter, ProgressEvent
from docfuse.core.registry import get_extractor_for
from docfuse.core.report import write_report_pair
from docfuse.core.secret_scanner import scan_for_secrets
from docfuse.core.splitter import CorpusPart
from docfuse.core.tokenizers.base import TokenizerEngine
from docfuse.core.tokenizers.registry import resolve_engine
from docfuse.core.workers import BrokenProcessPool, extraction_pool
from docfuse.extractors.base import file_type_for
from docfuse.i18n import format_number, get_language, set_language, t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus
from docfuse.models.input_selection import InputSelection, path_key
from docfuse.output.paths import report_base_path

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
        cancelled: True si l'analyse a été interrompue par l'utilisateur
            (D-099) — le résultat est alors vide et ne doit pas être utilisé.
        split_context: Mode « découpage » (D-101) : le plafond ne bloque plus,
            les fichiers sont répartis en plusieurs corpus (voir
            `core.splitter`). `oversized_files` liste alors les fichiers qui
            dépassent à eux seuls le plafond (isolés dans leur partie).
        oversized_files: Fichiers dont l'estimation avec marge dépasse le
            plafond — identique à `blocking_files` hors mode découpage.
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
        *,
        cancelled: bool = False,
        split_context: bool = False,
    ) -> None:
        self.files = files
        self.ignored = ignored
        self.estimates = estimates
        self.total = total
        self.context_limit = context_limit
        self.margin = margin
        self.engine = engine
        self.cancelled = cancelled
        self.split_context = split_context
        self._base_statuses = [file.status for file in files]
        # D-098 : estimations déjà calculées, par moteur — un aller-retour
        # de menu (approx → Mistral → approx) ne re-tokenise plus tout.
        self._estimates_by_engine: dict[str, list[TokenEstimate]] = {self.engine_id: estimates}
        self.blocking_files: list[ExtractedFile] = []
        self.oversized_files: list[ExtractedFile] = []
        self.is_blocked = False
        self.block_reason: str | None = None
        self.recompute_blocking(context_limit)

    def extracted_indices(self) -> list[int]:
        """Indices (dans `files`) des fichiers extraits, d'après leur statut
        d'analyse — indépendant d'un éventuel TOO_LARGE posé par le blocage.
        Ce sont exactement les fichiers que les writers écrivent."""
        return [i for i, status in enumerate(self._base_statuses) if status.is_extracted()]

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

        # Recalculer les fichiers hors plafond
        self.oversized_files = [
            f
            for f, e in zip(self.files, self.estimates, strict=True)
            if not check_limit(e.tokens_with_margin, context_limit) and f.status.is_extracted()
        ]
        if self.split_context:
            # D-101 : en mode découpage, rien ne bloque — un fichier hors
            # plafond est isolé dans sa propre partie et signalé, le total
            # est réparti sur plusieurs corpus. Les statuts restent ceux de
            # l'analyse (jamais TOO_LARGE).
            self.blocking_files = []
            self.is_blocked = False
            self.block_reason = None
            return

        self.blocking_files = list(self.oversized_files)
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
        cached = self._estimates_by_engine.get(engine.info.id)
        if cached is not None:
            new_estimates = cached
        else:
            new_estimates = []
            for file, base_status in zip(self.files, self._base_statuses, strict=True):
                if base_status.is_extracted():
                    # D-098 : estimer avec le statut d'analyse, pas avec un
                    # éventuel TOO_LARGE posé par le blocage — sinon la ligne
                    # `- alerte:` manque de l'en-tête compté et le calcul
                    # n'est plus idempotent (recompute_blocking le remet
                    # juste après).
                    file.status = base_status
                    new_estimates.append(estimate_source_context(file, self.margin, engine))
                else:
                    new_estimates.append(TokenEstimate(0, 0, 0))
            self._estimates_by_engine[engine.info.id] = new_estimates

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
        self._base_statuses.pop(index)
        # D-098 : toutes les listes d'estimations en cache restent alignées
        # sur `files` (celle du moteur courant est `self.estimates`).
        for cached in self._estimates_by_engine.values():
            cached.pop(index)
        if reason is not None and all(path_key(item) != key for item, _ in self.ignored):
            self.ignored.append((removed.path, reason))

        if self._promote_duplicate_of(removed):
            # Le texte d'un fichier a changé : seules les estimations du
            # moteur courant ont été recalculées, les autres sont périmées.
            self._estimates_by_engine = {self.engine_id: self.estimates}

        self.total = aggregate_tokens(self.estimates, self.margin, self.engine)
        self.recompute_blocking(self.context_limit)
        return True

    def _promote_duplicate_of(self, removed: ExtractedFile) -> bool:
        """Si `removed` servait d'original à des doublons, promeut le premier
        d'entre eux pour que le contenu reste dans le corpus (D-096).

        `detect_duplicates` remplace le texte des doublons par une note
        « identique à <original> ». Retirer l'original (cas typique : c'est
        le fichier TOO_LARGE que l'utilisateur enlève pour débloquer, D-045)
        laissait uniquement la note dans le corpus — le contenu réel
        disparaissait sans aucune trace, en violation de la règle 12.4.

        Returns:
            True si un fichier a été promu (son texte a changé).
        """
        from docfuse.output.source_header import estimate_source_context

        duplicates = [
            f for f in self.files if f.extra_metadata.get("duplicate_of") == removed.relative_path
        ]
        if not duplicates:
            return False

        promoted = duplicates[0]
        promoted.text = removed.text
        del promoted.extra_metadata["duplicate_of"]
        for other in duplicates[1:]:
            other.extra_metadata["duplicate_of"] = promoted.relative_path
            other.text = t("duplicate.placeholder_text", original=promoted.relative_path)

        index = self.files.index(promoted)
        if self._base_statuses[index].is_extracted():
            promoted.status = self._base_statuses[index]
            self.estimates[index] = estimate_source_context(promoted, self.margin, self.engine)
        return True


@dataclass(frozen=True)
class _ScanThresholds:
    """Seuils de pauvreté de texte (C-08), depuis `ScanConfig` ou les constantes."""

    min_chars_file: int
    min_chars_per_page: int
    sparse_page_chars: int
    sparse_page_ratio: float


def _scan_thresholds(scan_config: ScanConfig | None) -> _ScanThresholds:
    if scan_config is not None:
        return _ScanThresholds(
            scan_config.min_chars_file,
            scan_config.min_chars_per_page,
            scan_config.sparse_page_chars,
            scan_config.sparse_page_ratio,
        )
    return _ScanThresholds(
        SCAN_MIN_CHARS_FILE,
        SCAN_MIN_CHARS_PER_PAGE,
        SCAN_SPARSE_PAGE_CHARS,
        SCAN_SPARSE_PAGE_RATIO,
    )


def _extract_one(
    idx: int, path: Path, relative_path: str, extract_embedded_images: bool
) -> tuple[int, ExtractedFile]:
    """Extraction d'un fichier (dans un thread du pool) ; ne lève jamais."""
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
            extension=file_type_for(path),
            file_type=file_type_for(path),
            size_bytes=path.stat().st_size if path.exists() else 0,
            status=FileStatus.IGNORED,
            error_message=t("error.no_extractor", ext=path.suffix),
        )
    else:
        result = extractor_cls.safe_extract(
            path, relative_path, extract_images=extract_embedded_images
        )
    return idx, result


def _extract_all(
    inventory_entries: Sequence[InventoryEntry],
    emitter: ProgressEmitter | None,
    extract_embedded_images: bool,
) -> dict[int, ExtractedFile] | None:
    """Extraction parallèle bornée (`MAX_WORKERS`) dans le pool partagé
    (`core/workers.py` : processus, threads en repli), progression émise à
    chaque fichier terminé. Rend `None` si l'émetteur a été annulé en cours
    de route. Un pool de processus cassé en plein lot (travailleur tué) ne
    perd aucun fichier : ce qui n'était pas rendu est refait par threads."""
    total_files = len(inventory_entries)
    results_map: dict[int, ExtractedFile] = {}
    pending = dict(enumerate(inventory_entries))
    while pending:
        pool = extraction_pool()
        lang = get_language()
        futures: dict[Future[tuple[int, ExtractedFile]], int] = {
            pool.submit(
                _extract_task, lang, i, entry.path, entry.relative_path, extract_embedded_images
            ): i
            for i, entry in pending.items()
        }
        try:
            for future in as_completed(futures):
                if emitter and emitter.is_cancelled:
                    pool.cancel_pending()
                    break
                idx, result = future.result()
                results_map[idx] = result
                del pending[idx]
                if emitter:
                    # D-099 : `current` = nombre de fichiers terminés (monotone),
                    # pas l'index d'inventaire — les extractions finissent dans
                    # le désordre et la barre reculait.
                    emitter.emit(
                        ProgressEvent(
                            file_path=result.relative_path,
                            current=len(results_map),
                            total=total_files,
                            status=result.status.value,
                            message=result.error_message,
                        )
                    )
        except BrokenProcessPool as exc:
            pool.broken(str(exc) or type(exc).__name__)
            continue  # les fichiers encore dans `pending` repartent, par threads
        break
    if emitter and emitter.is_cancelled:
        logger.info("Analyse annulée après %d fichier(s)", len(results_map))
        return None
    return results_map


def _extract_task(
    lang: str, idx: int, path: Path, relative_path: str, extract_embedded_images: bool
) -> tuple[int, ExtractedFile]:
    """`_extract_one` tel que le pool l'exécute : dans un processus, la langue
    des messages n'est pas héritée du parent — elle voyage avec la tâche."""
    set_language(lang)
    return _extract_one(idx, path, relative_path, extract_embedded_images)


def _qualify_and_count(
    files: list[ExtractedFile],
    thresholds: _ScanThresholds,
    margin: float,
    engine: TokenizerEngine,
) -> list[TokenEstimate]:
    """Statut images/texte pauvre (C-08), secrets, doublons, noms d'images, puis
    compteur par fichier (en-têtes SOURCE comprises, CdC §8.2 §10.1)."""
    from docfuse.output.source_header import estimate_source_context

    for f in files:
        if f.status.is_extracted():  # M-03: simplifié, is_extracted suffit
            f.status = determine_status(
                text=f.text,
                image_count=f.image_count,
                chars_per_page=f.chars_per_page or None,
                min_chars_file=thresholds.min_chars_file,
                min_chars_per_page=thresholds.min_chars_per_page,
                sparse_page_chars=thresholds.sparse_page_chars,
                sparse_page_ratio=thresholds.sparse_page_ratio,
            )

    # Alerte secrets potentiels (non bloquant, ne modifie jamais le texte).
    for f in files:
        if not f.status.is_extracted():
            continue
        findings = scan_for_secrets(f.text)
        if findings:
            f.extra_metadata["secrets_detected"] = _secrets_note(findings)

    # Doublons de contenu entre fichiers (avant comptage : le texte d'un doublon
    # est remplacé par une note, donc compté correctement).
    detect_duplicates(files)

    # Deux documents homonymes (`rapport.docx` dans deux sous-dossiers)
    # produisent les mêmes noms d'images exportées : renommage avant comptage,
    # tag et fichier restent cohérents (D-099).
    renamed = dedupe_image_filenames(files)
    if renamed:
        logger.warning("%d image(s) intégrée(s) renommée(s) pour éviter une collision", renamed)

    return [
        estimate_source_context(f, margin, engine)
        if f.status.is_extracted()
        else TokenEstimate(0, 0, 0)
        for f in files
    ]


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
    max_depth: int = MAX_TRAVERSAL_DEPTH,
    tokenizer_engine: str = DEFAULT_TOKENIZER_ENGINE,
    extract_embedded_images: bool = False,
    split_context: bool = False,
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
        split_context: Mode « découpage » (D-101) : ne bloque jamais, le
            corpus est réparti en plusieurs fichiers sous le plafond (voir
            `generate_corpus_parts` et `core.splitter`).

    Returns:
        OrchestratorResult avec les fichiers, estimations, statut de blocage.
    """
    exclude_globs = exclude_globs or []
    selection = InputSelection.from_value(input_path)
    engine = resolve_engine(tokenizer_engine)

    thresholds = _scan_thresholds(scan_config)

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
        return OrchestratorResult(
            files, ignored, [], total, context_limit, margin, engine, split_context=split_context
        )

    results_map = _extract_all(inventory_entries, emitter, extract_embedded_images)
    if results_map is None:
        # D-099 : résultat jeté par l'appelant de toute façon — inutile de
        # scanner, dédupliquer et compter ce qui a été extrait avant l'arrêt.
        return OrchestratorResult(
            [],
            ignored,
            [],
            TokenEstimate(0, 0, 0),
            context_limit,
            margin,
            engine,
            cancelled=True,
            split_context=split_context,
        )

    # Remettre dans l'ordre original (tri par inventaire)
    files = [results_map[i] for i in range(total_files)]

    estimates = _qualify_and_count(files, thresholds, margin, engine)

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
        split_context=split_context,
    )

    logger.info(
        "Analyse terminée : %d fichiers, %d tokens estimés, %d avec marge, blocage=%s",
        len(files),
        total.tokens_estimated,
        total.tokens_with_margin,
        orchestrator_result.is_blocked,
    )

    return orchestrator_result


def _secrets_note(findings: list[tuple[str, int]]) -> str:
    """Note « secrets potentiels » groupée par type, numéros de ligne
    plafonnés (D-099). Avant : une entrée par occurrence — un journal
    contenant 40 000 jetons produisait une note de 1,5 Mo, comptée dans
    les tokens de l'en-tête SOURCE."""
    by_kind: dict[str, list[int]] = {}
    for kind_key, line in findings:
        by_kind.setdefault(kind_key, []).append(line)

    parts: list[str] = []
    for kind_key, lines in by_kind.items():
        shown = lines[:SECRETS_NOTE_MAX_LINES_PER_KIND]
        note = t("secret.finding_lines", kind=t(kind_key), lines=", ".join(str(n) for n in shown))
        if len(lines) > len(shown):
            note += " " + t("secret.finding_more", count=len(lines) - len(shown))
        parts.append(note)
    return "; ".join(parts)


def generate_corpus(result: OrchestratorResult, output_path: Path) -> bool:
    """Génère le corpus final (Markdown ou PDF) + rapport.

    Plafond et marge sont ceux du résultat (`result.context_limit`,
    `result.margin`) — D-099 : les anciens paramètres en doublon pouvaient
    diverger de ce qui avait réellement servi au blocage.

    Args:
        result: Résultat de l'analyse.
        output_path: Chemin du fichier de sortie.

    Returns:
        True si le corpus a été généré, False si bloqué. En mode découpage
        (`result.split_context`, D-101), délègue à `generate_corpus_parts` :
        les fichiers `<stem>_001.<ext>`, `<stem>_002.<ext>`… sont écrits à la
        place de `output_path` et True est renvoyé dès qu'une partie existe.
    """
    if result.split_context:
        return bool(generate_corpus_parts(result, output_path))

    if result.is_blocked:
        logger.warning("Génération bloquée : %s", result.block_reason)
        write_report_pair(result, report_base_path(output_path))
        return False

    _write_corpus_file(result, output_path)
    _write_images_and_reports(result, output_path)
    logger.info("Corpus généré : %s", output_path)
    return True


def generate_corpus_parts(result: OrchestratorResult, output_path: Path) -> list[Path]:
    """Génère le corpus en plusieurs parties sous le plafond (D-101).

    Chaque partie devient `<stem>_NNN.<ext>` à côté de `output_path` (qui
    n'est pas écrit lui-même) : `corpus.md` → `corpus_001.md`,
    `corpus_002.md`… Les images intégrées et le rapport (unique, avec la
    partie de chaque fichier) sont écrits à côté, sous le nom de base.

    Args:
        result: Résultat de l'analyse (`split_context` ou non : la répartition
            se fait avec `result.context_limit`).
        output_path: Chemin de base du corpus (`.md` ou `.pdf`).

    Returns:
        Chemins des parties écrites, dans l'ordre. Vide si aucun fichier
        extrait (le rapport est quand même écrit).
    """
    from docfuse.core.splitter import split_by_budget

    parts = split_by_budget(result)
    ext = output_path.suffix.lower()
    if ext not in (".md", ".pdf"):
        raise ValueError(f"Format de sortie non supporté : {ext}")

    written: list[Path] = []
    for part in parts:
        part_path = output_path.with_name(f"{output_path.stem}_{part.index:03d}{ext}")
        _write_corpus_file(result, part_path, part=part, parts_total=len(parts))
        written.append(part_path)

    _write_images_and_reports(result, output_path, parts=parts)
    logger.info("Corpus généré en %d partie(s) : %s", len(written), output_path.parent)
    return written


def _write_corpus_file(
    result: OrchestratorResult,
    output_path: Path,
    *,
    part: CorpusPart | None = None,
    parts_total: int = 1,
) -> None:
    """Écrit un fichier de corpus (Markdown ou PDF) — entier ou une partie."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ext = output_path.suffix.lower()
    if ext == ".md":
        from docfuse.output.markdown_writer import write_markdown_corpus

        write_markdown_corpus(
            result, output_path, result.margin, part=part, parts_total=parts_total
        )
    elif ext == ".pdf":
        from docfuse.output.pdf_writer import write_pdf_corpus

        write_pdf_corpus(result, output_path, result.margin, part=part, parts_total=parts_total)
    else:
        raise ValueError(f"Format de sortie non supporté : {ext}")


def _write_images_and_reports(
    result: OrchestratorResult, output_path: Path, *, parts: list[CorpusPart] | None = None
) -> None:
    from docfuse.output.image_writer import write_embedded_images

    images_written = write_embedded_images(result.files, output_path)
    if images_written:
        logger.info("%d image(s) intégrée(s) exportée(s) à côté de %s", images_written, output_path)

    write_report_pair(result, report_base_path(output_path), parts=parts)
