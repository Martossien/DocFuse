"""Extracteur d'images : le texte d'un document scanné livré comme image (D-109).

Un courrier passé au scanner de bureau ressort en `.tif` ou en `.jpg`, pas en PDF —
c'est la sortie par défaut de la plupart des copieurs, et de tous les serveurs de
fax. Ces fichiers étaient jusqu'ici **ignorés** (`IMAGE_EXTENSIONS`, CdC §7.4),
c'est-à-dire absents de l'audit : ni classés, ni signalés comme non lus. Sur un
partage d'entreprise, c'est un angle mort qui peut contenir des bulletins de paie,
des arrêts de travail ou des pièces d'identité numérisées.

L'OCR n'est pas neuf ici : cinq extracteurs l'utilisent déjà (PDF, DOCX, XLSX,
PPTX, ODF) pour les images **intégrées** aux documents. Ce module ne fait que
brancher la même chaîne — `ocr_with_slot`, donc le même créneau de concurrence et
le même moteur — sur un fichier image autonome. Rien n'est réécrit.

Deux refus assumés :

* les formats **non matriciels** (`.svg`) et les icônes (`.ico`) restent hors
  périmètre : Leptonica ne les lit pas, et une icône ne porte pas de texte à
  auditer ;
* une image trop grande pour `OCR_MAX_PIXELS_PER_PAGE` n'est pas océrisée mais
  **dite** telle quelle, jamais rendue vide en silence — un fichier vide serait
  classé « sans contenu » puis proposé à la suppression.
"""

from __future__ import annotations

import logging
from pathlib import Path

from docfuse.constants import OCR_LANG, OCR_MAX_PIXELS_PER_PAGE, OCR_READABLE_IMAGES
from docfuse.core.ocr.registry import ocr_with_slot, resolve_ocr_engine
from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result, file_type_for
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)

__all__ = ["ImageExtractor", "OCR_IMAGE_EXTENSIONS"]

OCR_IMAGE_EXTENSIONS: frozenset[str] = OCR_READABLE_IMAGES
"""Images matricielles qu'un moteur OCR sait lire.

`.svg` (vectoriel, donc du XML) et `.ico` (icône d'interface) en sont exclus à
dessein : le premier n'est pas une image pour Leptonica, le second ne porte aucun
texte à auditer. Ils restent traités comme avant."""

_SANS_MOTEUR = (
    "[[IMAGE non lue : aucun moteur OCR disponible sur ce poste — "
    "le contenu de ce fichier n'a pas été audité]]"
)
"""Marqueur quand l'OCR manque.

Rendre une chaîne vide ferait classer le fichier « sans contenu », donc candidat
à la suppression : exactement l'inverse de ce qu'il faut dire d'un document qu'on
n'a pas su lire."""


def _marqueur_trop_grande(pixels: int) -> str:
    return (
        f"[[IMAGE non lue : {pixels // 1_000_000} Mpx, au-delà de la limite OCR "
        f"({OCR_MAX_PIXELS_PER_PAGE // 1_000_000} Mpx) — le contenu de ce fichier "
        "n'a pas été audité]]"
    )


def _pixels(data: bytes) -> int | None:
    """Nombre de pixels de l'image, ou `None` si on ne sait pas le dire.

    Pillow n'est pas une dépendance de DocFuse : la mesure passe par lui s'il est
    présent (il l'est via les extracteurs bureautiques), et on s'abstient sinon —
    ne pas savoir mesurer ne doit pas empêcher d'océriser.
    """
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            largeur, hauteur = image.size
            return int(largeur) * int(hauteur)
    except Exception:  # noqa: BLE001 - mesure facultative, jamais bloquante
        return None


@register(*OCR_IMAGE_EXTENSIONS)
class ImageExtractor(Extractor):
    """Océrise une image autonome et rend son texte comme celui d'un document."""

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in OCR_IMAGE_EXTENSIONS

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            data = path.read_bytes()
        except Exception as exc:  # noqa: BLE001 - remonté en ERROR, jamais avalé
            logger.exception("Erreur lecture image %s", path)
            return error_result(path, relative_path, exc)

        texte, statut = cls._lire(data, path)
        return ExtractedFile(
            path=path,
            relative_path=relative_path,
            extension=file_type_for(path),
            file_type=file_type_for(path),
            size_bytes=len(data),
            text=texte,
            status=statut,
            image_count=1,
        )

    @classmethod
    def _lire(cls, data: bytes, path: Path) -> tuple[str, FileStatus]:
        """Texte reconnu et statut associé — jamais un vide muet."""
        if not data:
            return "[[IMAGE non lue : fichier vide]]", FileStatus.IMAGES

        pixels = _pixels(data)
        if pixels is not None and pixels > OCR_MAX_PIXELS_PER_PAGE:
            logger.warning("Image trop grande pour l'OCR (%d px) : %s", pixels, path)
            return _marqueur_trop_grande(pixels), FileStatus.IMAGES

        engine = resolve_ocr_engine()
        if engine is None:
            return _SANS_MOTEUR, FileStatus.IMAGES

        texte = ocr_with_slot(engine, data, OCR_LANG).strip()
        if not texte:
            # Une image sans texte, c'est banal (photo, logo, schéma). Le dire
            # explicitement vaut mieux qu'un fichier vide, que l'aval classerait
            # « sans contenu » et proposerait à la suppression.
            return (
                f"[[IMAGE sans texte reconnu (tesseract, {OCR_LANG})]]",
                FileStatus.IMAGES,
            )
        return f"[[IMAGE — texte OCR (tesseract, {OCR_LANG})]]\n{texte}", FileStatus.READY
