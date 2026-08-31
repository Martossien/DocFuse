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

import logging
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
    """Double fidèle à l'API réelle de `oxmsg.attachment.Attachment` : le nom
    du fichier est exposé par `file_name` (D-104 — le code lisait
    `long_filename`, qui n'existe pas, d'où l'AttributeError en production)."""

    file_name: str | None


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


def _patch_load(monkeypatch: pytest.MonkeyPatch, fake: object) -> None:
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


# --- D-104/D-106 : robustesse sur les .msg réels (bug production Windows) ---

_PID_SUBJECT = 0x0037
_PID_SENDER_EMAIL_ADDRESS = 0x0C1F
_PID_SENDER_NAME = 0x0C1A
_PID_BODY = 0x1000
_PID_BODY_HTML = 0x1013
_PID_ATTACH_LONG_FILENAME = 0x3707
_PTYP_STRING = 0x001F
_PTYP_STRING8 = 0x001E
_PTYP_BINARY = 0x0102

# Octets cp1252 d'un mail français : é (0xE9), è (0xE8), à (0xE0), € (0x80).
_CP1252_BODY = "Réunion à 9h : 15 € déjà prévus, très bien.".encode("cp1252")
_CP1252_HTML = "<html><body><p>Café déjà prêt</p></body></html>".encode("cp1252")
_SUBJECT_TEXT = "Réunion budgétaire à 14h : coût 12€"
_CP1252_SUBJECT = _SUBJECT_TEXT.encode("cp1252")
_SENDER_TEXT = '"Alice Dupont" <alice@example.com>'


class _FakeStorage:
    """Double du conteneur OLE2 : sert les flux bruts indexés par (pid, ptyp).

    Fidèle à `oxmsg.storage.Storage.property_stream_bytes`, qui lève un
    `KeyError` quand le flux demandé n'existe pas."""

    def __init__(self, streams: dict[tuple[int, int], bytes]) -> None:
        self._streams = streams

    def property_stream_bytes(self, pid: int, ptyp: int) -> bytes:
        return self._streams[(pid, ptyp)]


def _utf8_decode_error(raw: bytes) -> UnicodeDecodeError:
    """L'erreur exacte remontée par oxmsg/properties.py quand la code page
    annoncée (65001) ne correspond pas aux octets 8 bits stockés."""
    return UnicodeDecodeError("utf-8", raw, 1, 2, "invalid continuation byte")


class _BadEncodingMessage:
    """Message dont TOUTES les propriétés texte lèvent — la réalité D-104.

    D-106 : le double précédent exposait `subject` et `sender` comme des
    chaînes littérales, ce qui rendait le défaut invisible. Or `subject`,
    `sender` et `body` passent par le **même** `String8Property` avec la même
    code page mensongère : si le corps lève, le sujet et l'expéditeur lèvent
    aussi. Ici ils lèvent tous, comme sur les mails de production.
    """

    recipients: list[_FakeRecipient] = []
    sent_date = None
    attachment_count = 0
    attachments: list[object] = []

    def __init__(self, streams: dict[tuple[int, int], bytes] | None) -> None:
        self._storage = _FakeStorage(streams) if streams is not None else None

    @property
    def subject(self) -> str:
        raise _utf8_decode_error(_CP1252_SUBJECT)

    @property
    def sender(self) -> str:
        raise _utf8_decode_error(_SENDER_TEXT.encode())

    @property
    def body(self) -> str:
        raise _utf8_decode_error(_CP1252_BODY)

    @property
    def html_body(self) -> str:
        raise _utf8_decode_error(_CP1252_HTML)


class _NamelessAttachment:
    """Pièce jointe n'exposant aucun des noms d'attribut connus."""


class _BrokenNameAttachment:
    """Pièce jointe dont le nom lève à la lecture (propriété paresseuse)."""

    @property
    def file_name(self) -> str:
        raise _utf8_decode_error(b"pi\xe8ce.pdf")

    display_name = "piece_jointe.pdf"


