"""Interface commune des moteurs de comptage de tokens.

CdC §10 — Le moteur "approx" (octets/4) reste le défaut. Les moteurs précis
(ex: Mistral) sont optionnels, découverts par `core/tokenizers/registry.py`,
et ne doivent jamais faire planter l'analyse : une indisponibilité retombe
sur "approx" avec un avertissement journalisé (voir `resolve_engine`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenizerEngineInfo:
    """Métadonnées d'affichage d'un moteur de comptage.

    Attributes:
        id: Identifiant stable (CLI --tokenizer-engine, config JSON, rapport).
        label_key: Clé i18n du libellé affiché (GUI, --list-tokenizers).
    """

    id: str
    label_key: str


class TokenizerEngine(ABC):
    """Un moteur de comptage de tokens, précis ou approximatif."""

    info: TokenizerEngineInfo

    @abstractmethod
    def is_available(self) -> bool:
        """Indique si le moteur peut être utilisé dans cet environnement."""

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Compte le nombre de tokens d'un texte selon ce moteur."""
