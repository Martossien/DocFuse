"""Extracteur MSG : .msg (email Outlook).

CdC §7.3 — en-têtes utiles + corps texte/html→texte, même esprit que
`extractors/eml.py`.

D-094 : via `python-oxmsg` (MIT, même auteur que python-docx/python-pptx),
lecture directe du conteneur OLE2 (spec MS-OXMSG) — aucune dépendance
externe, aucun binaire.

D-104 : robustesse totale sur les .msg réels (bug production Windows).
Deux causes d'échec en masse ont été corrigées :

* le nom de pièce jointe était lu via `Attachment.long_filename`, attribut
  qui n'existe pas dans `python-oxmsg` (l'API réelle est `file_name`) —
  `AttributeError` sur tout mail avec pièce jointe ;
* `Message.body` lève `UnicodeDecodeError` quand le corps est un
  `PtypString8` dont la code page annoncée (souvent 65001/UTF-8) ne
  correspond pas aux octets réels (cp1252 dans les mails français : é, è,
  à, €). Le flux brut est alors relu dans le conteneur OLE2.

D-106 : le correctif D-104 laissait passer sa propre classe de défaut — de
la perte silencieuse — sur cinq points, tous corrigés ici :

1. `subject` et `sender` étaient lus par `_safe()`, qui rend `""` sans
   jamais tenter la relecture brute. Or ils passent par le **même**
   `String8Property` que `body` : sur un mail à code page mensongère, le
   corps était récupéré mais le mail sortait en `READY` amputé de son sujet
   et de son expéditeur. Ils passent désormais par `_property_text()`.
2. le décodage de repli réimplémentait une cascade `cp1252 → latin-1`
   strictement inférieure à `core/encoding.detect_encoding()` : cp1252 ne
   lève que sur 5 octets indéfinis, donc « réussissait » sur de l'UTF-8
   valide et rendait du mojibake (`RÃ©union`). On réutilise la détection du
   cœur (BOM → UTF-8 strict → presque-UTF-8 → cp1252 avec contrôle de
   plausibilité → charset-normalizer → latin-1) + `repair_mojibake()`.
3. `attachment_count` vient d'un `struct.unpack("<8x4I", …)` — un entier
   non signé 32 bits, sans borne haute : `["?"] * 4294967295` est un
   `MemoryError`, donc un SIGKILL, pas une exception rattrapable. Plafonné
   par `MSG_MAX_ATTACHMENT_PLACEHOLDERS`.
4. l'ordre des flux relus commençait par `PtypString8` (8 bits, code page
   ambiguë) alors qu'Outlook écrit souvent les deux variantes et que
   `PtypString` est toujours de l'utf-16-le sans ambiguïté : l'Unicode est
   désormais essayé en premier.
5. le nom de pièce jointe n'avait aucun repli brut (il retombait sur `"?"`
   dès que `file_name` levait) et un seul destinataire illisible faisait
   perdre **tous** les destinataires (`_safe` tout-ou-rien sur la liste).

Principe : aucun `.msg` ne doit faire échouer l'extraction. Chaque
propriété est lue défensivement ; au pire un champ manque, jamais le
fichier entier.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from docfuse.constants import MSG_MAX_ATTACHMENT_PLACEHOLDERS
from docfuse.core.encoding import detect_encoding, repair_mojibake
from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result, file_type_for
from docfuse.extractors.eml import _render_body
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# Identifiants MS-OXMSG utiles pour relire un flux brut sans passer par le
# décodage de `python-oxmsg` (constantes dupliquées volontairement : elles
# sont figées par la spec et `oxmsg.domain.constants` est un module privé).
_PID_SUBJECT = 0x0037  # PidTagSubject
_PID_SENDER_EMAIL_ADDRESS = 0x0C1F  # PidTagSenderEmailAddress
_PID_SENDER_SMTP_ADDRESS = 0x5D01  # PidTagSenderSmtpAddress
_PID_SENDER_NAME = 0x0C1A  # PidTagSenderName
_PID_BODY = 0x1000  # PidTagBody
_PID_BODY_HTML = 0x1013  # PidTagHtml / PidTagBodyHtml
_PID_ATTACH_LONG_FILENAME = 0x3707  # PidTagAttachLongFilename
_PID_ATTACH_FILENAME = 0x3704  # PidTagAttachFilename

# L'expéditeur peut être stocké sous trois propriétés selon le client ; la
# plus précise d'abord, le simple nom d'affichage en dernier recours.
_PIDS_SENDER = (_PID_SENDER_EMAIL_ADDRESS, _PID_SENDER_SMTP_ADDRESS, _PID_SENDER_NAME)

_PTYP_STRING = 0x001F  # chaîne Unicode, toujours utf-16-le — sans ambiguïté
_PTYP_STRING8 = 0x001E  # chaîne 8 bits, code page du message (souvent fausse)
_PTYP_BINARY = 0x0102  # HTML stocké en binaire (cas courant aujourd'hui)

# D-106 : l'Unicode d'abord. Outlook écrit fréquemment les deux variantes du
# même champ ; commencer par le 8 bits faisait sortir `CoÃ»t 12â‚¬` alors que
# le flux `PtypString` voisin donnait `Coût 12€` sans la moindre heuristique.
_PTYP_ORDER: tuple[int, ...] = (_PTYP_STRING, _PTYP_STRING8, _PTYP_BINARY)

# Noms d'attribut successivement essayés pour le nom d'une pièce jointe.
# D-106 : réduits aux deux seuls qui existent — `file_name` est l'API réelle
# de `python-oxmsg`, `display_name` couvre les doubles de test et une
# éventuelle évolution. Les six autres (dont `name`, assez générique pour
# capter un attribut sans rapport) n'existaient dans aucune version publiée.
_ATTACHMENT_NAME_ATTRS: tuple[str, ...] = ("file_name", "display_name")


@register(".msg")
class MsgExtractor(Extractor):
    """Extracteur MSG (email Outlook) via python-oxmsg."""

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
                extension=file_type_for(path),
                file_type=file_type_for(path),
                size_bytes=path.stat().st_size,
                text=text,
                status=FileStatus.READY,
            )
        except Exception as exc:
            logger.exception("Erreur extraction MSG %s", path)
            return error_result(path, relative_path, exc)


def _safe(getter: Callable[[], _T], default: _T) -> _T:
    """Évalue `getter` en absorbant toute exception.

    Les propriétés de `python-oxmsg` sont paresseuses : un mail mal encodé
    ne lève pas au chargement mais à la lecture du champ. Un champ illisible
    ne doit jamais coûter le fichier entier (D-104)."""
    try:
        return getter()
    except Exception:
        logger.debug("Propriété MSG illisible, ignorée", exc_info=True)
        return default


def _decode_8bit(raw: bytes) -> str:
    """Décode un flux 8 bits dont la code page annoncée est fausse ou absente.

    D-106 : délègue à `core/encoding.py`. La cascade maison
    `cp1252 → latin-1 → utf-8/replace` n'essayait **jamais** l'UTF-8 en
    premier — cp1252 ne lève que sur 5 octets indéfinis, donc il « réussit »
    sur presque tout : un corps UTF-8 valide sortait en `RÃ©union budgÃ©taire`.
    C'est exactement la régression que D-097 avait corrigée côté fichiers
    texte ; `detect_encoding()` traite en plus le BOM, l'UTF-8 tronqué
    (D-097) et la plausibilité cp1252 (D-093)."""
    encoding, data = detect_encoding(raw)
    return repair_mojibake(data.decode(encoding, errors="replace"))


def _raw_string_property(obj: Any, *pids: int) -> str:
    """Relit une propriété texte directement dans le conteneur OLE2.

    Court-circuite le décodage de `python-oxmsg` (qui applique la code page
    déclarée par le message, parfois mensongère). Fonctionne pour un
    `Message` comme pour un `Attachment` : les deux exposent un `_storage`
    avec `property_stream_bytes(pid, ptyp)` (contrat vérifié par
    `tests/test_extractors/test_msg.py::TestOxmsgContract`).

    Args:
        obj: Objet oxmsg porteur d'un `_storage`.
        pids: Identifiants de propriété essayés dans l'ordre.

    Returns:
        La première valeur non vide trouvée, sinon une chaîne vide.
    """
    reader = getattr(getattr(obj, "_storage", None), "property_stream_bytes", None)
    if reader is None:
        return ""

    for pid in pids:
        for ptyp in _PTYP_ORDER:
            try:
                raw = bytes(reader(pid, ptyp))
            except Exception:
                # Type de propriété absent pour ce pid : cas normal de la cascade,
                # dit au niveau `debug` pour rester diagnosticable (D-104).
                logger.debug(
                    "Propriété MSG %#06x/%#06x illisible en brut", pid, ptyp, exc_info=True
                )
                continue
            if not raw:
                continue
            if ptyp == _PTYP_STRING:
                return raw.decode("utf-16-le", errors="replace")
            # D-106 : DEBUG et non WARNING — ce message sortait par propriété
            # et par fichier, sans compteur ni nom de fichier, et parlait du
            # « corps » alors qu'il sert aussi le sujet, l'expéditeur, le HTML
            # et les pièces jointes. Sur un dossier de centaines de mails
            # c'était exactement le bruit console supprimé par D-105 côté
            # openpyxl. Le repli n'est pas une anomalie à signaler à
            # l'utilisateur : le texte est récupéré.
            logger.debug("Flux MSG 0x%04X en 8 bits mal étiqueté, décodage de repli", pid)
            return _decode_8bit(raw)
    return ""


def _property_text(obj: Any, attr: str, *pids: int) -> str:
    """Valeur texte d'une propriété, avec relecture brute en repli.

    Le repli n'est tenté que si l'accesseur a levé (typiquement
    `UnicodeDecodeError`) : une propriété absente vaut légitimement `None`."""
    try:
        return str(getattr(obj, attr) or "")
    except Exception:
        logger.debug("Propriété MSG %s illisible, relecture brute", attr, exc_info=True)
    return _raw_string_property(obj, *pids)


def _recipient_label(recipient: Any) -> str:
    """« Nom <adresse> » d'un destinataire ; chaîne vide sans adresse."""
    email = _safe(lambda: recipient.email_address, "") or ""
    if not email:
        return ""
    name = _safe(lambda: recipient.name, "") or ""
    return f"{name} <{email}>" if name else email


