"""Extracteur MHTML/MHT : .mhtml, .mht.

CdC §7.3 — Corps HTML→texte si simple.

MHTML (MIME HTML) est un format d'archive web qui contient du HTML
et ses ressources (images, CSS) encodées en MIME multipart.
On extrait le HTML de la partie text/html et le convertit en texte.
"""

from __future__ import annotations

import logging
from email import policy
from email.parser import BytesParser
from pathlib import Path

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)


@register(".mhtml", ".mht")
class MhtmlExtractor(Extractor):
    """Extracteur MHTML/MHT — parse le MIME multipart et extrait le HTML."""

    file_type = "mhtml"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in (".mhtml", ".mht")

    @classmethod
    def extract(cls, path: Path, relative_path: str) -> ExtractedFile:
        try:
            with open(path, "rb") as f:
                msg = BytesParser(policy=policy.default).parse(f)

            parts: list[str] = []
            image_count = 0

            # Parcourir les parties MIME
            for part in msg.walk() if msg.is_multipart() else [msg]:
                content_type = part.get_content_type()
                if content_type == "text/html":
                    html_content = part.get_content()
                    text = _html_to_text(str(html_content))
                    if text:
                        parts.append(text)
                elif content_type.startswith("image/"):
                    image_count += 1

            full_text = "\n\n".join(parts)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=path.suffix.lower().lstrip("."),
                file_type=path.suffix.lower().lstrip("."),
                size_bytes=path.stat().st_size,
                text=full_text,
                status=FileStatus.READY,
                image_count=image_count,
            )
        except Exception as exc:
            logger.exception("Erreur extraction MHTML %s", path)
            return error_result(path, relative_path, cls.file_type, exc)


def _html_to_text(html: str) -> str:
    """Convertit un fragment HTML en texte simple.

    D-081 : le `alt` des images n'était jamais extrait (contrairement à
    `extractors/html.py`) — une archive web a souvent des diagrammes/
    captures d'écran dont le texte alternatif porte l'information utile.
    Remplace chaque `<img>` par un marqueur texte, même convention que
    `html.py` (`[image: ...]` / `[image sans description]`), avant
    `get_text()`.
    """
    try:
        from bs4 import BeautifulSoup, NavigableString

        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all(["script", "style", "noscript"]):
            tag.decompose()
        for img in soup.find_all("img"):
            alt_raw = img.get("alt", "")
            alt = str(alt_raw).strip() if alt_raw else ""
            placeholder = f"[image: {alt}]" if alt else "[image sans description]"
            img.replace_with(NavigableString(placeholder))
        return soup.get_text(separator="\n", strip=True)
    except Exception:
        return html
