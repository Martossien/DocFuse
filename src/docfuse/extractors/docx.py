"""Extracteur DOCX : .docx.

CdC §8.3 — Body, tableaux, headers/footers, footnotes, endnotes.
Utilise python-docx (MIT).
Détecte les images via word/media/* dans le ZIP.
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


@register(".docx")
class DocxExtractor(Extractor):
    """Extracteur DOCX via python-docx + détection media dans le ZIP."""

    file_type = "docx"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".docx"

    @classmethod
    def extract(cls, path: Path, relative_path: str) -> ExtractedFile:
        try:
            from docx import Document
            from docx.table import Table
            from docx.text.paragraph import Paragraph

            # Compter les images dans word/media/
            image_count = _count_media_images(path)

            doc = Document(str(path))
            parts: list[str] = []

            # BUG FIX: extraire paragraphes ET tableaux dans l'ordre du document
            # python-docx n'expose pas l'ordre directement, on itère sur les enfants
            # du body element XML pour respecter l'ordre d'apparition.
            body = doc.element.body
            for child in body:
                if child.tag.endswith("}p"):
                    para = Paragraph(child, doc)
                    if para.text.strip():
                        parts.append(para.text)
                elif child.tag.endswith("}tbl"):
                    table = Table(child, doc)
                    for row in table.rows:
                        cells = [cell.text.strip() for cell in row.cells]
                        parts.append(" | ".join(cells))

            # Headers et footers
            for section in doc.sections:
                for header in [section.header, section.first_page_header, section.even_page_header]:
                    if header and header.paragraphs:
                        for para in header.paragraphs:
                            if para.text.strip():
                                parts.append(f"[en-tête] {para.text}")
                for footer in [section.footer, section.first_page_footer, section.even_page_footer]:
                    if footer and footer.paragraphs:
                        for para in footer.paragraphs:
                            if para.text.strip():
                                parts.append(f"[pied de page] {para.text}")

            # Footnotes et endnotes (via XML brut si python-docx ne les expose pas)
            footnote_text = _extract_footnotes(path)
            if footnote_text:
                parts.append(f"[notes de bas de page]\n{footnote_text}")

            endnote_text = _extract_endnotes(path)
            if endnote_text:
                parts.append(f"[notes de fin]\n{endnote_text}")

            # I-19: zones de texte (w:txbxContent) depuis document.xml
            textbox_text = _extract_textboxes(path)
            if textbox_text:
                parts.append(f"[zones de texte]\n{textbox_text}")

            text = "\n\n".join(parts)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension="docx",
                file_type=cls.file_type,
                size_bytes=path.stat().st_size,
                text=text,
                status=FileStatus.READY,
                image_count=image_count,
            )
        except Exception as exc:
            logger.exception("Erreur extraction DOCX %s", path)
            return error_result(path, relative_path, cls.file_type, exc)


def _count_media_images(path: Path) -> int:
    """Compte les images dans word/media/ du ZIP DOCX.

    CdC §9.4 — DOCX : word/media/* dans le ZIP.
    """
    try:
        with zipfile.ZipFile(str(path), "r") as zf:
            media_files = [n for n in zf.namelist() if n.startswith("word/media/")]
            return len(media_files)
    except Exception:
        return 0


def _extract_footnotes(path: Path) -> str:
    """Extrait le texte des footnotes depuis word/footnotes.xml."""
    try:
        from bs4 import BeautifulSoup

        with zipfile.ZipFile(str(path), "r") as zf:
            if "word/footnotes.xml" not in zf.namelist():
                return ""
            xml = zf.read("word/footnotes.xml")
            soup = BeautifulSoup(xml, "xml")
            texts: list[str] = []
            for fn in soup.find_all("w:footnote"):
                # Ignorer les footnotes système (separator/continuationSeparator)
                fn_id = fn.get("w:id", "")
                if fn_id in ("-1", "0"):
                    continue
                text = fn.get_text(strip=True)
                if text:
                    texts.append(text)
            return "\n".join(texts)
    except Exception as _e:
        logger.warning("Échec extraction notes/zones: %s", _e)
        return ""


def _extract_endnotes(path: Path) -> str:
    """Extrait le texte des endnotes depuis word/endnotes.xml."""
    try:
        from bs4 import BeautifulSoup

        with zipfile.ZipFile(str(path), "r") as zf:
            if "word/endnotes.xml" not in zf.namelist():
                return ""
            xml = zf.read("word/endnotes.xml")
            soup = BeautifulSoup(xml, "xml")
            texts: list[str] = []
            for en in soup.find_all("w:endnote"):
                en_id = en.get("w:id", "")
                if en_id in ("-1", "0"):
                    continue
                text = en.get_text(strip=True)
                if text:
                    texts.append(text)
            return "\n".join(texts)
    except Exception as _e:
        logger.warning("Échec extraction notes/zones: %s", _e)
        return ""


def _extract_textboxes(path: Path) -> str:
    """I-19: Extrait le texte des zones de texte (w:txbxContent) depuis document.xml.

    CdC §8.3 — DOCX : zones de texte doivent être extraites.
    python-docx n'expose pas les text boxes → parsing XML manuel.
    """
    try:
        from bs4 import BeautifulSoup

        with zipfile.ZipFile(str(path), "r") as zf:
            if "word/document.xml" not in zf.namelist():
                return ""
            xml = zf.read("word/document.xml")
            soup = BeautifulSoup(xml, "xml")
            texts: list[str] = []
            for txbx in soup.find_all("w:txbxcontent"):
                text = txbx.get_text(strip=True)
                if text:
                    texts.append(text)
            return "\n".join(texts)
    except Exception as _e:
        logger.warning("Échec extraction notes/zones: %s", _e)
        return ""
