"""Internationalisation : catalogue de chaînes FR/EN.

CdC §15 — Toutes les chaînes UI, CLI, rapport via catalogue.
v1 : FR complet, EN amorcé. Ajout d'une langue = ajout d'un fichier JSON.
Le contenu extrait n'est pas traduit.
Formats nombres : espaces insécables FR (96 830).
"""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CATALOGS: dict[str, dict[str, str]] = {}
_CURRENT_LANG: str = "fr"


def _load_catalog(lang: str) -> dict[str, str]:
    """Charge un catalogue de langue depuis le fichier JSON."""
    if lang in _CATALOGS:
        return _CATALOGS[lang]

    catalog_dir = Path(__file__).resolve().parent / "i18n"
    catalog_file = catalog_dir / f"{lang}.json"

    if not catalog_file.exists():
        logger.warning("Catalogue i18n introuvable : %s", catalog_file)
        return {}

    try:
        data = json.loads(catalog_file.read_text(encoding="utf-8"))
        catalog = {k: str(v) for k, v in data.items()}
        _CATALOGS[lang] = catalog
        return catalog
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Erreur chargement i18n %s : %s", catalog_file, exc)
        return {}


def set_language(lang: str) -> None:
    """Change la langue active."""
    global _CURRENT_LANG
    _CURRENT_LANG = lang


def t(key: str, **kwargs: object) -> str:
    """Traduit une clé dans la langue active.

    Si la clé n'existe pas, retourne la clé elle-même.
    Supporte les placeholders {name}.

    Args:
        key: Clé de traduction.
        **kwargs: Valeurs de substitution.

    Returns:
        Chaîne traduite.
    """
    catalog = _load_catalog(_CURRENT_LANG)
    text = catalog.get(key, key)

    # Substitution des placeholders
    if kwargs:
        with contextlib.suppress(KeyError, IndexError):
            text = text.format(**{k: str(v) for k, v in kwargs.items()})

    return text


def format_number(value: int) -> str:
    """Formate un nombre selon la langue active (espaces insécables FR)."""
    if _CURRENT_LANG == "fr":
        return f"{value:,}".replace(",", "\u00a0")
    return f"{value:,}"
