"""Extracteur HTML : .html, .htm.

CdC §7.2 — Texte visible. Pas le JS. Titres → Markdown #.
CdC §8.3 — Titres, paragraphes, listes, tableaux, alt des images.
I-18 — Ordre du document respecté (parcours séquentiel du DOM).
BUG FIX — Plus de duplication du texte (get_text évité sur les éléments structurés).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.extractors.text import detect_encoding
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)

# Tags dont on extrait le texte de manière structurée (pas via get_text global)
STRUCTURED_TAGS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "img",
    "table",
    "ul",
    "ol",
    "script",
    "style",
    "noscript",
}


@register(".html", ".htm")
class HtmlExtractor(Extractor):
    """Extracteur HTML avec BeautifulSoup4 — parcours séquentiel du DOM sans duplication."""

    file_type = "html"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in (".html", ".htm")

    @classmethod
    def extract(cls, path: Path, relative_path: str) -> ExtractedFile:
        try:
            from bs4 import BeautifulSoup, Tag, UnicodeDammit

            raw = path.read_bytes()
            # D-073 : `detect_encoding()` (BOM→UTF-8→cp1252→...) ignore
            # totalement <meta charset=...>/<meta http-equiv="Content-Type"
            # content="...charset=...">. cp1252 décode presque tous les
            # octets sans erreur, donc la détection générique "gagne" avant
            # même d'essayer le charset déclaré par la page — mojibake
            # silencieux et total pour tout charset legacy mono-octet non
            # latin (cyrillique, grec, hébreu...). `UnicodeDammit(is_html=True)`
            # sait lire cette déclaration ; on ne garde `detect_encoding()`
            # qu'en dernier repli si Dammit échoue à produire du texte.
            dammit = UnicodeDammit(raw, is_html=True)
            if dammit.unicode_markup is not None:
                html = dammit.unicode_markup
                encoding = dammit.original_encoding or "utf-8"
            else:
                encoding, data = detect_encoding(raw)
                html = data.decode(encoding, errors="replace")

            soup = BeautifulSoup(html, "lxml")

            # Supprimer les scripts et styles
            for tag in soup.find_all(["script", "style", "noscript"]):
                tag.decompose()

            image_count = 0
            parts: list[str] = []

            # I-18: Parcourir le body dans l'ordre du document
            body = soup.find("body")
            if body is None:
                body = soup
            body_tag: Tag = body if isinstance(body, Tag) else soup

            # Parcourir les enfants directs du body (pas descendants) pour éviter la duplication
            image_counter = {"count": 0}
            _extract_elements(body_tag, parts, image_counter)
            image_count = image_counter["count"]

            full_text = "\n\n".join(parts)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=path.suffix.lower().lstrip("."),
                file_type=path.suffix.lower().lstrip("."),
                size_bytes=len(raw),
                text=full_text,
                status=FileStatus.READY,
                encoding=encoding,
                image_count=image_count,
            )
        except Exception as exc:
            logger.exception("Erreur extraction HTML %s", path)
            return error_result(path, relative_path, cls.file_type, exc)


def _extract_elements(parent: Any, parts: list[str], counter: dict[str, int]) -> None:
    """Extrait les éléments d'un conteneur HTML séquentiellement.

    Parcourt les enfants directs et extrait chaque élément selon son type.
    `counter` est un dict mutable {"count": int} pour compter les images par référence.
    """
    from bs4 import Comment, NavigableString, Tag

    for element in parent.children:
        if isinstance(element, Comment):
            # D-080 : Comment hérite de NavigableString — sans cette
            # exclusion explicite, un commentaire HTML (notes internes,
            # code commenté, IE conditional comments) fuite dans le texte
            # extrait comme s'il s'agissait de contenu visible normal.
            continue
        if isinstance(element, NavigableString):
            text = str(element).strip()
            if text:
                parts.append(text)
            continue

        if not isinstance(element, Tag):
            continue

        tag_name = element.name or ""

        # Titres → Markdown # (h1-h6 uniquement, pas <hr>, <head>, <html>, etc.)
        if tag_name and tag_name.startswith("h") and len(tag_name) == 2 and tag_name[1].isdigit():
            level = int(tag_name[1])
            text = element.get_text(strip=True)
            if text:
                parts.append(f"{'#' * level} {text}")
            continue

        # Images : compter + extraire le alt
        if tag_name == "img":
            counter["count"] += 1
            alt_raw = element.get("alt", "")
            alt = str(alt_raw).strip() if alt_raw else ""
            if alt:
                parts.append(f"[image: {alt}]")
            else:
                parts.append("[image sans description]")
            continue

        # Tableaux → Markdown
        if tag_name == "table":
            table_md = _table_to_markdown(element)
            if table_md:
                parts.append(table_md)
            continue

        # Listes → Markdown
        if tag_name in ("ul", "ol"):
            list_md = _list_to_markdown(element)
            if list_md:
                parts.append(list_md)
            continue

        # Paragraphes et autres conteneurs → récursion pour trouver images/tableaux/listes
        if tag_name in (
            "p",
            "div",
            "span",
            "section",
            "article",
            "header",
            "footer",
            "main",
            "dl",
            "dt",
            "dd",
            "pre",
        ):
            # D'abord compter les images dans ce conteneur
            for img in element.find_all("img"):
                counter["count"] += 1
                alt_raw = img.get("alt", "")
                alt = str(alt_raw).strip() if alt_raw else ""
                if alt:
                    parts.append(f"[image: {alt}]")
                else:
                    parts.append("[image sans description]")
            # Puis extraire le texte (sans les images déjà traitées)
            text = element.get_text(separator=" ", strip=True)
            if text:
                parts.append(text)
            continue

        # Pour tout autre tag, extraire le texte direct (sans récursion sur les enfants structurés)
        text = element.get_text(strip=True)
        if text:
            parts.append(text)


def _table_to_markdown(table: Any) -> str:
    """Convertit un tableau HTML en Markdown."""
    rows = table.find_all("tr")
    if not rows:
        return ""

    lines: list[str] = []
    for i, row in enumerate(rows):
        cells = row.find_all(["td", "th"])
        cell_texts = [c.get_text(strip=True) for c in cells]
        lines.append("| " + " | ".join(cell_texts) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * len(cell_texts)) + " |")

    return "\n".join(lines)


def _list_to_markdown(list_el: Any) -> str:
    """Convertit une liste HTML en Markdown."""
    items = list_el.find_all("li", recursive=False)
    if not items:
        return ""

    lines: list[str] = []
    is_ordered = list_el.name == "ol"
    for i, item in enumerate(items, 1):
        text = item.get_text(strip=True)
        if is_ordered:
            lines.append(f"{i}. {text}")
        else:
            lines.append(f"- {text}")

    return "\n".join(lines)
