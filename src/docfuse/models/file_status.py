"""Énumération des statuts possibles pour un fichier analysé.

CdC §6.1 — Statuts visuels de la liste de fichiers.
"""

from __future__ import annotations

from enum import StrEnum


class FileStatus(StrEnum):

    READY = "ready"
    """Texte extractible, sous le plafond. Pastille verte."""

    IMAGES = "images"
    """Contient des images ; le texte sera quand même pris. Pastille jaune."""

    LOW_TEXT = "low_text"
    """Peu ou pas de texte extractible (probable scan). Pastille orange/rouge."""

    TOO_LARGE = "too_large"
    """Fichier seul ≥ plafond → génération bloquée. Pastille rouge, cadenas."""

    IGNORED = "ignored"
    """Extension hors périmètre, verrouillé, vide, ~$, etc. Pastille grise."""

    ERROR = "error"
    """Corrompu, mot de passe, lecture impossible. Pastille rouge."""

    def is_blocking(self) -> bool:
        """True si ce statut bloque la génération du corpus."""
        return self is FileStatus.TOO_LARGE

    def is_warning(self) -> bool:
        """True si ce statut est un avertissement (images) — ne bloque pas."""
        return self is FileStatus.IMAGES

    def is_alert(self) -> bool:
        """True si ce statut est une alerte importante (scan/pauvreté) — ne bloque pas."""
        return self is FileStatus.LOW_TEXT

    def is_extracted(self) -> bool:
        """True si le fichier a été extrait avec succès (texte disponible)."""
        return self in (FileStatus.READY, FileStatus.IMAGES, FileStatus.LOW_TEXT)

    @property
    def severity(self) -> int:
        """Niveau de gravité pour le tri et l'affichage (0 = OK, + = grave)."""
        order = {
            FileStatus.READY: 0,
            FileStatus.IMAGES: 1,
            FileStatus.LOW_TEXT: 2,
            FileStatus.IGNORED: 3,
            FileStatus.ERROR: 4,
            FileStatus.TOO_LARGE: 5,
        }
        return order[self]

    @property
    def i18n_key(self) -> str:
        """Clé i18n du label lisible de ce statut."""
        return {
            FileStatus.READY: "status.ready",
            FileStatus.IMAGES: "status.images",
            FileStatus.LOW_TEXT: "status.low_text",
            FileStatus.TOO_LARGE: "status.too_large",
            FileStatus.IGNORED: "status.ignored",
            FileStatus.ERROR: "status.error",
        }[self]

    def label(self) -> str:
        """Label lisible traduit via i18n. Source unique de vérité pour GUI et rapport."""
        from docfuse.i18n import t

        return t(self.i18n_key)
