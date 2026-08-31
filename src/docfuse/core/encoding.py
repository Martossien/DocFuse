"""Détection d'encodage et réparation de mojibake — service transverse.

CdC §7.2 — Encodage : BOM, puis UTF-8, puis cp1252, latin-1 en dernier.

D-106 : ces fonctions vivaient dans `extractors/text.py`. Cinq extracteurs
(`csv_tsv`, `html`, `eml`, `markdown`, `xml_json`) en dépendaient déjà, et
`extractors/msg.py` devait s'en servir à son tour : importer `text.py`
depuis un autre extracteur y déclenche l'enregistrement d'un extracteur
(`@register`) comme effet de bord d'un besoin de décodage, ce qui n'a aucun
sens. Le décodage est un service du cœur, pas d'un extracteur ; il est donc
remonté dans `core/`. `extractors/text.py` réexporte les mêmes noms (aucun
appelant existant, aucun test, ne casse) mais la définition est ici — une
seule copie.
"""

from __future__ import annotations

import logging
import unicodedata

from docfuse.constants import (
    ENCODING_MAX_CONTROL_RATIO,
    ENCODING_MAX_UTF8_REPLACEMENT_RATIO,
    ENCODING_PLAUSIBILITY_SAMPLE_CHARS,
)
from docfuse.i18n import t

logger = logging.getLogger(__name__)

__all__ = [
    "decode_text",
    "decode_text_with_note",
    "detect_encoding",
    "mojibake_metadata",
    "repair_mojibake",
]


def _looks_plausible(text: str) -> bool:
    """Garde-fou après un décodage cp1252 réussi (D-093, précisé D-097).

    Ce que ce ratio détecte réellement : des octets de contrôle ASCII bruts
    (NUL, etc.) en rafale — typiquement un fichier binaire ou de l'UTF-16
    sans BOM, que cp1252 « décode » sans erreur. Ce qu'il ne détecte PAS
    (docstring D-093 trop optimiste) : un vrai texte UTF-8 pris pour du
    cp1252 — cp1252 lève sur ses 5 octets indéfinis et ne produit jamais de
    caractère de contrôle pour les autres octets hauts ; ce cas est traité
    en amont par `_decode_nearly_utf8`.

    Échantillonné sur `ENCODING_PLAUSIBILITY_SAMPLE_CHARS` pour un coût
    borné même sur un gros fichier.
    """
    sample = text[:ENCODING_PLAUSIBILITY_SAMPLE_CHARS]
    if not sample:
        return True
    control_count = sum(1 for c in sample if c not in "\t\n\r" and unicodedata.category(c) == "Cc")
    return (control_count / len(sample)) <= ENCODING_MAX_CONTROL_RATIO


def _is_nearly_utf8(data: bytes) -> bool:
    """Vrai si `data` est de l'UTF-8 à une fraction négligeable d'octets
    invalides près (`ENCODING_MAX_UTF8_REPLACEMENT_RATIO`), D-097."""
    decoded = data.decode("utf-8", errors="replace")
    if not decoded:
        return False
    replacements = decoded.count("�")
    if replacements == 0:
        return True
    return replacements / len(decoded) <= ENCODING_MAX_UTF8_REPLACEMENT_RATIO


def detect_encoding(data: bytes) -> tuple[str, bytes]:
    """Détecte l'encodage d'un fichier texte.

    Ordre de tentative (CdC §7.2) :
    1. BOM UTF-8/UTF-16 → encodage correspondant
    2. UTF-8 strict
    3. cp1252 (Windows Latin-1, très fréquent), accepté seulement si le
       résultat est plausible (D-093)
    4. charset-normalizer (fallback encodages exotiques)
    5. latin-1 (dernier recours, ne rate jamais)

    Returns:
        Tuple (encodage détecté, données sans BOM si applicable).
    """
    # 1. BOM
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", data[3:]
    if data.startswith(b"\xff\xfe"):
        return "utf-16", data  # M-01: "utf-16" strippe le BOM automatiquement
    if data.startswith(b"\xfe\xff"):
        return "utf-16", data  # M-01: "utf-16" strippe le BOM automatiquement

    # 2. UTF-8 strict
    try:
        data.decode("utf-8")
        return "utf-8", data
    except UnicodeDecodeError:
        pass

    # 2b. UTF-8 « presque » valide (D-097) : une seule séquence multi-octets
    # tronquée (fin de fichier coupée, log tourné au milieu d'un caractère)
    # faisait échouer le test strict, puis cp1252 « réussissait » et TOUT le
    # fichier sortait en `Ã©` — ensuite « réparé » par ftfy et signalé comme
    # mojibake : doublement trompeur (mauvais encodage rapporté, caractère
    # tronqué survivant en `Ã`). Si le décodage tolérant ne produit qu'une
    # part négligeable de U+FFFD, c'est de l'UTF-8.
    if _is_nearly_utf8(data):
        return "utf-8", data

    # 3. cp1252 (Windows Latin-1 étendu — très fréquent sous Windows)
    # Essayer cp1252 AVANT charset-normalizer car ce dernier peut
    # retourner des encodages improbables (ex: mac_latin2) pour les fichiers courts.
    try:
        decoded = data.decode("cp1252")
        if _looks_plausible(decoded):
            return "cp1252", data
    except UnicodeDecodeError:
        pass

    # 4. charset-normalizer (fallback pour les encodages exotiques)
    try:
        from charset_normalizer import from_bytes

        result = from_bytes(data).best()
        if result and result.encoding:
            return result.encoding, data
    except Exception:
        pass

    # 5. latin-1 (ne rate jamais)
    return "latin-1", data


