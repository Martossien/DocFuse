"""Extracteur OpenDocument : .odt, .ods, .odp.

CdC §7.3 — Si ZIP/XML trivial (OpenDocument).
Les fichiers ODF sont des ZIP contenant du XML (content.xml, meta.xml).
On extrait le texte de content.xml.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.models.extraction_result import ExtractedFile
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
    def extract(cls, path: Path, relative_path: str) -> ExtractedFile:
        try:
            from bs4 import BeautifulSoup

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

                # En mode XML, les tags avec namespace sont préfixés
                office_text = soup.find("office:text")
                if office_text is None:
                    # Fallback: chercher par suffixe
                    for tag in soup.find_all(True):
                        if isinstance(tag, BTag) and tag.name and tag.name.endswith(":text"):
                            office_text = tag
                            break
                if office_text is None:
                    # Dernier fallback: extraire tous les text:p et text:h
                    for p in soup.find_all(["text:p", "text:h"]):
                        text = p.get_text(strip=True)
                        if text:
                            parts.append(text)
                elif isinstance(office_text, BTag):
                    for child in office_text.children:
                        if not isinstance(child, BTag):
                            continue
                        tag_name = child.name or ""

                        # Tableau → extraire les cellules ligne par ligne
                        if "table" in tag_name:
                            for row in child.find_all(True, recursive=True):
                                if row.name and "table-row" in row.name:
                                    cells = [
                                        c
                                        for c in row.children
                                        if isinstance(c, BTag) and c.name and "table-cell" in c.name
                                    ]
                                    cell_texts = [c.get_text(strip=True) for c in cells]
                                    if any(cell_texts):
                                        parts.append(" | ".join(cell_texts))

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
                )
        except Exception as exc:
            logger.exception("Erreur extraction ODF %s", path)
            return error_result(path, relative_path, cls.file_type, exc)
