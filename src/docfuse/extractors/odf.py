"""Extracteur OpenDocument : .odt, .ods, .odp.

CdC §7.3 — Si ZIP/XML trivial (OpenDocument).
Les fichiers ODF sont des ZIP contenant du XML (content.xml, meta.xml).
On extrait le texte de content.xml.
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
from docfuse.extractors.base import Extractor, error_result, is_zip_bomb
from docfuse.i18n import t
from docfuse.models.extraction_result import EmbeddedImage, ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)


@register(".odt", ".ods", ".odp")
class OdfExtractor(Extractor):
    """Extracteur OpenDocument (ODT/ODS/ODP) via ZIP/XML."""

    file_type = "odf"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in (".odt", ".ods", ".odp")

    @classmethod
    def extract(cls, path: Path, relative_path: str, extract_images: bool = False) -> ExtractedFile:
        try:
            # D-093 : garde-fou "bombe zip" avant tout parsing du conteneur.
            if is_zip_bomb(path):
                return ExtractedFile(
                    path=path,
                    relative_path=relative_path,
                    extension=path.suffix.lower().lstrip("."),
                    file_type=path.suffix.lower().lstrip("."),
                    size_bytes=path.stat().st_size,
                    status=FileStatus.ERROR,
                    error_message=t("error.zip_bomb_suspected"),
                )

            from bs4 import BeautifulSoup

            # D-093 : OCR/export des images intégrées (odt/odp), seulement
            # si utile — sinon zéro coût ajouté par rapport à avant.
            engine = resolve_ocr_engine()
            want_export = extract_images
            embedded_images: list[EmbeddedImage] = []

            with zipfile.ZipFile(str(path), "r") as zf:
                # Compter les images
                image_count = sum(1 for n in zf.namelist() if n.startswith(("Pictures/", "media/")))

                # Lire content.xml
                if "content.xml" not in zf.namelist():
                    return ExtractedFile(
                        path=path,
                        relative_path=relative_path,
                        extension=path.suffix.lower().lstrip("."),
                        file_type=path.suffix.lower().lstrip("."),
                        size_bytes=path.stat().st_size,
                        text="",
                        status=FileStatus.ERROR,
                        error_message="content.xml introuvable dans l'archive ODF",
                    )

                content_xml = zf.read("content.xml")
                soup = BeautifulSoup(content_xml, "xml")

                # BUG FIX: extraire les paragraphes et les tableaux dans l'ordre
                # sans duplication. On parcourt les enfants de office:text.
                parts: list[str] = []

                # Trouver le body (office:text avec namespace ODF)
                from bs4 import Tag as BTag

                # D-087 : .odp (office:presentation) traité en premier, à
                # part — voir _extract_presentation. Sans ce cas dédié, le
                # code tombait dans le "dernier fallback" ci-dessous, qui
                # mélange indistinctement le contenu visible des diapos ET
                # les notes d'orateur (presentation:notes, jamais affichées
                # à l'écran — potentielle fuite de contenu non destiné à la
                # diffusion), sans aucune séparation entre diapos.
                office_presentation = soup.find("office:presentation")
                office_text: BTag | None = None
                if isinstance(office_presentation, BTag):
                    presentation_parts, presentation_images = _extract_presentation(
                        office_presentation, zf, relative_path, engine, want_export
                    )
                    parts.extend(presentation_parts)
                    embedded_images.extend(presentation_images)
                else:
                    found_text = soup.find("office:text")
                    if isinstance(found_text, BTag):
                        office_text = found_text
                    else:
                        # Fallback: chercher par suffixe
                        for tag in soup.find_all(True):
                            if isinstance(tag, BTag) and tag.name and tag.name.endswith(":text"):
                                office_text = tag
                                break

                if office_presentation is not None:
                    pass  # déjà traité ci-dessus
                elif office_text is None:
                    # Dernier fallback: extraire tous les text:p et text:h
                    for p in soup.find_all(["text:p", "text:h"]):
                        text = p.get_text(strip=True)
                        if text:
                            parts.append(text)
                else:
                    image_counter = [0]
                    for child in office_text.children:
                        if not isinstance(child, BTag):
                            continue
                        tag_name = child.name or ""

                        # Tableau → extraire les cellules ligne par ligne
                        if "table" in tag_name:
                            parts.extend(_table_rows_to_parts(child))

                        # Paragraphe (text:p) ou titre (text:h)
                        elif (
                            tag_name == "p"
                            or tag_name == "h"
                            or "text:p" in tag_name
                            or "text:h" in tag_name
                        ):
                            text = child.get_text(strip=True)
                            if text:
                                parts.append(text)

                        # Liste
                        elif "list" in tag_name:
                            for item in child.find_all(True, recursive=True):
                                if item.name and "list-item" in item.name:
                                    text = item.get_text(strip=True)
                                    if text:
                                        parts.append(f"- {text}")

                        # D-093 : images intégrées (`draw:frame`/`draw:image`)
                        # — ancrées au paragraphe (inline, cas le plus
                        # fréquent) ou directement à la page (`child` lui
                        # -même un frame, aucune des branches ci-dessus ne
                        # matchant alors "table"/"p"/"h"/"list").
                        if want_export or engine is not None:
                            for href in _iter_image_hrefs(child):
                                image_counter[0] += 1
                                marker, embedded = _image_marker(
                                    zf,
                                    href,
                                    relative_path,
                                    None,
                                    image_counter[0],
                                    engine,
                                    want_export,
                                )
                                if marker:
                                    parts.append(marker)
                                if embedded:
                                    embedded_images.append(embedded)

                # D-072 : en-têtes/pieds de page ODT vivent dans styles.xml
                # (office:master-styles), jamais dans content.xml — invisibles
                # sans ce second passage. Contiennent souvent des métadonnées
                # de document (référence, mention de confidentialité).
                if "styles.xml" in zf.namelist():
                    parts.extend(_extract_master_headers_footers(zf.read("styles.xml")))

                full_text = "\n".join(parts)

                return ExtractedFile(
                    path=path,
                    relative_path=relative_path,
                    extension=path.suffix.lower().lstrip("."),
                    file_type=path.suffix.lower().lstrip("."),  # M-08: "odt" / "ods" / "odp"
                    size_bytes=path.stat().st_size,
                    text=full_text,
                    status=FileStatus.READY,
                    image_count=image_count,
                    embedded_images=embedded_images,
                )
        except Exception as exc:
            logger.exception("Erreur extraction ODF %s", path)
            return error_result(path, relative_path, cls.file_type, exc)


def _table_rows_to_parts(table_tag: Any) -> list[str]:
    """Cellules d'un tableau ODF, une ligne `" | "` par ligne de tableau."""
    from bs4 import Tag as BTag

    parts: list[str] = []
    for row in table_tag.find_all(True, recursive=True):
        if row.name and "table-row" in row.name:
            cells = [
                c for c in row.children if isinstance(c, BTag) and c.name and "table-cell" in c.name
            ]
            cell_texts = [c.get_text(strip=True) for c in cells]
            if any(cell_texts):
                parts.append(" | ".join(cell_texts))
    return parts


