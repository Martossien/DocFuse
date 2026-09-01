"""Interface graphique CustomTkinter (extra `docfuse[gui]`) — paquet.

Découpage (0.2.1) de l'ancien `gui.py` monolithique (1 136 lignes) :

- `docfuse.gui.app`     : la fenêtre (`DocFuseGUI`) et `launch()` ;
- `docfuse.gui.helpers` : fonctions pures (jauge, tri, résumé, chemins DnD),
  testables sans ouvrir de fenêtre ;
- `docfuse.gui.dnd`     : glisser-déposer via `tkinterdnd2` (optionnel).

`from docfuse.gui import launch, gauge_color, …` continue de fonctionner :
les noms publics de l'ancien module sont réexportés ici. `customtkinter` n'est
importé qu'à la construction de la fenêtre — importer ce paquet sans l'extra
`gui` ne lève rien (voir `docfuse.__main__`).
"""

from __future__ import annotations

from docfuse.gui.helpers import (
    _parse_dnd_paths,
    build_summary_lines,
    gauge_color,
    parse_context_limit,
    resolve_tokenizer_choice,
    sort_file_pairs,
)


def launch() -> None:
    """Lance la GUI (import différé : le cœur s'importe sans Tk).

    `DOCFUSE_GUI_SMOKE=1` : construit la fenêtre complète puis la ferme après
    un court délai — contrôle d'un exécutable empaqueté par la CI.
    """
    from docfuse.gui.app import launch as _launch

    _launch()


__all__ = [
    "_parse_dnd_paths",
    "build_summary_lines",
    "gauge_color",
    "launch",
    "parse_context_limit",
    "resolve_tokenizer_choice",
    "sort_file_pairs",
]
