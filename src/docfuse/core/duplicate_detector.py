"""Détection de doublons de contenu entre fichiers.

Deux fichiers différents peuvent contenir un texte extrait strictement
identique (copie dans deux dossiers, export dupliqué, sauvegarde) — un cas
fréquent quand l'utilisateur sélectionne un dossier entier plutôt que des
fichiers un par un. Sans détection, ce contenu est compté et inclus deux
fois dans le corpus, gaspillant des tokens sans rien apporter.

CdC §8 — sans perte silencieuse : le fichier doublon reste visible dans la
liste et le rapport, mais son texte est remplacé par une note pointant vers
l'original plutôt que d'être répété.
"""

from __future__ import annotations

import hashlib

from docfuse.constants import DUPLICATE_MIN_CHARS
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile


def detect_duplicates(files: list[ExtractedFile]) -> None:
    """Marque les fichiers dont le texte extrait est identique à un précédent.

    Modifie les fichiers en place : le premier fichier d'un groupe de
    doublons (dans l'ordre de `files`, déjà trié par l'inventaire) reste
    inchangé et sert d'original ; les suivants voient leur `text` remplacé
    par une courte note et `extra_metadata["duplicate_of"]` renseigné.

    Args:
        files: Fichiers extraits (modifiés en place).
    """
    seen_hashes: dict[str, ExtractedFile] = {}

    for file in files:
        if not file.status.is_extracted():
            continue

        normalized = file.text.strip()
        if len(normalized) < DUPLICATE_MIN_CHARS:
            continue

        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        original = seen_hashes.get(digest)
        if original is None:
            seen_hashes[digest] = file
            continue

        file.extra_metadata["duplicate_of"] = original.relative_path
        file.text = t("duplicate.placeholder_text", original=original.relative_path)