def _extract_presentation(
    office_presentation: Any,
    zf: zipfile.ZipFile,
    relative_path: str,
    engine: OcrEngine | None,
    want_export: bool,
) -> tuple[list[str], list[EmbeddedImage]]:
    """Contenu d'un `office:presentation` (.odp), diapo par diapo (D-087).

    Corrige deux problèmes du fallback générique (`text:p`/`text:h`
    document-wide) qu'un `.odp` déclenchait systématiquement (aucun tag ne
    matche `office:text` dans une présentation, qui utilise
    `office:presentation` à la place) :
    - Les notes d'orateur (`presentation:notes`, jamais affichées à
      l'écran) étaient mélangées indistinctement au contenu visible des
      diapos — extraites ici séparément, étiquetées, jamais silencieusement
      fondues dans le texte "normal" (risque de fuite de contenu non
      destiné à la diffusion).
    - Aucune séparation entre diapos.

    D-093 : les images intégrées de chaque diapo sont détectées et
    numérotées par diapo (`slide{i}`, comme PPTX), avant que les tables
    soient retirées de l'arbre (une image dans une cellule reste détectée).
    """
    from bs4 import Tag as BTag

    parts: list[str] = []
    embedded_images: list[EmbeddedImage] = []
    for i, page in enumerate(office_presentation.find_all("draw:page", recursive=False), 1):
        notes_texts: list[str] = []
        for notes in page.find_all("presentation:notes"):
            text = notes.get_text(separator=" ", strip=True)
            if text:
                notes_texts.append(text)
            notes.extract()  # retiré de l'arbre : jamais compté deux fois

        slide_parts: list[str] = []

        if want_export or engine is not None:
            for slide_image_index, href in enumerate(_iter_image_hrefs(page), 1):
                marker, embedded = _image_marker(
                    zf, href, relative_path, f"slide{i}", slide_image_index, engine, want_export
                )
                if marker:
                    slide_parts.append(marker)
                if embedded:
                    embedded_images.append(embedded)

        # Tables d'abord, puis retirées de l'arbre — sinon le texte de leurs
        # cellules serait aussi capté par la recherche text:p/text:h plus
        # bas (une cellule contient un text:p) et compté deux fois.
        tables = [
            t
            for t in page.find_all(True, recursive=True)
            if isinstance(t, BTag) and t.name and (t.name == "table" or t.name.endswith(":table"))
        ]
        for table in tables:
            slide_parts.extend(_table_rows_to_parts(table))
            table.extract()

        for p in page.find_all(["text:p", "text:h"]):
            text = p.get_text(strip=True)
            if text:
                slide_parts.append(text)

        if slide_parts:
            parts.append(f"## Diapo {i}\n" + "\n".join(slide_parts))
        if notes_texts:
            parts.append(f"[notes orateur diapo {i}]\n" + "\n".join(notes_texts))
    return parts, embedded_images


