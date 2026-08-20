"""Extracteur EML : .eml.

CdC §7.3 — En-têtes utiles + corps texte/html→texte.
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


@register(".eml")
class EmlExtractor(Extractor):
    """Extracteur EML (email) via stdlib email module."""

    file_type = "eml"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".eml"

    @classmethod
    def extract(cls, path: Path, relative_path: str) -> ExtractedFile:
        try:
            with open(path, "rb") as f:
                msg = BytesParser(policy=policy.default).parse(f)

            parts: list[str] = []

            # En-têtes utiles
            subject = msg.get("Subject", "")
            if subject:
                parts.append(f"**Sujet** : {subject}")

            from_ = msg.get("From", "")
            if from_:
                parts.append(f"**De** : {from_}")

            to = msg.get("To", "")
            if to:
                parts.append(f"**À** : {to}")

            date = msg.get("Date", "")
            if date:
                parts.append(f"**Date** : {date}")

            parts.append("")

            # Corps — BUG FIX: ne pas dupliquer text/plain ET text/html
            # On prend text/plain en priorité. Si absent, on prend text/html converti.
            body_text = ""
            body_html = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/plain" and not body_text:
                        body = part.get_content()
                        if body:
                            body_text = str(body)
                    elif content_type == "text/html" and not body_html:
                        body_html = str(part.get_content())
            else:
                content_type = msg.get_content_type()
                if content_type == "text/html":
                    body_html = str(msg.get_content())
                else:
                    body_text = str(msg.get_content() or "")

            # Préférence: text/plain si disponible, sinon HTML converti
            if body_text:
                parts.append(body_text)
            elif body_html:
                try:
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(body_html, "lxml")
                    for tag in soup.find_all(["script", "style"]):
                        tag.decompose()
                    text = soup.get_text(separator="\n", strip=True)
                    if text:
                        parts.append(text)
                except Exception:
                    parts.append(body_html)

            full_text = "\n".join(parts)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension="eml",
                file_type=path.suffix.lower().lstrip("."),
                size_bytes=path.stat().st_size,
                text=full_text,
                status=FileStatus.READY,
            )
        except Exception as exc:
            logger.exception("Erreur extraction EML %s", path)
            return error_result(path, relative_path, cls.file_type, exc)
