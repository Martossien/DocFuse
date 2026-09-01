"""Fonctions pures de la GUI : testables sans ouvrir de fenêtre.

Aucun import de `customtkinter` ni de `tkinter` ici — c'est la règle qui
permet de tester la logique d'affichage (jauge, tri, résumé, chemins déposés)
sous une CI sans session graphique.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from docfuse.constants import DEFAULT_TOKENIZER_ENGINE, GAUGE_COLORS, GAUGE_WARNING_RATIO
from docfuse.core.orchestrator import OrchestratorResult
from docfuse.i18n import format_number, t
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)

_BRACE_PATTERN = re.compile(r"\{([^}]+)\}")
"""Chemins déposés contenant des espaces : `{C:\\My Path\\file.txt}` (tkdnd)."""


def widget_state(enabled: bool) -> str:
    """`normal`/`disabled` pour `configure(state=...)`."""
    return "normal" if enabled else "disabled"


def parse_context_limit(raw: str, fallback: int) -> int:
    """Plafond saisi dans le champ texte : entier strictement positif, sinon
    `fallback` (D-099, fonction pure testable sans fenêtre)."""
    try:
        value = int(raw.strip())
    except ValueError:
        return fallback
    return value if value > 0 else fallback


def gauge_color(ratio: float) -> str:
    """Couleur de la jauge de contexte (I-11) pour un ratio tokens/plafond."""
    if ratio >= 1.0:
        return GAUGE_COLORS["blocked"]
    if ratio >= GAUGE_WARNING_RATIO:
        return GAUGE_COLORS["warning"]
    return GAUGE_COLORS["ok"]


def build_summary_lines(result: OrchestratorResult) -> list[str]:
    """Lignes du résumé sous le compteur (I-21, CdC §6.1) — fonction pure.

    Le message de blocage est celui calculé par `recompute_blocking()`
    (D-099 : la GUI le reconstruisait à part, avec un plafond qui pouvait
    différer de celui du blocage).
    """
    lines: list[str] = []
    ready_count = result.count_base_status(FileStatus.READY)
    if result.split_context:
        # D-101 : le plafond ne bloque plus, on annonce la répartition.
        from docfuse.core.splitter import split_by_budget

        parts = split_by_budget(result)
        if ready_count > 0:
            lines.append(
                t(
                    "summary.split",
                    count=ready_count,
                    parts=len(parts),
                    limit=format_number(result.context_limit),
                )
            )
        if result.oversized_files:
            lines.append(t("summary.split_oversized", count=len(result.oversized_files)))
    elif ready_count > 0 and not result.is_blocked:
        lines.append(t("summary.ok", count=ready_count, limit=format_number(result.context_limit)))
    images_count = result.count_base_status(FileStatus.IMAGES)
    if images_count > 0:
        lines.append(t("summary.images", count=images_count))
    low_text_count = result.count_base_status(FileStatus.LOW_TEXT)
    if low_text_count > 0:
        lines.append(t("summary.low_text", count=low_text_count))
    if result.is_blocked and result.block_reason:
        lines.append(result.block_reason)
    return lines


def _sort_key_for_column(pair: tuple[Any, Any], column: str) -> Any:
    """Valeur de tri pour une colonne du tableau de fichiers (D-090)."""
    f, est = pair
    if column == "file":
        return f.relative_path.lower()
    if column == "type":
        return f.file_type.lower()
    if column == "text_estimated":
        return est.tokens_estimated if est is not None else 0
    if column == "context_margin":
        return est.tokens_with_margin if est is not None else 0
    if column == "status":
        # Sévérité (0 = ready), pas le libellé traduit : "Peu de texte"
        # doit se regrouper avec "Images"/"Erreur", pas se ranger avec un
        # tri alphabétique arbitraire du texte affiché.
        return f.status.severity
    return 0


def sort_file_pairs(
    pairs: list[tuple[Any, Any]], column: str | None, reverse: bool
) -> list[tuple[Any, Any]]:
    """Trie des paires (ExtractedFile, TokenEstimate) pour l'affichage GUI (D-090).

    Fonction pure (testable sans ouvrir de fenêtre), même esprit que
    `resolve_tokenizer_choice`. `column=None` (pas encore trié par
    l'utilisateur) renvoie l'ordre reçu tel quel — ordre natural du dossier.
    """
    if column is None:
        return pairs
    return sorted(pairs, key=lambda pair: _sort_key_for_column(pair, column), reverse=reverse)


def resolve_tokenizer_choice(label: str, label_to_id: dict[str, str]) -> str:
    """Traduit le libellé affiché dans le menu déroulant vers l'id du moteur.

    Fonction pure (testable sans ouvrir de fenêtre) : un libellé inconnu
    (ex: langue changée entre-temps) retombe sur l'approximation par défaut
    plutôt que de faire planter l'analyse.
    """
    return label_to_id.get(label, DEFAULT_TOKENIZER_ENGINE)


def _parse_dnd_paths(data: str) -> list[str]:
    """Parse les chemins déposés depuis l'événement DnD de tkinterdnd2.

    Les chemins avec espaces sont entre accolades : {C:\\My Path\\file.txt}
    Les chemins sans espaces sont séparés par des espaces.
    """
    paths: list[str] = []
    brace_matches = _BRACE_PATTERN.findall(data)
    if brace_matches:
        paths.extend(brace_matches)
        # Retirer les matches du data pour les chemins restants
        remaining = _BRACE_PATTERN.sub("", data).strip()
        if remaining:
            paths.extend(remaining.split())
    else:
        # Pas d'accolades — split par espaces
        paths.extend(data.strip().split())
    return [p for p in paths if p]


def open_folder(path: Path) -> None:
    """Ouvre un dossier dans l'explorateur de fichiers (multi-plateforme)."""
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        logger.warning("Impossible d'ouvrir le dossier: %s", path)
