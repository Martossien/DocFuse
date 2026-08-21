"""Registre des moteurs de comptage, dispatch par identifiant.

Même principe que `core/registry.py` pour les extracteurs : chaque moteur
s'enregistre avec un id stable, et `resolve_engine()` ne lève jamais
d'exception — un id inconnu ou un moteur indisponible retombe silencieusement
(avec un avertissement journalisé) sur `ApproxEngine`, qui est toujours
disponible. L'analyse ne doit jamais planter à cause d'un choix de moteur.
"""

from __future__ import annotations

import logging

from docfuse.core.tokenizers.approx import ApproxEngine
from docfuse.core.tokenizers.base import TokenizerEngine, TokenizerEngineInfo
from docfuse.core.tokenizers.mistral import MistralEngine
from docfuse.core.tokenizers.openai import OpenAIEngine

logger = logging.getLogger(__name__)

# Ordre d'enregistrement = ordre d'affichage. "approx" est toujours premier.
_ENGINES: list[TokenizerEngine] = [ApproxEngine(), MistralEngine(), OpenAIEngine()]


def resolve_engine(engine_id: str) -> TokenizerEngine:
    """Résout un identifiant de moteur en instance utilisable.

    Args:
        engine_id: Identifiant demandé (ex: "approx", "mistral").

    Returns:
        Le moteur correspondant s'il est connu et disponible, sinon
        `ApproxEngine()` — jamais d'exception.
    """
    for engine in _ENGINES:
        if engine.info.id == engine_id:
            if engine.is_available():
                return engine
            logger.warning("Moteur de comptage '%s' indisponible, repli sur 'approx'", engine_id)
            return _ENGINES[0]

    if engine_id != _ENGINES[0].info.id:
        logger.warning("Moteur de comptage inconnu '%s', repli sur 'approx'", engine_id)
    return _ENGINES[0]


def list_engines() -> list[TokenizerEngineInfo]:
    """Liste les moteurs disponibles dans cet environnement (approx toujours inclus)."""
    return [engine.info for engine in _ENGINES if engine.is_available()]
