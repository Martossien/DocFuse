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

from docfuse.constants import DEFAULT_LANG

logger = logging.getLogger(__name__)

_CATALOGS: dict[str, dict[str, str]] = {}
_CURRENT_LANG: str = DEFAULT_LANG


def _load_catalog(lang: str) -> dict[str, str]:
    """Charge un catalogue de langue depuis le fichier JSON.

    D-099 : un catalogue absent ou illisible est mis en cache vide — avant,
    chaque appel à `t()` dans une langue inconnue (`--lang de`) retentait
    la lecture du disque et journalisait le même avertissement.
    """
    if lang in _CATALOGS:
        return _CATALOGS[lang]

    catalog_file = Path(__file__).resolve().parent / "i18n" / f"{lang}.json"
    catalog: dict[str, str] = {}
    if not catalog_file.exists():
        logger.warning("Catalogue i18n introuvable : %s", catalog_file)
    else:
        try:
            data = json.loads(catalog_file.read_text(encoding="utf-8"))
            catalog = {k: str(v) for k, v in data.items()}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Erreur chargement i18n %s : %s", catalog_file, exc)
    _CATALOGS[lang] = catalog
    return catalog


def set_language(lang: str) -> None:
    """Change la langue active."""
    global _CURRENT_LANG
    _CURRENT_LANG = lang


def get_language() -> str:
    """Langue active (à transmettre aux processus d'extraction, D-111)."""
    return _CURRENT_LANG


def t(key: str, **kwargs: object) -> str:
    """Traduit une clé dans la langue active.

    Une clé absente de la langue active est cherchée dans `DEFAULT_LANG`
    (catalogue de référence, complet), puis renvoyée telle quelle. Supporte
    les placeholders {name}.

    Args:
        key: Clé de traduction.
        **kwargs: Valeurs de substitution.

    Returns:
        Chaîne traduite.
    """
    text = _load_catalog(_CURRENT_LANG).get(key)
    if text is None and _CURRENT_LANG != DEFAULT_LANG:
        text = _load_catalog(DEFAULT_LANG).get(key)
    if text is None:
        text = key

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