class _RawNameAttachment:
    """Pièce jointe dont *tous* les attributs lèvent, mais dont le flux brut
    `PidTagAttachLongFilename` est lisible (D-106)."""

    def __init__(self, streams: dict[tuple[int, int], bytes]) -> None:
        self._storage = _FakeStorage(streams)

    @property
    def file_name(self) -> str:
        raise _utf8_decode_error(b"bilan.xlsx")

    @property
    def display_name(self) -> str:
        raise _utf8_decode_error(b"bilan.xlsx")


class _UnreadableAttachmentsMessage:
    """Message annonçant des pièces jointes dont le flux est illisible."""

    subject = "PJ perdues"
    sender = None
    recipients: list[_FakeRecipient] = []
    sent_date = None
    body = "Corps du message."
    html_body = None
    attachment_count = 2

    @property
    def attachments(self) -> list[object]:
        raise OSError("flux de pièces jointes illisible")


class _HostileAttachmentCountMessage(_UnreadableAttachmentsMessage):
    """`attachment_count` corrompu : entier non signé 32 bits au maximum.

    D-106 : `["?"] * 4294967295` alloue 34 Go de pointeurs — un `MemoryError`
    est un SIGKILL, pas une exception rattrapable (classe D-078/D-096)."""

    subject = "PJ hostiles"
    attachment_count = 0xFFFFFFFF


class _BrokenRecipient:
    """Destinataire dont l'adresse lève à la lecture."""

    @property
    def email_address(self) -> str:
        raise _utf8_decode_error(b"jos\xe9@example.com")

    @property
    def name(self) -> str:
        raise _utf8_decode_error(b"Jos\xe9")


class _PartiallyBrokenRecipients:
    """Itérable dont la **construction** d'un destinataire lève.

    Reproduit `Message._iter_recipients()` : un générateur qui construit un
    `Recipient` par storage. Un storage corrompu fait lever le générateur
    lui-même, pas seulement la lecture d'un champ."""

    def __init__(self, good: list[_FakeRecipient]) -> None:
        self._good = good

    def __iter__(self) -> object:
        def _gen() -> object:
            yield self._good[0]
            raise OSError("storage de destinataire corrompu")

        return _gen()


class _BrokenRecipientsMessage:
    subject = "Destinataires partiellement illisibles"
    sender = None
    sent_date = None
    body = "Corps."
    html_body = None
    attachment_count = 0
    attachments: list[object] = []

    def __init__(self, recipients: object) -> None:
        self.recipients = recipients  # type: ignore[assignment]


class TestOxmsgContract:
    """D-106 : la relecture brute repose sur deux points d'API privés de
    `python-oxmsg`. S'ils disparaissent, ce test échoue **explicitement**
    plutôt que de laisser l'extracteur se dégrader en silence (tous les
    replis rendraient `""` sans que rien ne le signale)."""

    def test_message_exposes_storage_with_property_stream_bytes(self) -> None:
        import inspect

        from oxmsg.message import Message
        from oxmsg.storage import Storage

        # `Message.__init__(self, storage)` pose `self._storage`.
        source = inspect.getsource(Message.__init__)
        assert "self._storage = storage" in source, (
            "oxmsg.Message n'expose plus `_storage` : la relecture brute des "
            "propriétés MSG (sujet, expéditeur, corps, pièces jointes) est morte."
        )
        reader = getattr(Storage, "property_stream_bytes", None)
        assert callable(reader), "oxmsg.Storage.property_stream_bytes a disparu"
        params = list(inspect.signature(reader).parameters)
        assert params == ["self", "pid", "ptyp"], (
            f"signature inattendue de property_stream_bytes : {params}"
        )

    def test_attachment_exposes_storage(self) -> None:
        import inspect

        from oxmsg.attachment import Attachment

        source = inspect.getsource(Attachment.__init__)
        assert "self._storage = storage" in source, (
            "oxmsg.Attachment n'expose plus `_storage` : le repli brut sur "
            "PidTagAttachLongFilename est mort."
        )

    def test_pids_match_oxmsg_constants(self) -> None:
        """Les PID dupliqués dans `msg.py` sont ceux de la spec MS-OXMSG."""
        from oxmsg.domain import constants as c

        from docfuse.extractors import msg as m

        assert m._PID_SUBJECT == c.PID_SUBJECT
        assert m._PID_SENDER_EMAIL_ADDRESS == c.PID_SENDER_EMAIL_ADDRESS
        assert m._PID_SENDER_SMTP_ADDRESS == c.PID_SENDER_SMTP_ADDRESS
        assert m._PID_SENDER_NAME == c.PID_SENDER_NAME
        assert m._PID_BODY == c.PID_BODY
        assert m._PID_BODY_HTML == c.PID_BODY_HTML
        assert m._PID_ATTACH_LONG_FILENAME == c.PID_ATTACH_LONG_FILENAME
        assert m._PID_ATTACH_FILENAME == c.PID_ATTACH_FILENAME


