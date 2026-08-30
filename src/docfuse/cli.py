"""Interface en ligne de commande.

CdC §6.3 — Arguments et codes retour.
CdC §15 — Toutes les chaînes via i18n.

Codes retour :
  0 = Corpus généré (warnings images possibles)
  1 = Erreur technique
  2 = Blocage plafond de contexte
  3 = Aucun fichier supporté
  4 = Sortie / dossier non inscriptible
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from docfuse import __version__
from docfuse.branding import APP_NAME, LOG_DIR_NAME, LOG_FILENAME
from docfuse.config import load_config
from docfuse.constants import ALL_EXTENSIONS, CORPUS_EXTENSIONS, UNUSUAL_CONTEXT_LIMIT
from docfuse.core.orchestrator import (
    OrchestratorResult,
    generate_corpus,
    generate_corpus_parts,
    run_analysis,
)
from docfuse.core.registry import list_supported_extensions
from docfuse.core.report import write_report_pair
from docfuse.core.tokenizers.registry import list_engines
from docfuse.i18n import format_number, set_language, t
from docfuse.models.input_selection import InputSelection
from docfuse.output.paths import corpus_extension, default_corpus_path, report_base_path

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Construit le parser argparse avec chaînes i18n."""
    parser = argparse.ArgumentParser(
        prog="docfuse",
        description=t("app.title", app=APP_NAME),
    )

    parser.add_argument(
        "--input",
        "-i",
        action="append",
        required=False,
        help=t("cli.input"),
    )
    parser.add_argument(
        "--output",
        "-o",
        help=t("cli.output"),
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["md", "pdf"],
        default=None,
        help=t("cli.format"),
    )
    parser.add_argument(
        "--context",
        "-c",
        type=int,
        default=None,
        help=t("cli.context"),
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=None,
        help=t("cli.margin"),
    )
    parser.add_argument(
        "--tokenizer-engine",
        choices=["approx", "mistral", "openai"],
        default=None,
        help=t("cli.tokenizer_engine"),
    )
    parser.add_argument(
        "--list-tokenizers",
        action="store_true",
        help=t("cli.list_tokenizers"),
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        default=None,
        help=t("cli.recursive"),
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        default=False,
        help=t("cli.no_recursive"),
    )
    parser.add_argument(
        "--extract-images",
        action="store_true",
        default=None,
        help=t("cli.extract_images"),
    )
    parser.add_argument(
        "--split-context",
        action="store_true",
        default=None,
        help=t("cli.split_context"),
    )
    parser.add_argument(
        "--include-ext",
        action="append",
        help=t("cli.include_ext"),
    )
    parser.add_argument(
        "--exclude-glob",
        action="append",
        help=t("cli.exclude_glob"),
    )
    parser.add_argument(
        "--report",
        help=t("cli.report"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=t("cli.dry_run"),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help=t("cli.yes"),
    )
    parser.add_argument(
        "--force-images",
        action="store_true",
        help=t("cli.force_images"),
    )
    parser.add_argument(
        "--lang",
        help=t("cli.lang"),
    )
    parser.add_argument(
        "--config",
        type=Path,
        help=t("cli.config"),
    )
    parser.add_argument(
        "--list-formats",
        action="store_true",
        help=t("cli.list_formats"),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"docfuse {__version__}",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help=t("cli.verbose"),
    )

    return parser


def _write_report(result: OrchestratorResult, output_path: Path, report_path: str | None) -> None:
    """Écrit le rapport MD + JSON à un chemin personnalisé ou à côté de la sortie.

    CdC §6.3 --report : chemin personnalisé pour le rapport (le Markdown et
    le JSON prennent ce nom avec leur suffixe respectif).
    CdC §19.2 : dry-run génère un rapport même sans corpus.
    """
    base = Path(report_path) if report_path else report_base_path(output_path)
    write_report_pair(result, base)


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée de la CLI.

    Args:
        argv: Arguments (si None, utilise sys.argv).

    Returns:
        Code retour (0=OK, 1=erreur, 2=blocage, 3=aucun fichier, 4=non inscriptible).
    """
    # Pré-charger la config pour la langue avant de construire le parser
    pre_config = load_config(None)
    set_language(pre_config.lang)

    parser = build_parser()
    args = parser.parse_args(argv)

    # Logging
    log_level = logging.DEBUG if args.verbose else logging.INFO

    # CdC §18 — log fichier avec rotation 2 Mo, sans contenu des documents
    import tempfile
    from logging.handlers import RotatingFileHandler

    log_dir = Path(tempfile.gettempdir()) / LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILENAME

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stderr),
        RotatingFileHandler(
            str(log_file),
            maxBytes=2_000_000,
            backupCount=1,
            encoding="utf-8",
        ),
    ]
    logging.basicConfig(
        level=log_level, handlers=handlers, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    # --list-formats
    if args.list_formats:
        exts = sorted(list_supported_extensions())
        print(f"{t('cli.list_formats')}:")
        for ext in exts:
            print(f"  {ext}")
        return 0

    # --list-tokenizers
    if args.list_tokenizers:
        print(f"{t('cli.list_tokenizers')}:")
        for engine_info in list_engines():
            print(f"  {engine_info.id} — {t(engine_info.label_key)}")
        return 0

    # Charger la config (avec chemin explicite si fourni)
    config = load_config(args.config)
    # D-096 : `Config.validate()` existait mais n'était appelé nulle part —
    # un plafond négatif ou une marge absurde passaient sans un mot.
    config_errors = config.validate()
    if config_errors:
        for message in config_errors:
            print(f"{t('cli.config_invalid')}: {message}", file=sys.stderr)
        return 1

    # Surcharge par CLI
    if args.lang:
        set_language(args.lang)
    else:
        set_language(config.lang)

    context_limit = args.context if args.context is not None else config.context_limit
    margin = args.margin if args.margin is not None else config.margin
    tokenizer_engine = (
        args.tokenizer_engine if args.tokenizer_engine is not None else config.tokenizer_engine
    )
    recursive = (
        True
        if args.recursive
        else (not args.no_recursive if args.no_recursive else config.recursive)
    )
    exclude_globs = args.exclude_glob if args.exclude_glob is not None else config.exclude_globs
    output_format = args.format if args.format is not None else config.format
    extract_embedded_images = (
        args.extract_images if args.extract_images is not None else config.extract_embedded_images
    )
    # D-101 : découpage en plusieurs corpus au lieu de bloquer.
    split_context = args.split_context if args.split_context is not None else config.split_context

    # M-11: Avertissement au-delà de 1 000 000 tokens (CdC §10.3)
    if context_limit > UNUSUAL_CONTEXT_LIMIT:
        print(
            t("gui.unusual_limit", tokens=format_number(context_limit)),
            file=sys.stderr,
        )

    # C-06: --include-ext : surcharge des extensions
    extensions: frozenset[str] | None = None
    if args.include_ext:
        ext_list = [e if e.startswith(".") else f".{e}" for e in args.include_ext]
        extensions = frozenset(e.lower() for e in ext_list)
    else:
        extensions = ALL_EXTENSIONS

    # Input obligatoire. D-099 : `parser.error()` sortait avec le code 2,
    # réservé au blocage plafond (CdC §6.3) — un script appelant ne pouvait
    # pas distinguer « mauvais appel » de « corpus trop gros ».
    if not args.input:
        print(t("cli.input_missing"), file=sys.stderr)
        return 1

    # I-07: --input répétable : collecter tous les inputs
    input_paths = [Path(p) for p in args.input]
    for p in input_paths:
        if not p.exists():
            logger.error("Input path does not exist: %s", p)
            print(t("error.unknown") + f": {p}", file=sys.stderr)
            return 1

    selection = InputSelection.from_paths(input_paths)

    # Output
    if args.output:
        output_path = Path(args.output)
        actual_ext = output_path.suffix.lower()
        if actual_ext in CORPUS_EXTENSIONS.values():
            # I-20: l'extension de --output prime sur --format
            # Si --output foo.pdf --format md, on génère un PDF (extension .pdf prime)
            output_format = actual_ext.lstrip(".")
        elif actual_ext == "" or output_path.is_dir():
            # Pas d'extension : --output désigne un dossier (cas légitime :
            # l'utilisateur veut juste choisir où mettre le corpus).
            # On ajoute le suffixe attendu et on garantit que le dossier existe.
            output_path.mkdir(parents=True, exist_ok=True)
            output_path = output_path / f"corpus{corpus_extension(output_format)}"
        else:
            # D-099 : `--output notes.txt` créait un dossier `notes.txt/`.
            print(t("cli.output_bad_extension", path=output_path), file=sys.stderr)
            return 1
    else:
        # I-13: Sortie par défaut dans <App>_output/ — même règle que la
        # GUI (D-099 : un fichier seul en entrée écrivait dans le dossier
        # courant côté CLI, dans le dossier du fichier côté GUI).
        output_path = default_corpus_path(selection, output_format)

    # Vérifier que le dossier de sortie est inscriptible
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        test_file = output_path.parent / ".docfuse_write_test"
        test_file.touch()
        test_file.unlink()
    except (OSError, PermissionError):
        logger.error("Output dir not writable: %s", output_path.parent)
        print(t("exit.not_writable") + f": {output_path.parent}", file=sys.stderr)
        return 4

    # Tous les --input participent à une sélection unique et exacte.
    result = run_analysis(
        input_path=selection,
        context_limit=context_limit,
        margin=margin,
        recursive=recursive,
        exclude_globs=exclude_globs,
        extensions=extensions,
        scan_config=config.scan,
        sort=config.sort,
        max_depth=config.max_depth,
        tokenizer_engine=tokenizer_engine,
        extract_embedded_images=extract_embedded_images,
        split_context=split_context,
    )

    # Aucun fichier supporté
    if len(result.files) == 0:
        logger.error("No supported files found")
        print(t("exit.no_files"), file=sys.stderr)
        return 3

    # Blocage
    if result.is_blocked:
        if result.block_reason:
            print(f"{t('exit.blocked')}: {result.block_reason}", file=sys.stderr)
        if args.yes:
            # CdC §6.3 : --yes + dépassement → code 2, rapport éventuel oui
            _write_report(result, output_path, args.report)
            return 2

    # Dry-run : analyse seule, mais rapport généré (CdC §19.2)
    if args.dry_run:
        print(f"{t('gui.analyze')}: {len(result.files)}")
        print(f"{t('counter.estimated')}: {format_number(result.total.tokens_estimated)}")
        print(f"{t('counter.with_margin')}: {format_number(result.total.tokens_with_margin)}")
        print(f"{t('counter.limit')}: {format_number(context_limit)}")
        # C-05: Générer le rapport même en dry-run
        _write_report(result, output_path, args.report)
        return 0 if not result.is_blocked else 2

    # Génération
    if split_context:
        # D-101 : plusieurs fichiers `<stem>_NNN.<ext>`, jamais de code 2.
        part_paths = generate_corpus_parts(result, output_path)
        if args.report:
            _write_report(result, output_path, args.report)
        for part_path in part_paths:
            print(t("gui.corpus_generated", path=str(part_path)))
        print(t("gui.corpus_parts_generated", count=len(part_paths), path=str(output_path.parent)))
        print(f"{t('counter.estimated')}: {format_number(result.total.tokens_estimated)}")
        print(f"{t('counter.with_margin')}: {format_number(result.total.tokens_with_margin)}")
        return 0

    success = generate_corpus(result, output_path)
    if not success:
        return 2

    # C-07: Rapport avec chemin personnalisé si --report
    if args.report:
        _write_report(result, output_path, args.report)

    print(t("gui.corpus_generated", path=str(output_path)))
    print(f"{t('counter.estimated')}: {format_number(result.total.tokens_estimated)}")
    print(f"{t('counter.with_margin')}: {format_number(result.total.tokens_with_margin)}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(1)
