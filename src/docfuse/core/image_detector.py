"""Détection d'images et de pauvreté de texte.

CdC §9 — Deux niveaux d'alerte, cumulables :
  1. Warning images : au moins une image détectée ET texte non sous le seuil critique.
  2. Alerte importante : peu ou pas de texte extractible (scan probable).
"""

from __future__ import annotations

from docfuse.constants import (
    SCAN_MIN_CHARS_FILE,
    SCAN_MIN_CHARS_PER_PAGE,
    SCAN_SPARSE_PAGE_CHARS,
    SCAN_SPARSE_PAGE_RATIO,
)
from docfuse.models.file_status import FileStatus


def check_low_text(
    text: str,
    chars_per_page: list[int] | None = None,
    image_count: int = 0,
    min_chars_file: int = SCAN_MIN_CHARS_FILE,
    min_chars_per_page: int = SCAN_MIN_CHARS_PER_PAGE,
    sparse_page_chars: int = SCAN_SPARSE_PAGE_CHARS,
    sparse_page_ratio: float = SCAN_SPARSE_PAGE_RATIO,
) -> bool:
    """Détecte si un fichier a peu ou pas de texte extractible (scan probable).

    CdC §9.2 — Critères :
    - texte extractible (espaces normalisés) < 80 caractères, OU
    - PDF : moyenne < 50 caractères par page, OU
    - PDF : ≥ 30 % des pages avec < 20 caractères ET présence d'images.

    Args:
        text: Texte extrait du fichier.
        chars_per_page: Liste du nombre de caractères par page (PDF).
        image_count: Nombre d'images détectées dans le fichier.
        min_chars_file: Seuil minimum de caractères par fichier.
        min_chars_per_page: Seuil minimum moyen de caractères par page.
        sparse_page_chars: Seuil pour qu'une page soit « sparse ».
        sparse_page_ratio: Ratio minimum de pages sparse.

    Returns:
        True si le fichier est en alerte importante (peu/pas de texte).
    """
    normalized_text = text.strip()
    char_count = len(normalized_text)

    # Critère 1 : texte total < seuil fichier
    if char_count < min_chars_file:
        return True

    # Critères spécifiques PDF (si chars_per_page fourni)
    if chars_per_page:
        total_pages = len(chars_per_page)
        if total_pages > 0:
            # Critère 2 : moyenne < seuil par page
            avg_chars = sum(chars_per_page) / total_pages
            if avg_chars < min_chars_per_page:
                return True

            # Critère 3 : ≥ 30 % de pages sparse + images présentes
            sparse_pages = sum(1 for c in chars_per_page if c < sparse_page_chars)
            if image_count > 0 and sparse_pages / total_pages >= sparse_page_ratio:
                return True

    return False


def determine_status(
    text: str,
    image_count: int,
    chars_per_page: list[int] | None = None,
    is_ignored: bool = False,
    has_error: bool = False,
    min_chars_file: int = SCAN_MIN_CHARS_FILE,
    min_chars_per_page: int = SCAN_MIN_CHARS_PER_PAGE,
    sparse_page_chars: int = SCAN_SPARSE_PAGE_CHARS,
    sparse_page_ratio: float = SCAN_SPARSE_PAGE_RATIO,
) -> FileStatus:
    """Détermine le statut final d'un fichier après extraction.

    CdC §9.3 — Combinaison :
    - Un scan illustré = alerte importante (+ éventuellement compteur d'images).
    - Le bandeau global affiche d'abord le plus grave.

    Priorité : ERROR > IGNORED > TOO_LARGE (déterminé ailleurs) >
               LOW_TEXT > IMAGES > READY.

    Args:
        text: Texte extrait.
        image_count: Nombre d'images détectées.
        chars_per_page: Caractères par page (PDF).
        is_ignored: True si le fichier est ignoré (hors périmètre).
        has_error: True si l'extraction a échoué.

    Returns:
        FileStatus approprié.
    """
    if has_error:
        return FileStatus.ERROR
    if is_ignored:
        return FileStatus.IGNORED

    # Vérifier la pauvreté de texte en premier (plus grave que images)
    if check_low_text(
        text,
        chars_per_page,
        image_count,
        min_chars_file=min_chars_file,
        min_chars_per_page=min_chars_per_page,
        sparse_page_chars=sparse_page_chars,
        sparse_page_ratio=sparse_page_ratio,
    ):
        return FileStatus.LOW_TEXT

    # Warning images (ne bloque pas)
    if image_count > 0:
        return FileStatus.IMAGES

    return FileStatus.READY
