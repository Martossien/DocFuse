"""Extracteur EML : .eml.

CdC §7.3 — En-têtes utiles + corps texte/html→texte.

D-070 : un email transféré en pièce jointe (`message/rfc822`) est un
sous-message complet imbriqué. `msg.walk()` le traverse bien, mais la
logique "premier text/plain gagne" faisait que le corps du message
englobant (toujours rencontré en premier dans l'ordre du document) gagnait
systématiquement, et le sujet/corps du message transféré — souvent le
contenu le plus important du fichier — disparaissaient sans trace. Corrigé
en traitant chaque `message/rfc822` comme un sous-message à rendre
séparément (récursif, gère les transferts imbriqués à plusieurs niveaux).
"""

from __future__ import annotations

import logging
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

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

            parts = _render_message(msg, is_nested=False)
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


def _render_message(msg: Any, is_nested: bool) -> list[str]:
    """Rend un message (top-level ou `message/rfc822` imbriqué — email
    transféré en pièce jointe) : en-têtes utiles, corps, puis récursivement
    tout message imbriqué qu'il contiendrait lui-même (D-070)."""
    blocks: list[str] = []
    if is_nested:
        blocks.append("--- Message transféré ---")

    subject = msg.get("Subject", "")
    if subject:
        blocks.append(f"**Sujet** : {subject}")

    from_ = msg.get("From", "")
    if from_:
        blocks.append(f"**De** : {from_}")

    to = msg.get("To", "")
    if to:
        blocks.append(f"**À** : {to}")

    date = msg.get("Date", "")
    if date:
        blocks.append(f"**Date** : {date}")

    blocks.append("")

    body_text, body_html = _extract_direct_body(msg)
    rendered_body = _render_body(body_text, body_html)
    if rendered_body:
        blocks.append(rendered_body)

    for nested in _iter_nested_messages(msg):
        blocks.append("")
        blocks.extend(_render_message(nested, is_nested=True))

    return blocks


def _extract_direct_body(msg: Any) -> tuple[str, str]:
    """Corps direct de `msg` (text/plain, text/html) — sans descendre dans un
    `message/rfc822` imbriqué, traité séparément par `_iter_nested_messages`.

    BUG FIX (v0.1.0) : ne pas dupliquer text/plain ET text/html — on prend
    text/plain en priorité, HTML en repli. "Premier gagnant" par partie,
    mais chaque niveau de message a désormais son propre appel (D-070) : le
    corps de l'englobant ne "vole" plus le slot du message transféré.
    """
    body_text = ""
    body_html = ""
    if msg.is_multipart():
        for part in msg.iter_parts():
            content_type = part.get_content_type()
            if content_type == "message/rfc822":
                continue  # traité par _iter_nested_messages
            if content_type == "text/plain" and not body_text:
                body = part.get_content()
                if body:
                    body_text = str(body)
            elif content_type == "text/html" and not body_html:
                body_html = str(part.get_content())
            elif part.is_multipart():
                nested_text, nested_html = _extract_direct_body(part)
                body_text = body_text or nested_text
                body_html = body_html or nested_html
    else:
        content_type = msg.get_content_type()
        if content_type == "text/html":
            body_html = str(msg.get_content())
        elif content_type != "message/rfc822":
            body_text = str(msg.get_content() or "")

    return body_text, body_html


def _iter_nested_messages(msg: Any) -> list[Any]:
    """Sous-messages `message/rfc822` imbriqués directement (récursif dans
    les conteneurs multipart intermédiaires) — emails transférés en pièce
    jointe (D-070)."""
    nested: list[Any] = []
    if not msg.is_multipart():
        return nested
    for part in msg.iter_parts():
        if part.get_content_type() == "message/rfc822":
            payload = part.get_payload()
            if isinstance(payload, list) and payload:
                nested.append(payload[0])
        elif part.is_multipart():
            nested.extend(_iter_nested_messages(part))
    return nested


def _render_body(body_text: str, body_html: str) -> str:
    """Préférence text/plain, repli HTML→texte (BeautifulSoup)."""
    if body_text:
        return body_text
    if not body_html:
        return ""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(body_html, "lxml")
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text or body_html
    except Exception:
        return body_html
