"""Glisser-déposer via `tkinterdnd2` (C-10, D-096) — optionnel.

`tkinterdnd2` est un extra : absent, la GUI fonctionne avec les seuls boutons.
Importer ce module ne lève jamais.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _try_import_dnd() -> tuple[bool, Any]:
    """Tente d'importer tkinterdnd2. Retourne (disponible, module ou None)."""
    try:
        import tkinterdnd2

        return True, tkinterdnd2
    except ImportError:
        return False, None


DND_AVAILABLE, dnd_module = _try_import_dnd()


def load_tkdnd(root: Any) -> bool:
    """Charge le paquet Tcl `tkdnd` dans l'interpréteur de `root` (D-096).

    Importer `tkinterdnd2` ne fait que greffer `drop_target_register`/
    `dnd_bind` sur les widgets Tk ; le côté Tcl (`package require tkdnd`)
    n'est chargé que par `TkinterDnD.require(root)`, jamais appelé jusqu'ici.
    Résultat : `drop_target_register` levait `TclError: invalid command name
    "tkdnd::drop_target"`, avalé par le `except` de `_setup_drag_and_drop`,
    et le glisser-déposer annoncé dans le README n'a jamais fonctionné —
    le message « fallback sur bouton uniquement » apparaissait à chaque
    lancement sans alerter personne.
    """
    if dnd_module is None:
        return False
    try:
        dnd_module.TkinterDnD.require(root)
        return True
    except Exception:
        logger.warning("Bibliothèque tkdnd introuvable, glisser-déposer désactivé", exc_info=True)
        return False