class TestMsgRobustness:
    """Aucun .msg ne doit faire échouer l'extraction (D-104)."""

    def test_attachment_name_uses_real_oxmsg_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Bug (A) : `Attachment.long_filename` n'existe pas dans python-oxmsg."""
        fake = _FakeMessage(
            subject="Avec pièce jointe",
            body="Voir pièce jointe.",
            attachment_count=1,
            attachments=[_FakeAttachment("bilan_2026.xlsx")],
        )
        _patch_load(monkeypatch, fake)
        f = tmp_path / "pj.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "pj.msg")
        assert result.status is FileStatus.READY
        assert "[pièces jointes : bilan_2026.xlsx]" in result.text

    def test_attachment_without_any_known_name_attribute(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeMessage(
            subject="PJ anonyme",
            body="Corps.",
            attachment_count=1,
            attachments=[_NamelessAttachment()],  # type: ignore[list-item]
        )
        _patch_load(monkeypatch, fake)
        f = tmp_path / "pj_anonyme.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "pj_anonyme.msg")
        assert result.status is FileStatus.READY
        assert "[pièces jointes : ?]" in result.text

    def test_attachment_name_falls_back_when_property_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeMessage(
            subject="PJ illisible",
            body="Corps.",
            attachment_count=1,
            attachments=[_BrokenNameAttachment()],  # type: ignore[list-item]
        )
        _patch_load(monkeypatch, fake)
        f = tmp_path / "pj_illisible.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "pj_illisible.msg")
        assert result.status is FileStatus.READY
        assert "piece_jointe.pdf" in result.text

    def test_cp1252_body_is_recovered_from_raw_stream(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Bug (B) : UnicodeDecodeError sur un corps cp1252 étiqueté UTF-8."""
        fake = _BadEncodingMessage(
            {
                (_PID_BODY, _PTYP_STRING8): _CP1252_BODY,
                (_PID_SUBJECT, _PTYP_STRING8): _CP1252_SUBJECT,
            }
        )
        _patch_load(monkeypatch, fake)
        f = tmp_path / "cp1252.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "cp1252.msg")
        assert result.status is FileStatus.READY
        assert "Réunion à 9h : 15 € déjà prévus" in result.text
        assert f"**Sujet** : {_SUBJECT_TEXT}" in result.text

    def test_cp1252_html_body_is_recovered_when_plain_body_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _BadEncodingMessage({(_PID_BODY_HTML, _PTYP_BINARY): _CP1252_HTML})
        _patch_load(monkeypatch, fake)
        f = tmp_path / "cp1252_html.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "cp1252_html.msg")
        assert result.status is FileStatus.READY
        assert "Café déjà prêt" in result.text

    def test_unreadable_body_without_raw_stream_still_ready(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dernier filet : ni corps décodable ni flux brut — le mail reste extrait."""
        fake = _BadEncodingMessage(None)
        _patch_load(monkeypatch, fake)
        f = tmp_path / "corps_perdu.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "corps_perdu.msg")
        assert result.status is FileStatus.READY
        assert result.text == ""

    def test_broken_recipient_is_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeMessage(
            subject="Destinataire illisible",
            body="Corps.",
            recipients=[
                _BrokenRecipient(),  # type: ignore[list-item]
                _FakeRecipient("Bob Martin", "bob@example.com"),
            ],
        )
        _patch_load(monkeypatch, fake)
        f = tmp_path / "dest.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "dest.msg")
        assert result.status is FileStatus.READY
        assert "**À** : Bob Martin <bob@example.com>" in result.text

    def test_attachments_announced_but_unreadable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_load(monkeypatch, _UnreadableAttachmentsMessage())
        f = tmp_path / "pj_perdues.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "pj_perdues.msg")
        assert result.status is FileStatus.READY
        assert "[pièces jointes : ?, ?]" in result.text


class TestMsgSilentLossD106:
    """D-106 : le correctif D-104 laissait passer sa propre classe de défaut."""

    def test_subject_and_sender_survive_a_lying_codepage(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D1 — `subject`/`sender` passaient par `_safe()` : sur les mails
        visés par D-104, le corps était récupéré mais le mail sortait en
        `READY` **amputé de son sujet et de son expéditeur**, en silence."""
        fake = _BadEncodingMessage(
            {
                (_PID_SUBJECT, _PTYP_STRING8): _CP1252_SUBJECT,
                (_PID_SENDER_EMAIL_ADDRESS, _PTYP_STRING8): _SENDER_TEXT.encode("cp1252"),
                (_PID_BODY, _PTYP_STRING8): _CP1252_BODY,
            }
        )
        _patch_load(monkeypatch, fake)
        f = tmp_path / "sujet_perdu.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "sujet_perdu.msg")
        assert result.status is FileStatus.READY
        assert f"**Sujet** : {_SUBJECT_TEXT}" in result.text
        assert f"**De** : {_SENDER_TEXT}" in result.text

    def test_sender_falls_back_to_sender_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sans adresse SMTP stockée, `PidTagSenderName` fait l'affaire."""
        fake = _BadEncodingMessage({(_PID_SENDER_NAME, _PTYP_STRING8): "Aliénor".encode("cp1252")})
        _patch_load(monkeypatch, fake)
        f = tmp_path / "sender_name.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "sender_name.msg")
        assert "**De** : Aliénor" in result.text

    def test_valid_utf8_stream_is_not_turned_into_mojibake(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D2 — la cascade maison `cp1252 → latin-1` n'essayait jamais UTF-8 :
        cp1252 ne lève que sur 5 octets indéfinis, donc « réussissait » sur un
        corps UTF-8 valide et rendait `RÃ©union budgÃ©taire Ã\xa0 14h`."""
        utf8_body = "Réunion budgétaire à 14h — café…".encode()
        fake = _BadEncodingMessage({(_PID_BODY, _PTYP_STRING8): utf8_body})
        _patch_load(monkeypatch, fake)
        f = tmp_path / "utf8.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "utf8.msg")
        assert "Réunion budgétaire à 14h — café…" in result.text
        assert "Ã©" not in result.text

    def test_truncated_utf8_stream_is_still_read_as_utf8(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D2 (suite) — l'UTF-8 « presque valide » de D-097 : un flux coupé au
        milieu d'un caractère multi-octets ne doit pas basculer tout le corps
        en cp1252."""
        utf8_body = ("Réunion budgétaire à 14h — café " * 50).encode() + "é".encode()[:1]
        fake = _BadEncodingMessage({(_PID_BODY, _PTYP_STRING8): utf8_body})
        _patch_load(monkeypatch, fake)
        f = tmp_path / "utf8_tronque.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "utf8_tronque.msg")
        assert "Réunion budgétaire à 14h — café" in result.text
        assert "Ã©" not in result.text

    def test_hostile_attachment_count_does_not_explode_memory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D3 — `attachment_count` est un entier non signé 32 bits lu dans le
        fichier : `["?"] * 4294967295` = 34 Go de pointeurs, donc un SIGKILL."""
        _patch_load(monkeypatch, _HostileAttachmentCountMessage())
        f = tmp_path / "pj_hostiles.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "pj_hostiles.msg")
        assert result.status is FileStatus.READY
        assert "[pièces jointes : 4294967295 annoncées, illisibles]" in result.text
        assert "?, ?" not in result.text

    def test_attachment_count_at_the_cap_is_still_materialised(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le plafond ne dégrade pas le cas normal (quelques pièces jointes)."""
        from docfuse.constants import MSG_MAX_ATTACHMENT_PLACEHOLDERS

        class _AtCap(_UnreadableAttachmentsMessage):
            attachment_count = MSG_MAX_ATTACHMENT_PLACEHOLDERS

        _patch_load(monkeypatch, _AtCap())
        f = tmp_path / "pj_plafond.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "pj_plafond.msg")
        expected = ", ".join(["?"] * MSG_MAX_ATTACHMENT_PLACEHOLDERS)
        assert f"[pièces jointes : {expected}]" in result.text

    def test_unicode_stream_wins_over_the_8bit_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D4 — Outlook écrit fréquemment les deux variantes du même champ.
        `PtypString` (0x001F) est toujours de l'utf-16-le, sans ambiguïté ;
        commencer par `PtypString8` rendait `CoÃ»t 12â‚¬`."""
        text = "Coût 12€"
        fake = _BadEncodingMessage(
            {
                (_PID_BODY, _PTYP_STRING): text.encode("utf-16-le"),
                (_PID_BODY, _PTYP_STRING8): text.encode("utf-8"),
            }
        )
        _patch_load(monkeypatch, fake)
        f = tmp_path / "deux_flux.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "deux_flux.msg")
        assert text in result.text
        assert "CoÃ»t" not in result.text

    def test_attachment_name_falls_back_to_raw_stream(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D5 — `Attachment.file_name` traverse le même décodage que `subject` :
        sur les mails de D-104 il lève, et on retombait sur `"?"` alors que le
        nom est parfaitement lisible dans `PidTagAttachLongFilename`."""
        attachment = _RawNameAttachment(
            {(_PID_ATTACH_LONG_FILENAME, _PTYP_STRING8): "bilan_été.xlsx".encode("cp1252")}
        )
        fake = _FakeMessage(
            subject="PJ au nom illisible",
            body="Corps.",
            attachment_count=1,
            attachments=[attachment],  # type: ignore[list-item]
        )
        _patch_load(monkeypatch, fake)
        f = tmp_path / "pj_brute.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "pj_brute.msg")
        assert "[pièces jointes : bilan_été.xlsx]" in result.text

    def test_one_broken_recipient_does_not_lose_the_others(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D5 (note liée) — `_safe(lambda: list(msg.recipients), [])` est
        tout-ou-rien : un seul destinataire dont la **construction** lève
        faisait perdre en silence toute la liste."""
        recipients = _PartiallyBrokenRecipients([_FakeRecipient("Bob Martin", "bob@example.com")])
        _patch_load(monkeypatch, _BrokenRecipientsMessage(recipients))
        f = tmp_path / "dest_partiels.msg"
        f.write_bytes(b"peu importe")

        result = MsgExtractor.extract(f, "dest_partiels.msg")
        assert result.status is FileStatus.READY
        assert "**À** : Bob Martin <bob@example.com>" in result.text

    def test_fallback_decoding_is_not_logged_as_a_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """D6 — le repli était journalisé en WARNING par propriété et par
        fichier, sans compteur ni nom de fichier : sur un dossier de centaines
        de mails, exactement le bruit console supprimé par D-105."""
        fake = _BadEncodingMessage(
            {
                (_PID_SUBJECT, _PTYP_STRING8): _CP1252_SUBJECT,
                (_PID_BODY, _PTYP_STRING8): _CP1252_BODY,
            }
        )
        _patch_load(monkeypatch, fake)
        f = tmp_path / "bruit.msg"
        f.write_bytes(b"peu importe")

        with caplog.at_level(logging.WARNING, logger="docfuse.extractors.msg"):
            result = MsgExtractor.extract(f, "bruit.msg")

        assert result.status is FileStatus.READY
        assert caplog.records == []
