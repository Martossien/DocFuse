"""Interface commune des moteurs OCR.

Même principe que `core/tokenizers/base.py` : un moteur OCR est optionnel,
découvert par `core/ocr/registry.py`, et son indisponibilité ne doit jamais
faire planter l'extraction — voir `resolve_ocr_engine()`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class OcrEngineInfo:
    """Métadonnées d'affichage d'un moteur OCR.

    Attributes:
        id: Identifiant stable (rapport, extra_metadata).
        label_key: Clé i18n du libellé affiché.
    """

    id: str
    label_key: str


class OcrEngine(ABC):
    """Un moteur de reconnaissance de texte sur image (OCR)."""

    info: OcrEngineInfo

    @abstractmethod
    def is_available(self) -> bool:
        """Indique si le moteur peut être utilisé dans cet environnement."""

    @abstractmethod
    def ocr_image(self, png_bytes: bytes, lang: str) -> str:
        """Reconnaît le texte d'une image PNG.

        Args:
            png_bytes: Image PNG encodée (une page rastérisée).
            lang: Code(s) langue Tesseract (ex: "fra+eng").

        Returns:
            Texte reconnu, chaîne vide si rien de lisible.
        """