def _recipient_labels(msg: Any) -> list[str]:
    """Étiquettes des destinataires, un `try` **par destinataire**.

    D-106 : `list(msg.recipients)` était enveloppé dans un seul `_safe()` —
    tout-ou-rien. Un unique destinataire dont la construction lève (storage
    de destinataire corrompu) faisait perdre en silence la liste entière.
    L'itérateur est consommé élément par élément pour n'en perdre qu'un.
    """
    labels: list[str] = []
    try:
        iterator = iter(msg.recipients)
    except Exception:
        logger.debug("Liste des destinataires MSG illisible", exc_info=True)
        return labels
    while True:
        try:
            recipient = next(iterator)
        except StopIteration:
            break
        except Exception:
            logger.debug("Destinataire MSG illisible, ignoré", exc_info=True)
            continue
        label = _recipient_label(recipient)
        if label:
            labels.append(label)
    return labels


def _attachment_name(attachment: Any) -> str:
    """Nom d'une pièce jointe, quel que soit l'attribut exposé.

    D-104 : `long_filename` n'existe pas dans `python-oxmsg` — l'API réelle
    est `file_name`.
    D-106 : `file_name` traverse le même décodage que `subject` ; sur un mail
    à code page mensongère il lève et on retombait sur `"?"` alors que le nom
    est lisible dans le flux brut. Relecture brute de
    `PidTagAttachLongFilename` puis `PidTagAttachFilename` en dernier
    recours."""
    for attr in _ATTACHMENT_NAME_ATTRS:
        try:
            value = getattr(attachment, attr, None)
        except Exception:
            logger.debug("Attribut %s illisible sur une pièce jointe MSG", attr, exc_info=True)
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    raw = _raw_string_property(attachment, _PID_ATTACH_LONG_FILENAME, _PID_ATTACH_FILENAME)
    return raw.strip() or "?"


