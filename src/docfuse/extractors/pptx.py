"""Extracteur PPTX : .pptx.

CdC §8.3 — Texte des shapes, tableaux, notes d'orateur.
Diapo sans texte → [[DIAPO N: aucun texte extractible]].
Détecte les images via ppt/media/* dans le ZIP.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Any

from docfuse.constants import OCR_LANG
from docfuse.core.embedded_images import build_image_marker, build_image_tag
from docfuse.core.ocr.base import OcrEngine
from docfuse.core.ocr.registry import resolve_ocr_engine
from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result, is_ole_encrypted, is_zip_bomb
from docfuse.i18n import t
from docfuse.models.extraction_result import EmbeddedImage, ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)


@register(".pptx")
class PptxExtractor(Extractor):
    """Extracteur PPTX via python-pptx + détection media."""

    file_type = "pptx"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".pptx"

    @classmethod
    def extract(cls, path: Path, relative_path: str, extract_images: bool = False) -> ExtractedFile:
        try:
            # D-089 : un .pptx protégé par mot de passe à l'ouverture est un
            # conteneur OLE2, plus un ZIP — sans cette détection, python-pptx
            # échoue avec un `PackageNotFoundError` bas niveau qui ne dit
            # jamais à l'utilisateur que le fichier est protégé.
            if is_ole_encrypted(path):
                return ExtractedFile(
                    path=path,
                    relative_path=relative_path,
                    extension="pptx",
                    file_type=cls.file_type,
                    size_bytes=path.stat().st_size,
                    status=FileStatus.ERROR,
                    error_message=t("error.encrypted_office"),
                )

            # D-093 : garde-fou "bombe zip" avant tout parsing du conteneur.
            if is_zip_bomb(path):
                return ExtractedFile(
                    path=path,
                    relative_path=relative_path,
                    extension="pptx",
                    file_type=cls.file_type,
                    size_bytes=path.stat().st_size,
                    status=FileStatus.ERROR,
                    error_message=t("error.zip_bomb_suspected"),
                )

            from pptx import Presentation
            from pptx.enum.shapes import MSO_SHAPE_TYPE

            image_count = _count_media_images(path)

            # D-091 : OCR/export des images intégrées, seulement si utile
            # (export demandé ou OCR disponible) — sinon zéro coût ajouté,
            # comportement strictement identique à avant.
            engine = resolve_ocr_engine()
            want_export = extract_images
            embedded_images: list[EmbeddedImage] = []

            prs = Presentation(str(path))
            parts: list[str] = []
            slide_count = 0

            for i, slide in enumerate(prs.slides, 1):
                slide_count += 1
                slide_text: list[str] = []
                slide_image_index = 0

                # D-074 : descend dans les formes groupées (GroupShape) —
                # sans ça, tout texte/tableau dans un groupe (schémas,
                # diagrammes annotés — fréquents dans les decks "corporate")
                # est invisible : shape.has_text_frame/has_table renvoient
                # False pour le conteneur groupe lui-même.
                for shape in _iter_shapes(slide.shapes):
                    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                        if want_export or engine is not None:
                            slide_image_index += 1
                            marker, embedded = _process_picture(
                                shape, relative_path, i, slide_image_index, want_export, engine
                            )
                            if marker:
                                slide_text.append(marker)
                            if embedded:
                                embedded_images.append(embedded)
                        continue

                    if shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            text = _clean_text(para.text)
                            if text:
                                slide_text.append(text)

                    if shape.has_table:
                        table = shape.table
                        for row in table.rows:
                            cells = [_clean_text(cell.text) for cell in row.cells]
                            slide_text.append(" | ".join(cells))

                # Notes d'orateur
                if slide.has_notes_slide:
                    notes = slide.notes_slide.notes_text_frame
                    if notes and _clean_text(notes.text):
                        slide_text.append(f"[Notes] {_clean_text(notes.text)}")

                if not slide_text:
                    slide_text.append(f"[[DIAPO {i}: aucun texte extractible]]")

                parts.append(f"## Diapo {i}\n\n" + "\n\n".join(slide_text))

            text = "\n\n---\n\n".join(parts)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension="pptx",
                file_type=cls.file_type,
                size_bytes=path.stat().st_size,
                text=text,
                status=FileStatus.READY,
                image_count=image_count,
                page_count=slide_count,
                embedded_images=embedded_images,
            )
        except Exception as exc:
            logger.exception("Erreur extraction PPTX %s", path)
            return error_result(path, relative_path, cls.file_type, exc)


def _clean_text(text: str) -> str:
    """Normalise le texte d'une forme PPTX (D-096).

    python-pptx rend un saut de ligne manuel (`<a:br/>`, Maj+Entrée dans
    PowerPoint) comme `\\x0b` (tabulation verticale) dans `.text`. Sans
    conversion, ce caractère de contrôle finit tel quel dans le Markdown
    (compté par les tokenizers, rendu en glyphe inconnu dans le PDF).
    """
    return text.replace("\x0b", "\n").strip()


def _process_picture(
    shape: Any,
    relative_path: str,
    slide_no: int,
    index: int,
    want_export: bool,
    engine: OcrEngine | None,
) -> tuple[str, EmbeddedImage | None]:
    """Construit le marqueur inline (et l'image à exporter) d'une forme image
    d'une diapo (D-091). N'échoue jamais : une image illisible est ignorée
    plutôt que de faire échouer toute l'extraction de la diapo."""
    try:
        image = shape.image
        data = image.blob
        ext = image.ext
    except Exception:
        logger.warning("Lecture de l'image slide %d échouée", slide_no, exc_info=True)
        return "", None

    tag = build_image_tag(relative_path, f"slide{slide_no}", index, ext)

    ocr_text = ""
    if engine is not None:
        try:
            ocr_text = engine.ocr_image(data, OCR_LANG)
        except Exception:
            logger.warning("Échec OCR image slide %d", slide_no, exc_info=True)

    marker = build_image_marker(tag if want_export else None, ocr_text, OCR_LANG)
    embedded = EmbeddedImage(filename=tag, data=data) if want_export and marker else None
    return marker, embedded


def _iter_shapes(shapes: Any) -> Any:
    """Parcourt les formes d'une diapo récursivement, en descendant dans les
    formes groupées (GroupShape, D-074) — la notion de groupe est elle-même
    récursive (un groupe peut contenir un groupe)."""
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_shapes(shape.shapes)
        else:
            yield shape


def _count_media_images(path: Path) -> int:
    """Compte les images dans ppt/media/ du ZIP PPTX."""
    try:
        with zipfile.ZipFile(str(path), "r") as zf:
            return sum(1 for n in zf.namelist() if n.startswith("ppt/media/"))
    except Exception:
        return 0
