"""Tests de l'extracteur MSG (email Outlook).

CdC §7.3 — en-têtes utiles + corps, via `python-oxmsg` (D-094).

Pas de fixture binaire committée : contrairement aux autres formats,
`python-oxmsg` ne peut qu'ouvrir des fichiers `.msg` (aucune bibliothèque
disponible pour en écrire un dans ce sandbox, et Outlook n'est pas
disponible pour en générer un). La logique de correspondance
`Message -> ExtractedFile` est donc testée via un double de `Message`
plutôt qu'un vrai binaire — le parsing OLE2/MS-OXMSG lui-même est la
responsabilité de `python-oxmsg`, déjà vérifié manuellement sur un
fichier `.msg` réel avant l'adoption de la dépendance (D-094).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

from docfuse.extractors.msg import MsgExtractor
from docfuse.models.file_status import FileStatus


@dataclass
class _FakeRecipient:
    name: str | None
    email_address: str | None


@dataclass
class _FakeAttachment:
    long_filename: str | None


@dataclass
class _FakeMessage:
    subject: str | None = None
    sender: str | None = None
    recipients: list[_FakeRecipient] = field(default_factory=list)
    sent_date: datetime | None = None
    body: str | None = None
    html_body: str | None = None
    attachment_count: int = 0
    attachments: list[_FakeAttachment] = field(default_factory=list)


def _patch_load(monkeypatch: pytest.MonkeyPatch, fake: _FakeMessage) -> None:
    import oxmsg

    monkeypatch.setattr(oxmsg.Message, "load", staticmethod(lambda _path: fake))


class TestMsgExtractor:
    def test_accepts(self) -> None:
        assert MsgExtractor.accepts(Path("email.msg")) is True
        assert MsgExtractor.accepts(Path("email.eml")) is False

    def test_safe_extract_no_crash(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.msg"
        result = MsgExtractor.safe_extract(f, "nonexistent.msg")
        assert result.status is FileStatus.ERROR

    def test_corrupt_msg_gives_error(self, tmp_path: Path) -> None:
        f = tmp_path / "broken.msg"
        f.write_bytes(b"ceci n'est pas un fichier .msg valide")

        result = MsgExtractor.extract(f, "broken.msg")
        assert result.status is FileStatus.ERROR

    def test_extract_maps_headers_and_body(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeMessage(
            subject="Réunion projet",
            # Repliement RFC 822 réel (\r\n\t), comme renvoyé par python-oxmsg (D-094)
            sender='"Alice Dupont"\r\n\t<alice@example.com>',
            recipients=[_FakeRecipient("Bob Martin", "bob@example.com")],
            sent_date=datetime(2026, 1, 15, 10, 30),
            body="Corps du message avec suffisamment de texte pour le test.",
        )
        _patch_load(monkeypatch, fake)
        f = tmp_path / "email.msg"
        f.write_bytes(b"peu importe, Message.load est mocke")

        result = MsgExtractor.extract(f, "email.msg")
        assert result.status is FileStatus.READY
        assert "**Sujet** : Réunion projet" in result.text
        assert '**De** : "Alice Dupont" <alice@example.com>' in result.text
        assert "**À** : Bob Martin <bob@example.com>" in result.text
        assert "Corps du message" in result.text

    def test_extract_falls_back_to_html_body(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeMessage(
            subject="HTML seulement",
            body=None,
            html_body="<html><body><p>CONTENU_HTML_SEUL</p></body></html>",
        )
        _patch_load(monkeypatch, fake)
        f = tmp_path / "html_only.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "html_only.msg")
        assert result.status is FileStatus.READY
        assert "CONTENU_HTML_SEUL" in result.text

    def test_extract_lists_attachment_names(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeMessage(
            subject="Avec pièce jointe",
            body="Voir pièce jointe.",
            attachment_count=1,
            attachments=[_FakeAttachment("rapport.pdf")],
        )
        _patch_load(monkeypatch, fake)
        f = tmp_path / "with_attachment.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "with_attachment.msg")
        assert result.status is FileStatus.READY
        assert "rapport.pdf" in result.text
