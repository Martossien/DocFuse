"""Formateur d'en-tête SOURCE pour chaque fichier du corpus.

CdC §8.2 — En-tête de source (anti-perte de provenance) :

    ---
    ## SOURCE: rapports/2024/contrat.docx
    - type: docx
    - taille_octets: 184320
    - pages_ou_diapos: 12
    - tokens_estimes: 4200
    - tokens_avec_marge: 4830
    - images: 4
    - alerte: images
    ---

Ces métadonnées **comptent** dans le compteur de contexte.
"""

from __future__ import annotations

from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus


def build_source_header(
    file: ExtractedFile,
    margin: float = 0.15,
    tokens_estimated: int | None = None,
    tokens_with_margin: int | None = None,
) -> str:
    """Construit l'en-tête SOURCE pour un fichier.

    Args:
        file: Fichier extrait.
        margin: Marge appliquée (pour info dans l'en-tête).
        tokens_estimated: Tokens estimés (si déjà calculé, sinon calculé ici).
        tokens_with_margin: Tokens avec marge (si déjà calculé).

    Returns:
        Chaîne Markdown de l'en-tête SOURCE.
    """
    from docfuse.core.context_counter import estimate_tokens

    if tokens_estimated is None or tokens_with_margin is None:
        est = estimate_tokens(file.text, margin)
        tokens_estimated = est.tokens_estimated
        tokens_with_margin = est.tokens_with_margin

    lines: list[str] = []
    lines.append("---")
    lines.append(f"## SOURCE: {file.relative_path}")
    lines.append(f"- type: {file.file_type}")
    lines.append(f"- taille_octets: {file.size_bytes}")
    if file.page_count > 0:
        lines.append(f"- pages_ou_diapos: {file.page_count}")
    lines.append(f"- tokens_estimes: {tokens_estimated}")
    lines.append(f"- tokens_avec_marge: {tokens_with_margin}")
    if file.image_count > 0:
        lines.append(f"- images: {file.image_count}")

    # Alerte
    alert = _alert_label(file.status)
    if alert:
        lines.append(f"- alerte: {alert}")

    if file.encoding:
        lines.append(f"- encodage: {file.encoding}")

    lines.append("---")
    return "\n".join(lines)


def _alert_label(status: FileStatus) -> str:
    """Label d'alerte pour l'en-tête SOURCE."""
    if status is FileStatus.IMAGES:
        return "images"
    if status is FileStatus.LOW_TEXT:
        return "peu_de_texte"
    return ""


def adaptive_backticks(content: str) -> str:
    """Compte le nombre de backticks nécessaires pour ne pas casser un bloc.

    Si le contenu contient ```` ``` ````, on utilise 4 backticks, etc.
    Inspiré de files-to-prompt (cli.py:90-92).

    Args:
        content: Contenu à encadrer.

    Returns:
        Chaîne de backticks (au minimum 3).
    """
    backticks = "```"
    while backticks in content:
        backticks += "`"
    return backticks