def _iter_image_hrefs(tag: Any) -> list[str]:
    """Chemins ZIP (`xlink:href`) des images intégrées (`draw:frame` >
    `draw:image`) trouvées dans `tag`, y compris `tag` lui-même si c'est
    déjà un `draw:frame` (ancrage "à la page", D-093). Contrairement à
    OOXML (DOCX/PPTX/XLSX), pas d'indirection par relation : le chemin ZIP
    est donné directement par `xlink:href`."""
    from bs4 import Tag as BTag

    def _is_frame(t: Any) -> bool:
        return (
            isinstance(t, BTag)
            and bool(t.name)
            and (t.name == "frame" or t.name.endswith(":frame"))
        )

    def _is_image(t: Any) -> bool:
        return (
            isinstance(t, BTag)
            and bool(t.name)
            and (t.name == "image" or t.name.endswith(":image"))
        )

    frames = [tag] if _is_frame(tag) else []
    frames.extend(t for t in tag.find_all(True, recursive=True) if _is_frame(t))

    hrefs: list[str] = []
    for frame in frames:
        image_tag = next((t for t in frame.find_all(True, recursive=True) if _is_image(t)), None)
        if image_tag is None:
            continue
        href = image_tag.get("xlink:href")
        if href:
            hrefs.append(str(href))
    return hrefs


def _image_marker(
    zf: zipfile.ZipFile,
    href: str,
    relative_path: str,
    location: str | None,
    index: int,
    engine: OcrEngine | None,
    want_export: bool,
) -> tuple[str, EmbeddedImage | None]:
    """Construit le marqueur inline (et l'image à exporter) d'une image ODF
    (D-093). N'échoue jamais : une image illisible est ignorée."""
    try:
        data = zf.read(href)
    except KeyError:
        return "", None

    ext = href.rsplit(".", 1)[-1] if "." in href else "png"
    tag = build_image_tag(relative_path, location, index, ext)

    ocr_text = ""
    if engine is not None:
        try:
            ocr_text = engine.ocr_image(data, OCR_LANG)
        except Exception:
            logger.warning("Échec OCR image %s", tag, exc_info=True)

    marker = build_image_marker(tag if want_export else None, ocr_text, OCR_LANG)
    embedded = EmbeddedImage(filename=tag, data=data) if want_export and marker else None
    return marker, embedded


def _extract_master_headers_footers(styles_xml: bytes) -> list[str]:
    """Texte des en-têtes/pieds de page ODT (D-072).

    Spec OASIS ODF 1.2 §16.4-16.5 : `office:master-styles` contient un ou
    plusieurs `style:master-page`, chacun avec un `style:header`/
    `style:footer` optionnel — le texte récurrent affiché sur les pages qui
    utilisent ce style de page. Absent de `content.xml`.
    """
    from bs4 import BeautifulSoup
    from bs4 import Tag as BTag

    soup = BeautifulSoup(styles_xml, "xml")
    parts: list[str] = []
    for master_page in soup.find_all("style:master-page"):
        if not isinstance(master_page, BTag):
            continue
        header = master_page.find("style:header")
        if isinstance(header, BTag):
            text = header.get_text(strip=True)
            if text:
                parts.append(f"[en-tête] {text}")
        footer = master_page.find("style:footer")
        if isinstance(footer, BTag):
            text = footer.get_text(strip=True)
            if text:
                parts.append(f"[pied de page] {text}")
    return parts