def _announced_attachments(msg: Any) -> str:
    """Ligne de pièces jointes quand aucune n'a pu être listée.

    D-106 : `attachment_count` est lu par `struct.unpack("<8x4I", …)` — un
    entier **non signé 32 bits** sans borne haute. Un fichier corrompu ou
    hostile annonçant 4 294 967 295 pièces jointes faisait allouer 34 Go de
    pointeurs puis joindre 8 Go de chaînes : un `MemoryError`, c'est-à-dire
    un SIGKILL du processus entier, pas une exception rattrapable (même
    classe que D-078 et D-096). Au-delà de
    `MSG_MAX_ATTACHMENT_PLACEHOLDERS`, on écrit le nombre annoncé au lieu de
    le matérialiser — la trace reste, la mémoire aussi."""
    count = max(_safe(lambda: int(msg.attachment_count), 0), 0)
    if count == 0:
        return ""
    if count > MSG_MAX_ATTACHMENT_PLACEHOLDERS:
        return f"[pièces jointes : {count} annoncées, illisibles]"
    return f"[pièces jointes : {', '.join(['?'] * count)}]"


def _normalize_header(value: str) -> str:
    """Aplati le repliement de ligne RFC 822 (`\\r\\n\\t`) d'une valeur
    d'en-tête MSG brute en une seule ligne lisible."""
    return " ".join(value.split())


