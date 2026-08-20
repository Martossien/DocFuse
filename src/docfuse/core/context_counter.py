"""Compteur de contexte générique.

CdC §10 — Formule unique :
  octets_utf8 = nombre d'octets UTF-8 du texte qui irait au LLM
  tokens_estimes = ceil(octets_utf8 / 4)
  tokens_avec_marge = ceil(tokens_estimes * (1 + margin))

La marge par défaut est +15 % (0.15).

Interdit : appeler une API pour compter. Pas de tiktoken requis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from docfuse.constants import BYTES_PER_TOKEN, DEFAULT_MARGIN


@dataclass(frozen=True)
class TokenEstimate:
    """Estimation de tokens pour un texte donné.

    Attributes:
        bytes_utf8: Nombre d'octets UTF-8 du texte.
        tokens_estimated: Estimation brute (octets / 4).
        tokens_with_margin: Estimation + marge (brut * (1 + margin)).
    """

    bytes_utf8: int
    tokens_estimated: int
    tokens_with_margin: int


def estimate_tokens(text: str, margin: float = DEFAULT_MARGIN) -> TokenEstimate:
    """Estime le nombre de tokens d'un texte.

    Args:
        text: Texte à estimer (UTF-8 en interne).
        margin: Marge à appliquer (défaut 0.15 = +15 %).

    Returns:
        TokenEstimate avec les trois valeurs.
    """
    bytes_utf8 = len(text.encode("utf-8"))
    tokens_estimated = math.ceil(bytes_utf8 / BYTES_PER_TOKEN)
    tokens_with_margin = math.ceil(tokens_estimated * (1.0 + margin))
    return TokenEstimate(
        bytes_utf8=bytes_utf8,
        tokens_estimated=tokens_estimated,
        tokens_with_margin=tokens_with_margin,
    )


def check_limit(
    tokens_with_margin: int,
    context_limit: int,
) -> bool:
    """Vérifie si un nombre de tokens dépasse le plafond.

    CdC §10.2 : égalité (= L) passe ; strictement supérieur bloque.

    Args:
        tokens_with_margin: Tokens estimés + marge.
        context_limit: Plafond de contexte.

    Returns:
        True si le plafond est respecté (OK), False si dépassé (blocage).
    """
    return tokens_with_margin <= context_limit


def aggregate_tokens(
    estimates: list[TokenEstimate],
    margin: float = DEFAULT_MARGIN,
) -> TokenEstimate:
    """Agrège plusieurs estimations en une seule (pour le total du corpus).

    Args:
        estimates: Liste d'estimations par fichier.
        margin: Marge appliquée au corpus complet.

    Returns:
        TokenEstimate agrégée (total).
    """
    total_bytes = sum(e.bytes_utf8 for e in estimates)
    total_estimated = math.ceil(total_bytes / BYTES_PER_TOKEN)
    total_with_margin = math.ceil(total_estimated * (1.0 + margin))
    return TokenEstimate(
        bytes_utf8=total_bytes,
        tokens_estimated=total_estimated,
        tokens_with_margin=total_with_margin,
    )
