"""Classe de base abstraite pour tous les extracteurs.

Inspiré de MarkItDown (DocumentConverter avec accepts + convert),
adapté pour DocFuse.

Contrat :
- ``accepts(path) -> bool`` : vérifie rapidement si l'extracteur peut traiter
  le fichier (par extension, par contenu). Ne doit pas consommer le flux.
- ``extract(path) -> ExtractedFile`` : extrait le texte et les métadonnées.
  Capture ses propres erreurs et retourne un statut ERROR plutôt que de crasher.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)


def error_result(
    path: Path,
    relative_path: str,
    file_type: str,
    exc: Exception,
) -> ExtractedFile:
    """Construit un ExtractedFile d'erreur — factorisation des 13 extracteurs.

    Au lieu de dupliquer le bloc try/except dans chaque extracteur,
    chaque extracteur peut lever une exception qui sera attrapée par
    ``safe_extract`` ou utiliser cette helper directement.
    """
    return ExtractedFile(
        path=path,
        relative_path=relative_path,
        extension=path.suffix.lower().lstrip("."),
        file_type=file_type,
        size_bytes=path.stat().st_size if path.exists() else 0,
        status=FileStatus.ERROR,
        error_message=f"{type(exc).__name__}: {exc}",
    )


class Extractor(ABC):
    """Classe de base abstraite pour les extracteurs de texte.

    Chaque sous-classe :
    1. Décore avec ``@register(".ext")`` pour s'enregistrer.
    2. Implémente ``accepts()`` et ``extract()``.
    3. ``extract()`` ne doit JAMAIS lever d'exception — capturer et retourner
       un ExtractedFile avec ``status=FileStatus.ERROR``.
    """

    file_type: str = "unknown"
    """Type de format pour les métadonnées (ex: "pdf", "docx")."""

    @classmethod
    @abstractmethod
    def accepts(cls, path: Path) -> bool:
        """Vérifie rapidement si cet extracteur peut traiter le fichier."""
        ...

    @classmethod
    @abstractmethod
    def extract(cls, path: Path, relative_path: str) -> ExtractedFile:
        """Extrait le texte et les métadonnées d'un fichier.

        Ne doit JAMAIS lever d'exception. Utiliser ``error_result()``
        pour construire un résultat d'erreur en cas d'échec.
        """
        ...

    @classmethod
    def safe_extract(cls, path: Path, relative_path: str) -> ExtractedFile:
        """Wrapper défensif : appelle extract() et capture toute exception non gérée."""
        try:
            result = cls.extract(path, relative_path)
            if result.status is FileStatus.ERROR and not result.error_message:
                from docfuse.i18n import t as _t

                result.error_message = _t("error.unknown")
            return result
        except Exception as exc:
            logger.exception("Erreur non capturée dans %s pour %s", cls.__name__, path)
            return error_result(path, relative_path, cls.file_type, exc)
