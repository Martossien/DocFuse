"""Extracteur MSG : .msg (email Outlook).

CdC §7.3 — en-têtes utiles + corps texte/html→texte, même esprit que
`extractors/eml.py`.

D-094 : via `python-oxmsg` (MIT, même auteur que python-docx/python-pptx),
lecture directe du conteneur OLE2 (spec MS-OXMSG) — aucune dépendance
externe, aucun binaire.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.extractors.eml import _render_body
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)


@register(".msg")
class MsgExtractor(Extractor):
    """Extracteur MSG (email Outlook) via python-oxmsg."""

    file_type = "msg"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".msg"

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            from oxmsg import Message

            msg = Message.load(str(path))
            text = _render_msg(msg)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension="msg",
                file_type=cls.file_type,
                size_bytes=path.stat().st_size,
                text=text,
                status=FileStatus.READY,
            )
        except Exception as exc:
            logger.exception("Erreur extraction MSG %s", path)
            return error_result(path, relative_path, cls.file_type, exc)


def _normalize_header(value: str) -> str:
    """Aplati le repliement de ligne RFC 822 (`\\r\\n\\t`) d'une valeur
    d'en-tête MSG brute en une seule ligne lisible."""
    return " ".join(value.split())


def _render_msg(msg: Any) -> str:
    """Rend un message MSG : en-têtes utiles, corps, pièces jointes listées
    par nom (contenu non extrait, hors périmètre v1)."""
    blocks: list[str] = []

    if msg.subject:
        blocks.append(f"**Sujet** : {msg.subject}")
    if msg.sender:
        blocks.append(f"**De** : {_normalize_header(msg.sender)}")

    recipient_parts = [
        f"{r.name} <{r.email_address}>" if r.name else r.email_address
        for r in msg.recipients
        if r.email_address
    ]
    if recipient_parts:
        blocks.append(f"**À** : {', '.join(recipient_parts)}")

    if msg.sent_date:
        blocks.append(f"**Date** : {msg.sent_date}")

    blocks.append("")

    body = _render_body(msg.body or "", msg.html_body or "")
    if body:
        blocks.append(body)

    if msg.attachment_count:
        names = ", ".join(a.long_filename or "?" for a in msg.attachments)
        blocks.append(f"[pièces jointes : {names}]")

    return "\n".join(blocks)