def _render_msg(msg: Any) -> str:
    """Rend un message MSG : en-têtes utiles, corps, pièces jointes listées
    par nom (contenu non extrait, hors périmètre v1).

    Aucune propriété n'est lue sans garde : un mail dont un seul champ est
    illisible reste extrait au mieux (D-104)."""
    blocks: list[str] = []

    # D-106 : `_property_text` et non `_safe` — `Message.subject` passe par le
    # même `String8Property` que `Message.body` : si le corps lève, le sujet
    # lève aussi, et `_safe` rendait `""` en silence.
    subject = _property_text(msg, "subject", _PID_SUBJECT)
    if subject:
        blocks.append(f"**Sujet** : {subject}")

    sender = _property_text(msg, "sender", *_PIDS_SENDER)
    if sender:
        blocks.append(f"**De** : {_normalize_header(sender)}")

    recipient_parts = _recipient_labels(msg)
    if recipient_parts:
        blocks.append(f"**À** : {', '.join(recipient_parts)}")

    sent_date: Any = _safe(lambda: msg.sent_date, None)
    if sent_date:
        blocks.append(f"**Date** : {sent_date}")

    blocks.append("")

    body = _render_body(
        _property_text(msg, "body", _PID_BODY),
        _property_text(msg, "html_body", _PID_BODY_HTML),
    )
    if body:
        blocks.append(body)

    attachments: list[Any] = _safe(lambda: list(msg.attachments), [])
    names = [_attachment_name(a) for a in attachments]
    if names:
        blocks.append(f"[pièces jointes : {', '.join(names)}]")
    else:
        # Les pièces jointes sont annoncées mais illisibles : on garde la trace.
        announced = _announced_attachments(msg)
        if announced:
            blocks.append(announced)

    return "\n".join(blocks)
