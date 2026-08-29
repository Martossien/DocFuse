"""Extracteur Markdown : .md, .markdown.

CdC §7.3 — Tel quel (pas de transformation, le Markdown est déjà du texte structuré).
"""

from __future__ import annotations

import re
from pathlib import Path

from docfuse.constants import MARKDOWN_BASE64_MIN_LEN
from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.extractors.text import detect_encoding
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

# Data URI d'image encodée en base64 (ex: `![alt](data:image/png;base64,iVBOR...)`).
# En contexte texte, un LLM ne peut pas "voir" une image depuis du base64 brut :
# ce n'est pas du contenu, juste du bruit qui coûte des tokens sans valeur
# informative. Longueur minimale pour éviter de matcher une chaîne courte
# accidentelle qui ressemblerait à un data URI.
_BASE64_IMAGE_RE = re.compile(
    r"data:image/[\w.+-]+;base64,[A-Za-z0-9+/=]{" + str(MARKDOWN_BASE64_MIN_LEN) + r",}"
)


def _strip_base64_images(text: str) -> tuple[str, int, int]:
    """Retire les images encodées en base64 (data URI) du texte Markdown.

    Le marqueur `![alt](...)`/`<img src="...">` autour du data URI est
    conservé (l'alt text peut porter une information utile) ; seul le
    payload base64 est remplacé par une note explicite, pas retiré en
    silence (CdC §8 — sans perte silencieuse).

    Returns:
        Tuple (texte mis à jour, nombre d'images retirées, caractères économisés).
    """
    count = 0
    chars_saved = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal count, chars_saved
        count += 1
        chars_saved += len(match.group(0))
        return t("markdown.base64_image_removed", chars=len(match.group(0)))

    new_text = _BASE64_IMAGE_RE.sub(_replace, text)
    return new_text, count, chars_saved


@register(".md", ".markdown")
class MarkdownExtractor(Extractor):
    """Extracteur pour les fichiers Markdown (tel quel)."""

    file_type = "markdown"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in (".md", ".markdown")

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            raw = path.read_bytes()
            encoding, data = detect_encoding(raw)
            text = data.decode(encoding, errors="replace")

            text, image_count, chars_saved = _strip_base64_images(text)
            extra_metadata: dict[str, str] = {}
            if image_count > 0:
                extra_metadata["markdown_base64_stripped"] = t(
                    "markdown.base64_note", count=image_count, chars=chars_saved
                )

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=path.suffix.lower().lstrip("."),
                file_type=path.suffix.lower().lstrip("."),
                size_bytes=len(raw),
                text=text,
                status=FileStatus.READY,
                encoding=encoding,
                image_count=image_count,
                extra_metadata=extra_metadata,
            )
        except Exception as exc:
            return error_result(path, relative_path, cls.file_type, exc)
