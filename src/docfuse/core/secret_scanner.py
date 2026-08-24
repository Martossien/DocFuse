"""Détection heuristique de secrets/identifiants potentiels dans le texte extrait.

DocFuse prépare un corpus destiné à être collé dans un chat LLM externe — un
`.env`, une clé API dans un fichier de config, une clé privée SSH glissés
involontairement dans la sélection partiraient tels quels vers un tiers.
Ce module ne bloque rien et ne modifie jamais le texte : il pose une alerte
non bloquante (CdC §9 — même esprit que les alertes images/pauvreté de
texte), pour que l'utilisateur puisse décider en connaissance de cause.

Volontairement conservateur (peu de motifs, à haute confiance) pour limiter
les faux positifs : mieux vaut manquer un secret exotique que noyer
l'utilisateur d'alertes sur du texte légitime.

Important : seul le *type* de secret détecté et son numéro de ligne sont
rapportés, jamais la valeur trouvée — le rapport lui-même pourrait sinon
devenir un vecteur de fuite (ex: committé par erreur dans un dépôt).
"""

from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("secret.kind_aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "secret.kind_private_key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"),
    ),
    ("secret.kind_slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    (
        "secret.kind_jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ),
    (
        "secret.kind_generic_api_key",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|client[_-]?secret)"
            r"\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+]{16,}"
        ),
    ),
]


def scan_for_secrets(text: str) -> list[tuple[str, int]]:
    """Recherche des motifs de secrets à haute confiance dans le texte.

    Args:
        text: Texte extrait à analyser.

    Returns:
        Liste de (clé i18n du type de secret, numéro de ligne 1-indexé),
        dans l'ordre d'apparition. Vide si rien détecté.
    """
    if not text:
        return []

    findings: list[tuple[str, int]] = []
    lines = text.split("\n")
    for line_number, line in enumerate(lines, 1):
        for kind_key, pattern in _PATTERNS:
            if pattern.search(line):
                findings.append((kind_key, line_number))

    return findings
