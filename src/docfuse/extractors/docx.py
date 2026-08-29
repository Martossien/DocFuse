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

            # Compter les images dans word/media/
            image_count = _count_media_images(path)

            doc = Document(str(path))
            parts: list[str] = []

            # BUG FIX: extraire paragraphes ET tableaux dans l'ordre du document
            # python-docx n'expose pas l'ordre directement, on itère sur les enfants
            # du body element XML pour respecter l'ordre d'apparition.
            # D-069 : descend aussi dans les w:sdt (contrôles de contenu Word) —
            # sans ça, un paragraphe/tableau entier enveloppé dans un contrôle de
            # contenu (omniprésent dans les modèles RH/juridique/formulaires) est
            # invisible.
            body = doc.element.body
            parts.extend(_iter_body_parts(body, doc, Table))

            # Headers et footers
            for section in doc.sections:
                for header in [section.header, section.first_page_header, section.even_page_header]:
                    if header and header.paragraphs:
                        for para in header.paragraphs:
                            text = _flatten_paragraph_text(para._p)
                            if text.strip():
                                parts.append(f"[en-tête] {text}")
                for footer in [section.footer, section.first_page_footer, section.even_page_footer]:
                    if footer and footer.paragraphs:
                        for para in footer.paragraphs:
                            text = _flatten_paragraph_text(para._p)
                            if text.strip():
                                parts.append(f"[pied de page] {text}")

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


def _flatten_paragraph_text(p_element: object) -> str:
    """Texte complet d'un paragraphe, en descendant dans TOUT élément imbriqué
    (`w:ins` — suivi des modifications, `w:sdt` — contrôle de contenu au
    niveau run, `w:hyperlink`, `w:fldSimple`, `w:smartTag`, ...), pas
    seulement les runs enfants directs comme le fait `Paragraph.text` de
    python-docx (D-069).

    Exclut volontairement `w:delText` (texte supprimé en suivi des
    modifications) : on veut le texte final du document, pas les deux
    versions mélangées.
    """
    parts: list[str] = []
    for el in p_element.iter():  # type: ignore[attr-defined]
        tag = el.tag
        if tag.endswith("}t"):
            parts.append(el.text or "")
        elif tag.endswith("}tab"):
            parts.append("\t")
        elif tag.endswith(("}br", "}cr")):
            parts.append("\n")
    return "".join(parts)


def _iter_body_parts(container: object, doc: object, table_cls: type) -> list[str]:
    """Parcourt les enfants d'un conteneur "body-like" (le corps du document,
    ou le contenu d'un `w:sdt`) et retourne paragraphes/tableaux dans l'ordre
    d'apparition — en descendant récursivement dans les `w:sdt` (contrôles de
    contenu Word) rencontrés au niveau bloc (D-069). Sans cette récursion, un
    paragraphe ou un tableau entier enveloppé dans un contrôle de contenu est
    invisible : ni `child.tag.endswith("}p")` ni `"}tbl"` ne matche `w:sdt`.
    """
    parts: list[str] = []
    for child in container:  # type: ignore[attr-defined]
        if child.tag.endswith("}p"):
            text = _flatten_paragraph_text(child)
            if text.strip():
                parts.append(text)
        elif child.tag.endswith("}tbl"):
            table = table_cls(child, doc)
            for row in table.rows:
                cells = [
                    "\n".join(_flatten_paragraph_text(p._p) for p in cell.paragraphs).strip()
                    for cell in row.cells
                ]
                parts.append(" | ".join(cells))
        elif child.tag.endswith("}sdt"):
            sdt_content = next((c for c in child if c.tag.endswith("}sdtContent")), None)
            if sdt_content is not None:
                parts.extend(_iter_body_parts(sdt_content, doc, table_cls))
    return parts


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