def repair_mojibake(text: str) -> str:
    """Répare un mojibake évident (encodage incohérent, double-encodage
    UTF-8/Latin-1, octets Windows-1252 égarés dans de l'UTF-8...) via
    `ftfy` — jamais d'exception : renvoie le texte original si `ftfy`
    échoue (D-093).

    Configuration volontairement restreinte à la seule détection/
    correction d'encodage corrompu (`fix_encoding` et sa famille — vérifié
    en conditions réelles : répare de vrais octets cp1252 égarés comme
    `\\x92` → `’`). Quatre options par défaut de `ftfy` désactivées après
    avoir trouvé, en testant sur ~/Téléchargements, qu'elles modifiaient
    des centaines de fichiers non corrompus — ce sont des normalisations
    cosmétiques, pas des réparations de corruption :
    `uncurl_quotes` (guillemets typographiques légitimes `’` → `'` ASCII),
    `fix_latin_ligatures` (`ﬁ` → `fi`), `fix_line_breaks` (CRLF → LF,
    aurait changé le comportement de tous les fichiers texte sans lien
    avec le mojibake, alors que la gestion des fins de ligne est déjà un
    choix explicite du corpus généré, pas de l'extraction),
    `fix_character_width` (constaté sur un vrai fichier JS : altérait un
    littéral de chaîne listant les espaces Unicode utilisé par du code
    fonctionnel — et sur un vrai JSON avec du texte chinois : convertissait
    des virgules chinoises pleine chasse `，`, une ponctuation correcte
    pour cette langue, en virgules ASCII).
    """
    # D-097 : chemin rapide, sortie identique. `ftfy` coûte ~10 µs par
    # ligne quel que soit le contenu (2,4 s mesurées sur 200 000 lignes de
    # code ASCII) — payé par tout `.py/.log/.json/.csv/.md`. Avec la
    # configuration ci-dessous, seules restent des heuristiques agissant sur
    # des caractères non-ASCII (mojibake, C1, substituts) : sur du texte
    # purement ASCII, rien ne peut changer — on rend le texte tel quel
    # (garde `isascii()` mesurée à ~20 ms sur le même fichier).
    if text.isascii():
        return text
    try:
        import ftfy

        # D-097 : 4 options par défaut de plus désactivées, trouvées en
        # conditions réelles après D-093 : `unescape_html` décodait les
        # entités (`&amp;` → `&`) ligne par ligne — un JSON/Markdown sain
        # était réécrit AVANT `json.loads`, et de façon incohérente dans un
        # même fichier ; `remove_terminal_escapes` et `remove_control_chars`
        # retiraient les codes ANSI (ESC) d'un `.log` ; `normalization="NFC"`
        # réécrivait du texte NFD légitime. Aucune n'est une réparation de
        # corruption d'encodage — l'unique mission de cette fonction.
        config = ftfy.TextFixerConfig(
            uncurl_quotes=False,
            fix_latin_ligatures=False,
            fix_line_breaks=False,
            fix_character_width=False,
            unescape_html=False,
            remove_terminal_escapes=False,
            remove_control_chars=False,
            normalization=None,
        )
        return ftfy.fix_text(text, config=config)
    except Exception:
        logger.warning("Échec de la réparation mojibake (ftfy)", exc_info=True)
        return text


def decode_text(raw: bytes) -> tuple[str, str, bool]:
    """Détecte l'encodage, décode, puis répare un éventuel mojibake (D-093).

    Args:
        raw: Octets bruts du fichier.

    Returns:
        Tuple (encodage détecté, texte final, `True` si le texte a été
        modifié par la réparation mojibake). Jamais silencieux : les
        appelants doivent tracer une modification via
        `extra_metadata["mojibake_repaired"]` (voir `core/notes.py`).
    """
    encoding, data = detect_encoding(raw)
    original = data.decode(encoding, errors="replace")
    repaired = repair_mojibake(original)
    return encoding, repaired, repaired != original


def mojibake_metadata(repaired: bool) -> dict[str, str]:
    """Note de transparence à poser dans `extra_metadata` quand la réparation
    mojibake a modifié le texte (D-099 : un seul endroit, six copies avant)."""
    return {"mojibake_repaired": t("text.mojibake_repaired_note")} if repaired else {}


def decode_text_with_note(raw: bytes) -> tuple[str, str, dict[str, str]]:
    """`decode_text()` + note de transparence prête pour `extra_metadata`.

    Returns:
        Tuple (encodage détecté, texte final, métadonnées à fusionner dans
        `ExtractedFile.extra_metadata` — vide si rien n'a été réparé).
    """
    encoding, text, repaired = decode_text(raw)
    return encoding, text, mojibake_metadata(repaired)
