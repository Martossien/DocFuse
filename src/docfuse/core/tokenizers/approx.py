"""Moteur de comptage approximatif : octets UTF-8 / 4 (CdC §10).

Toujours disponible, aucune dépendance. Comportement identique à la formule
historique de DocFuse — ce moteur ne change rien pour les utilisateurs qui
ne choisissent pas explicitement un moteur précis.
"""

from __future__ import annotations

import math

from docfuse.constants import BYTES_PER_TOKEN
from docfuse.core.tokenizers.base import TokenizerEngine, TokenizerEngineInfo


class ApproxEngine(TokenizerEngine):
    """Approximation générique : ceil(octets_utf8 / 4)."""

    info = TokenizerEngineInfo(id="approx", label_key="tokenizer.approx")

    def is_available(self) -> bool:
        return True

    def count_tokens(self, text: str) -> int:
        return math.ceil(len(text.encode("utf-8")) / BYTES_PER_TOKEN)
