"""Dataclass ExtractedFile : résultat d'extraction d'un fichier.

Contient le texte extrait, les métadonnées, le compteur d'images,
et le statut. C'est l'unité de base manipulée par l'orchestrator
et les writers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from docfuse.models.file_status import FileStatus


@dataclass(frozen=True)
class EmbeddedImage:
    """Image intégrée exportée (D-091), en mémoire jusqu'à la génération du corpus.

    Attributes:
        filename: Nom de fichier prêt à écrire (voir `core/embedded_images.py`).
        data: Octets bruts de l'image (format d'origine, PNG/JPEG/...).
    """

    filename: str
    data: bytes


@dataclass
class ExtractedFile:
    """Résultat de l'extraction d'un fichier.

    Attributes:
        path: Chemin absolu du fichier source.
        relative_path: Chemin relatif au dossier d'entrée (pour l'en-tête SOURCE).
        extension: Extension en minuscules sans le point (ex: "pdf", "docx").
        file_type: Type affiché/rapporté — l'extension normalisée, via
            `extractors.base.file_type_for()` (D-099 : une seule politique,
            résultat READY ou ERREUR).
        size_bytes: Taille du fichier en octets.
        text: Texte extrait, normalisé UTF-8. Peut être vide si le fichier
            est un scan ou si l'extraction a échoué.
        status: Statut après analyse (READY, IMAGES, LOW_TEXT, IGNORED, etc.).
        error_message: Message d'erreur si status == ERROR, sinon None.
        image_count: Nombre d'images détectées dans le fichier.
        page_count: Nombre de pages ou diapositives (PDF, PPTX). 0 si non applicable.
        encoding: Encodage détecté pour les fichiers texte (ex: "utf-8", "cp1252").
        chars_per_page: Liste du nombre de caractères extraits par page (PDF uniquement).
        extra_metadata: Métadonnées supplémentaires libres (titre, auteur, etc.).
        embedded_images: Images intégrées exportées (DOCX/PPTX, D-091), vide
            si l'export n'a pas été demandé.
    """

    path: Path
    relative_path: str
    extension: str
    file_type: str
    size_bytes: int
    text: str = ""
    status: FileStatus = FileStatus.READY
    error_message: str | None = None
    image_count: int = 0
    page_count: int = 0
    encoding: str | None = None
    chars_per_page: list[int] = field(default_factory=list)
    extra_metadata: dict[str, str] = field(default_factory=dict)
    embedded_images: list[EmbeddedImage] = field(default_factory=list)

    @property
    def text_length(self) -> int:
        """Nombre de caractères du texte extrait (espaces normalisés non inclus)."""
        return len(self.text)

    @property
    def text_bytes_utf8(self) -> int:
        """Nombre d'octets UTF-8 du texte extrait."""
        return len(self.text.encode("utf-8"))

    @property
    def has_images(self) -> bool:
        """True si le fichier contient au moins une image détectée."""
        return self.image_count > 0

    @property
    def is_scan(self) -> bool:
        """True si le fichier est probablement un scan (peu de texte + images)."""
        return self.status is FileStatus.LOW_TEXT

    def to_dict(self) -> dict[str, object]:
        """Sérialisation pour le rapport JSON."""
        return {
            "path": str(self.path),
            "relative_path": self.relative_path,
            "extension": self.extension,
            "file_type": self.file_type,
            "size_bytes": self.size_bytes,
            "text_length": self.text_length,
            "status": self.status.value,
            "error_message": self.error_message,
            "image_count": self.image_count,
            "page_count": self.page_count,
            "encoding": self.encoding,
            "chars_per_page": self.chars_per_page,
            "extra_metadata": self.extra_metadata,
            "embedded_images_count": len(self.embedded_images),
        }
