"""Extracteur RTF : .rtf.

Utilise la bibliothèque striprtf (MIT) pour extraire le texte.

D-075 : striprtf traite `\\result` (texte de repli lisible d'un objet OLE
incrusté `\\object` — ex. un tableau Excel collé en objet dans un Word puis
exporté RTF, scénario très courant) comme une "destination ignorable", au
même titre que `\\objdata` (les données binaires de l'objet). Le texte de
repli, souvent le rendu tabulaire complet destiné aux lecteurs sans support
OLE, disparaît donc silencieusement avec les données binaires. Corrigé en
extrayant chaque groupe `{\\result ...}` du RTF brut (avant l'appel
principal à striprtf) et en le passant séparément à `rtf_to_text()` — son
contenu est lui-même un fragment RTF valide.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)

_RESULT_GROUP_START = re.compile(r"\{\\result\b")


@register(".rtf")
class RtfExtractor(Extractor):
    """Extracteur RTF via striprtf."""

    file_type = "rtf"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".rtf"

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            from striprtf.striprtf import rtf_to_text

            raw = path.read_bytes()
            rtf_text = raw.decode("latin-1", errors="replace")
            # D-096 : striprtf décode les séquences `\'xx` avec `errors="strict"`
            # par défaut — un seul octet indéfini en cp1252 (0x81/8D/8F/90/9D,
            # produits par certains générateurs) faisait échouer tout le
            # fichier en `UnicodeDecodeError`. `replace` dégrade localement
            # (un caractère U+FFFD) au lieu de perdre le document entier.
            text = str(rtf_to_text(rtf_text, errors="replace"))  # type: ignore[no-untyped-call]

            ole_fallback_texts = _extract_ole_fallback_texts(rtf_text)
            if ole_fallback_texts:
                text += "\n\n[objet(s) OLE incrusté(s) — texte de repli récupéré]\n" + "\n\n".join(
                    ole_fallback_texts
                )

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension="rtf",
                file_type=path.suffix.lower().lstrip("."),
                size_bytes=len(raw),
                text=text,
                status=FileStatus.READY,
                encoding="latin-1",
            )
        except Exception as exc:
            logger.exception("Erreur extraction RTF %s", path)
            return error_result(path, relative_path, cls.file_type, exc)


def _extract_ole_fallback_texts(rtf_text: str) -> list[str]:
    """Texte de repli de chaque objet OLE incrusté (groupes `{\\result ...}`,
    D-075). Retourne le texte déjà "striprtf-é" de chaque groupe trouvé,
    dans l'ordre d'apparition ; ignore un groupe dont l'accolade fermante
    n'est jamais trouvée (RTF tronqué/malformé — pas grave à ce stade,
    l'appel principal à `rtf_to_text` gérera déjà l'erreur globale)."""
    from striprtf.striprtf import rtf_to_text

    texts: list[str] = []
    for match in _RESULT_GROUP_START.finditer(rtf_text):
        inner = _matching_brace_content(rtf_text, match.start(), match.end())
        if inner is None:
            continue
        try:
            recovered = str(rtf_to_text(inner, errors="replace"))  # type: ignore[no-untyped-call]
        except Exception:
            continue
        recovered = recovered.strip()
        if recovered:
            texts.append(recovered)
    return texts


def _matching_brace_content(text: str, open_brace_index: int, content_start: int) -> str | None:
    """Contenu entre la fin de `{\\result` (`content_start`) et l'accolade
    fermante correspondant à l'accolade ouvrante en `open_brace_index`, en
    respectant l'imbrication des accolades (et les accolades échappées
    `\\{`/`\\}`, qui sont des caractères littéraux, pas structurels)."""
    depth = 0
    i = open_brace_index
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[content_start:i]
        i += 1
    return None
