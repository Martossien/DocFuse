"""Nom de l'application et tout ce qui en dérive (D-102).

Jusqu'en 0.1.x, le nom de code « CorpusOne » était écrit en dur à six
endroits du code (dossier de sortie, fichiers de config, journal, auteur
PDF, titre de fenêtre) et dans les specs PyInstaller. Ce module est
désormais **le seul** endroit qui connaît le nom : tout le reste en dérive.

Le nom par défaut est ``DocFuse``. Il se surcharge par la variable
d'environnement ``DOCFUSE_APP_NAME`` — lue à l'import, au démarrage de
l'exe ou du script — pour distribuer l'outil sous un autre nom (build
interne, marque blanche) sans toucher au code. Les specs PyInstaller lisent
la même variable pour nommer l'exécutable.

Compatibilité ascendante : une installation 0.1.x a pu laisser une config
``CorpusOne.json`` (à côté de l'exe ou dans ``%APPDATA%/CorpusOne``) et des
dossiers ``CorpusOne_output`` ; ``config.py`` les lit en repli et
``constants.IGNORE_PATTERNS`` ignore toujours les anciens noms de sortie.
Aucune chaîne de ce module ne passe par i18n : ce sont des identifiants,
pas du texte d'interface.
"""

from __future__ import annotations

import os
import re

DEFAULT_APP_NAME: str = "DocFuse"
"""Nom par défaut, utilisé si la variable d'environnement est absente ou vide."""

LEGACY_APP_NAME: str = "CorpusOne"
"""Ancien nom de code (0.1.x) — uniquement pour lire une config ou ignorer
une sortie héritées, jamais pour écrire."""

APP_NAME_ENV_VAR: str = "DOCFUSE_APP_NAME"

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def resolve_app_name(raw: str | None) -> str:
    """Nom d'application effectif à partir d'une valeur d'environnement.

    Un nom est accepté s'il peut servir de nom de fichier/dossier portable
    (lettres, chiffres, ``.``, ``_``, ``-``, 64 caractères max, pas de
    caractère initial spécial). Sinon — vide, espaces, séparateurs de
    chemin — on retombe sur ``DEFAULT_APP_NAME`` : un nom invalide ne doit
    jamais empêcher le lancement.
    """
    if raw is None:
        return DEFAULT_APP_NAME
    candidate = raw.strip()
    if not candidate or not _SAFE_NAME.match(candidate):
        return DEFAULT_APP_NAME
    return candidate


APP_NAME: str = resolve_app_name(os.environ.get(APP_NAME_ENV_VAR))
"""Nom de l'application (titre de fenêtre, rapports, nom de l'exe)."""

OUTPUT_DIR_NAME: str = f"{APP_NAME}_output"
"""Dossier de sortie par défaut, créé dans la source sélectionnée (I-13)."""

LEGACY_OUTPUT_DIR_NAME: str = f"{LEGACY_APP_NAME}_output"

CONFIG_FILENAME: str = f"{APP_NAME}.json"
"""Config portable, à côté de l'exécutable (CdC §5.2)."""

LEGACY_CONFIG_FILENAME: str = f"{LEGACY_APP_NAME}.json"

APPDATA_DIR_NAME: str = APP_NAME
"""Sous-dossier de %APPDATA% (ou ~/.config) pour la config utilisateur."""

LEGACY_APPDATA_DIR_NAME: str = LEGACY_APP_NAME

LOG_DIR_NAME: str = APP_NAME
"""Sous-dossier du répertoire temporaire pour le journal (CdC §18)."""

LOG_FILENAME: str = f"{APP_NAME.lower()}.log"

OCR_VARIANT_NAME: str = f"{APP_NAME}-OCR"
"""Nom de la variante d'exécutable avec Tesseract embarqué (D-067)."""

PDF_AUTHOR: str = APP_NAME
"""Métadonnée « auteur » des corpus PDF."""
