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

import codecs
import logging
import unicodedata

from docfuse.constants import (
    ENCODING_MAX_CONTROL_RATIO,
    ENCODING_PLAUSIBILITY_SAMPLE_CHARS,
)
from docfuse.i18n import t

logger = logging.getLogger(__name__)

#: Caractère de remplacement Unicode, produit par tout décodage
#: `errors="replace"` : un octet que l'encodage retenu n'a pas su lire.
REPLACEMENT_CHAR = "�"

__all__ = [
    "REPLACEMENT_CHAR",
    "decode_text",
    "decode_text_with_note",
    "detect_encoding",
    "mojibake_metadata",
    "replacement_metadata",
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


def _is_utf8_truncated_at_end(data: bytes) -> bool:
    """Vrai si `data` est de l'UTF-8 valide, à une unique séquence
    multi-octets **incomplète en toute fin de flux** près (D-097, corrigé
    D-107).

    Pourquoi pas un ratio (la faute corrigée). D-097 justifiait la
    tolérance par « une seule séquence multi-octets tronquée (fin de
    fichier coupée) », mais l'implémentait comme un ratio d'octets
    invalides (`ENCODING_MAX_UTF8_REPLACEMENT_RATIO`, 0,1 %) : le budget
    d'octets illisibles croissait avec la taille du fichier. Un export ERP
    français de 3 Mo majoritairement ASCII, en cp1252, avec un millier
    d'octets accentués (0,035 %) était donc déclaré `utf-8`, décodé avec
    `errors="replace"`, et sortait en `Mme <?>lodie Lef<?>vre` — l'en-tête
    du corpus affirmant `encodage: utf-8`, une affirmation fausse. Mesuré :
    dès 10 000 caractères ASCII, 5 accents suffisaient à basculer.

    Le critère correspond maintenant à l'intention : on décode en flux et
    on autorise le décodeur à garder en attente ce qui traîne à la fin. Si
    tout le reste est de l'UTF-8 strictement valide, la seule anomalie est
    bien une séquence coupée au bout du fichier (fichier tronqué, log
    tourné au milieu d'un caractère) — et le fichier reste lisible en
    UTF-8 plutôt que d'être entièrement transformé en `cafÃ©` par cp1252.
    Le nombre d'octets tolérés ne dépend plus de la taille : il est borné
    par la longueur maximale d'une séquence UTF-8 incomplète (3 octets).

    Ce que ce critère refuse désormais, et qui passait avant :

    - tout octet invalide **ailleurs** qu'à la toute fin, en quelque
      quantité que ce soit — c'est exactement le cas de l'export cp1252 ;
    - un fichier UTF-8 tronqué au **début** (log tourné juste après un
      octet de continuation) : il repart en cp1252. Cas non observé en
      production ; le traiter demanderait de rogner la tête du flux, ce qui
      rouvrirait une porte sur les fichiers cp1252 commençant par un octet
      0x80-0xBF (« ¿ », « « »…). Refus assumé.

    Un flux entièrement fait d'une séquence incomplète (`b"\\xc3"` seul) ne
    produit aucun caractère : il n'est pas reconnu comme UTF-8, comme
    avant.
    """
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        # final=False : une séquence incomplète en fin de flux est mise en
        # attente au lieu de lever ; toute autre anomalie lève toujours.
        decoded = decoder.decode(data, False)
    except UnicodeDecodeError:
        return False
    return bool(decoded)


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

    # 2b. UTF-8 tronqué en fin de flux (D-097, resserré D-107) : une seule
    # séquence multi-octets coupée (fin de fichier tronquée, log tourné au
    # milieu d'un caractère) faisait échouer le test strict, puis cp1252
    # « réussissait » et TOUT le fichier sortait en `Ã©` — ensuite
    # « réparé » par ftfy et signalé comme mojibake : doublement trompeur
    # (mauvais encodage rapporté, caractère tronqué survivant en `Ã`).
    if _is_utf8_truncated_at_end(data):
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


def replacement_metadata(text: str) -> dict[str, str]:
    """Note de transparence quand des caractères restent illisibles (D-107).

    `decode_text()` décode avec `errors="replace"` : tout octet que
    l'encodage retenu n'a pas su lire devient U+FFFD, sans exception ni
    trace. Le corpus affichait alors un `encodage:` péremptoire sur un
    texte silencieusement amputé — pour un rapport qui sert à décider de
    suppressions de fichiers, c'est la perte la plus dangereuse : invisible.
    Le resserrement de `_is_utf8_truncated_at_end` supprime la cause
    massive ; il reste des cas légitimes et bornés (fichier réellement
    tronqué, octet isolé indécodable), et ceux-là doivent se voir dans les
    métadonnées du document, pas seulement dans un journal.

    Limite assumée : le comptage porte sur le texte final, donc un document
    contenant *authentiquement* des U+FFFD dans sa source serait signalé
    lui aussi. La note reste vraie sur le fond (ces caractères sont bien
    illisibles) et le texte n'est jamais modifié.

    Args:
        text: Texte décodé final.

    Returns:
        Métadonnées à fusionner dans `ExtractedFile.extra_metadata`, vides
        si aucun caractère de remplacement ne subsiste.
    """
    count = text.count(REPLACEMENT_CHAR)
    if not count:
        return {}
    return {"encoding_replacements": t("text.encoding_replacements_note", count=count)}


def decode_text_with_note(raw: bytes) -> tuple[str, str, dict[str, str]]:
    """`decode_text()` + notes de transparence prêtes pour `extra_metadata`.

    Returns:
        Tuple (encodage détecté, texte final, métadonnées à fusionner dans
        `ExtractedFile.extra_metadata` — vide si rien n'a été réparé et si
        aucun caractère n'est resté illisible).
    """
    encoding, text, repaired = decode_text(raw)
    return encoding, text, {**mojibake_metadata(repaired), **replacement_metadata(text)}
