"""Extracteur texte brut : .txt, .text, .log.

CdC §7.2 — Encodage : BOM, puis UTF-8, puis cp1252, latin-1 en dernier.
Signalé au rapport.
"""

from __future__ import annotations

import logging
import unicodedata
from pathlib import Path

from docfuse.constants import (
    CODE_EXTENSIONS,
    ENCODING_MAX_CONTROL_RATIO,
    ENCODING_PLAUSIBILITY_SAMPLE_CHARS,
)
from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)

# .txt/.text/.log (CdC §7.2) + fichiers de développement (CODE_EXTENSIONS,
# §7.3) : même traitement, un texte brut est un texte brut.
_TEXT_LIKE_EXTENSIONS: frozenset[str] = frozenset({".txt", ".text", ".log"}) | CODE_EXTENSIONS


def _looks_plausible(text: str) -> bool:
    """D-093 : un décodage cp1252 réussit presque toujours (cet encodage
    mappe presque tous les octets), même sur un fichier qui n'est PAS
    réellement cp1252 (ex: UTF-8 avec une séquence multi-octets tronquée en
    fin de fichier, qui fait juste échouer le test UTF-8 strict). Sans ce
    garde-fou, un tel fichier tombait directement sur un cp1252 mal choisi
    au lieu de retomber sur charset-normalizer.

    Heuristique : ratio de caractères de contrôle Unicode (catégorie `Cc`,
    hors `\\t\\n\\r`) — un décodage dans le mauvais encodage produit souvent
    des caractères de contrôle imprévus au milieu du texte. Échantillonné
    sur `ENCODING_PLAUSIBILITY_SAMPLE_CHARS` pour un coût borné même sur un
    gros fichier.
    """
    sample = text[:ENCODING_PLAUSIBILITY_SAMPLE_CHARS]
    if not sample:
        return True
    control_count = sum(1 for c in sample if c not in "\t\n\r" and unicodedata.category(c) == "Cc")
    return (control_count / len(sample)) <= ENCODING_MAX_CONTROL_RATIO


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
    try:
        import ftfy

        config = ftfy.TextFixerConfig(
            uncurl_quotes=False,
            fix_latin_ligatures=False,
            fix_line_breaks=False,
            fix_character_width=False,
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


@register(*_TEXT_LIKE_EXTENSIONS)
class TextExtractor(Extractor):
    """Extracteur pour les fichiers texte brut (dont les fichiers de développement)."""

    file_type = "text"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in _TEXT_LIKE_EXTENSIONS

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            raw = path.read_bytes()
            encoding, text, mojibake_repaired = decode_text(raw)
            extra_metadata: dict[str, str] = {}
            if mojibake_repaired:
                extra_metadata["mojibake_repaired"] = t("text.mojibake_repaired_note")

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=path.suffix.lower().lstrip("."),
                file_type=path.suffix.lower().lstrip("."),
                size_bytes=len(raw),
                text=text,
                status=FileStatus.READY,
                encoding=encoding,
                extra_metadata=extra_metadata,
            )
        except Exception as exc:
            logger.exception("Erreur extraction texte %s", path)
            return error_result(path, relative_path, cls.file_type, exc)
