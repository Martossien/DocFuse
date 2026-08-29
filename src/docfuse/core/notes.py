"""Notes de transparence (extra_metadata) partagées entre l'en-tête SOURCE
et le rapport MD — même libellé, même ordre, un seul endroit à maintenir.
"""

from __future__ import annotations

from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile

# Ordre d'affichage, du plus important au moins important. Chaque entrée =
# (clé extra_metadata, clé i18n du libellé).
_EXTRA_METADATA_LABELS: list[tuple[str, str]] = [
    ("secrets_detected", "source_header.secrets_detected"),
    ("duplicate_of", "source_header.duplicate_of"),
    ("markdown_base64_stripped", "source_header.markdown_base64_stripped"),
    ("pdf_dedup", "source_header.pdf_dedup"),
    ("ocr", "source_header.ocr"),
]


def ordered_notes(file: ExtractedFile) -> list[str]:
    """Notes de transparence d'un fichier, formatées `libellé: valeur`.

    Args:
        file: Fichier extrait dont on lit `extra_metadata`.

    Returns:
        Liste de chaînes prêtes à afficher, dans l'ordre de priorité fixe
        ci-dessus. Vide si `extra_metadata` ne contient aucune clé connue.
    """
    notes = []
    for metadata_key, label_key in _EXTRA_METADATA_LABELS:
        value = file.extra_metadata.get(metadata_key)
        if value:
            notes.append(f"{t(label_key)}: {value}")
    return notes
