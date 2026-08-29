"""Extracteur EPUB : .epub.

CdC §7.3 — livre électronique (ZIP + XHTML/OPF), texte dans l'ordre du
spine (ordre de lecture).

D-093 : implémentation native sur `zipfile` + `ElementTree` + BeautifulSoup
(pas de nouvelle dépendance) — `ebooklib`, la bibliothèque EPUB Python la
plus évidente, est en AGPLv3+, strictement interdite (règle 12.1). Le
format EPUB est structurellement un ZIP de XHTML/OPF, très proche de l'ODF
déjà géré nativement dans `extractors/odf.py` — même approche ici.
"""

from __future__ import annotations

import logging
import posixpath
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import unquote

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result, is_zip_bomb
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)


@register(".epub")
class EpubExtractor(Extractor):
    """Extracteur EPUB via zipfile/ElementTree/BeautifulSoup."""

    file_type = "epub"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".epub"

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            # D-093 : garde-fou "bombe zip" avant tout parsing du conteneur.
            if is_zip_bomb(path):
                return ExtractedFile(
                    path=path,
                    relative_path=relative_path,
                    extension="epub",
                    file_type=cls.file_type,
                    size_bytes=path.stat().st_size,
                    status=FileStatus.ERROR,
                    error_message=t("error.zip_bomb_suspected"),
                )

            with zipfile.ZipFile(str(path)) as zf:
                names = set(zf.namelist())

                # DRM (Adobe ADEPT, Readium LCP...) : `META-INF/encryption.xml`
                # signale un contenu chiffré — jamais tenter l'extraction
                # plutôt que de produire du bruit binaire illisible.
                if "META-INF/encryption.xml" in names:
                    return ExtractedFile(
                        path=path,
                        relative_path=relative_path,
                        extension="epub",
                        file_type=cls.file_type,
                        size_bytes=path.stat().st_size,
                        status=FileStatus.ERROR,
                        error_message=t("error.encrypted_epub"),
                    )

                opf_path = _find_opf_path(zf)
                if opf_path is None or opf_path not in names:
                    return ExtractedFile(
                        path=path,
                        relative_path=relative_path,
                        extension="epub",
                        file_type=cls.file_type,
                        size_bytes=path.stat().st_size,
                        status=FileStatus.ERROR,
                        error_message=f"{t('error.corrupt_file')} : container.xml/OPF introuvable",
                    )

                opf_root = ET.fromstring(zf.read(opf_path))
                title, author = _extract_metadata(opf_root)
                manifest = _parse_manifest(opf_root)
                spine_ids = _parse_spine(opf_root)

                opf_dir = posixpath.dirname(opf_path)
                parts: list[str] = []
                skipped: list[str] = []
                for item_id in spine_ids:
                    href = manifest.get(item_id)
                    if not href:
                        skipped.append(item_id)
                        continue
                    item_path = _resolve_spine_item(opf_dir, href, names)
                    if item_path is None:
                        skipped.append(href)
                        continue
                    chapter_text = _extract_xhtml_text(zf.read(item_path))
                    if chapter_text:
                        parts.append(chapter_text)

                full_text = "\n\n---\n\n".join(parts)
                extra_metadata: dict[str, str] = {}
                if title:
                    extra_metadata["epub_title"] = title
                if author:
                    extra_metadata["epub_author"] = author
                if skipped:
                    # D-096 : un item du spine introuvable était sauté en
                    # silence (statut READY, chapitre manquant sans trace).
                    extra_metadata["epub_skipped_items"] = t(
                        "epub.skipped_items_note", count=len(skipped), items=", ".join(skipped)
                    )

                return ExtractedFile(
                    path=path,
                    relative_path=relative_path,
                    extension="epub",
                    file_type=cls.file_type,
                    size_bytes=path.stat().st_size,
                    text=full_text,
                    status=FileStatus.READY,
                    page_count=len(parts),
                    extra_metadata=extra_metadata,
                )
        except Exception as exc:
            logger.exception("Erreur extraction EPUB %s", path)
            return error_result(path, relative_path, cls.file_type, exc)


def _resolve_spine_item(opf_dir: str, href: str, names: set[str]) -> str | None:
    """Chemin ZIP réel d'un item du spine (D-096).

    Les `href` du manifeste sont des IRI : Calibre/Sigil écrivent
    `chap%201.xhtml` pour « chap 1.xhtml ». Sans décodage, 1 chapitre sur 2
    d'un livre à noms de fichiers avec espaces était perdu sans trace.
    """
    for candidate in (href, unquote(href)):
        item_path = posixpath.normpath(posixpath.join(opf_dir, candidate))
        if item_path in names:
            return item_path
    return None


def _find_opf_path(zf: zipfile.ZipFile) -> str | None:
    """Chemin ZIP du fichier OPF (package), lu depuis `META-INF/container.xml`."""
    if "META-INF/container.xml" not in zf.namelist():
        return None
    try:
        root = ET.fromstring(zf.read("META-INF/container.xml"))
    except ET.ParseError:
        return None
    for el in root.iter():
        if el.tag.endswith("}rootfile"):
            return el.get("full-path")
    return None


def _extract_metadata(opf_root: ET.Element) -> tuple[str, str]:
    """Titre et auteur (`dc:title`/`dc:creator`) du bloc `<metadata>` de l'OPF."""
    title = ""
    author = ""
    for el in opf_root.iter():
        if el.tag.endswith("}title") and not title:
            title = (el.text or "").strip()
        elif el.tag.endswith("}creator") and not author:
            author = (el.text or "").strip()
    return title, author


def _parse_manifest(opf_root: ET.Element) -> dict[str, str]:
    """Table `id -> href` du `<manifest>` de l'OPF."""
    manifest: dict[str, str] = {}
    for el in opf_root.iter():
        if el.tag.endswith("}item"):
            item_id = el.get("id")
            href = el.get("href")
            if item_id and href:
                manifest[item_id] = href
    return manifest


def _parse_spine(opf_root: ET.Element) -> list[str]:
    """`idref` du `<spine>` de l'OPF, dans l'ordre de lecture."""
    for el in opf_root.iter():
        if el.tag.endswith("}spine"):
            idrefs: list[str] = []
            for child in el:
                if child.tag.endswith("}itemref"):
                    idref = child.get("idref")
                    if idref:
                        idrefs.append(idref)
            return idrefs
    return []


def _extract_xhtml_text(xhtml_bytes: bytes) -> str:
    """Texte d'un chapitre XHTML — réutilise le parcours structuré déjà
    testé de `extractors/html.py` (titres → Markdown, tableaux, listes,
    ordre séquentiel du DOM) plutôt que de dupliquer cette logique."""
    from bs4 import BeautifulSoup, Tag

    from docfuse.extractors.html import _extract_elements

    soup = BeautifulSoup(xhtml_bytes, "lxml")
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    body = soup.find("body")
    body_tag: Tag = body if isinstance(body, Tag) else soup

    parts: list[str] = []
    _extract_elements(body_tag, parts, {"count": 0})
    return "\n\n".join(parts)
