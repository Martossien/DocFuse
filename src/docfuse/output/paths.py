"""Chemins de sortie partagés par la CLI et la GUI (D-099).

Avant : la CLI écrivait `corpus.md` dans le dossier courant pour un fichier
unique en entrée, la GUI dans `<dossier du fichier>/CorpusOne_output/` ; le
suffixe `_rapport` et le nom du dossier de sortie étaient des littéraux
répétés dans trois modules. Un seul endroit à maintenir.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.constants import CORPUS_EXTENSIONS, OUTPUT_DIR_NAME, REPORT_SUFFIX
from docfuse.models.input_selection import InputSelection


def corpus_extension(output_format: str) -> str:
    """Extension (avec le point) du corpus pour un format (`md` → `.md`).

    Raises:
        ValueError: format inconnu — un appelant qui passe autre chose que
            `md`/`pdf` a un bug de validation en amont (`Config.validate()`,
            `choices=` d'argparse), on ne le masque pas.
    """
    try:
        return CORPUS_EXTENSIONS[output_format]
    except KeyError:
        raise ValueError(f"Format de sortie non supporté : {output_format}") from None


def default_corpus_path(selection: InputSelection, output_format: str) -> Path:
    """Chemin par défaut du corpus : `<source>/CorpusOne_output/corpus.<ext>`.

    `<source>` est le dossier sélectionné, ou le dossier du premier fichier
    pour une sélection de fichiers (I-13) — même règle CLI et GUI.
    """
    return selection.output_directory / OUTPUT_DIR_NAME / f"corpus{corpus_extension(output_format)}"


def report_base_path(output_path: Path) -> Path:
    """Base des rapports écrits à côté du corpus : `<stem>_rapport.md` (le
    JSON prend le même nom en `.json`, voir `core.report.write_report_pair`)."""
    return output_path.with_name(f"{output_path.stem}{REPORT_SUFFIX}.md")
