"""Registre des moteurs OCR, même principe que `core/tokenizers/registry.py`.

Un seul moteur pour l'instant (Tesseract) ; la liste est prête à en accueillir
d'autres sans changer l'appelant.
"""

from __future__ import annotations

from docfuse.core.ocr.base import OcrEngine, OcrEngineInfo
from docfuse.core.ocr.tesseract import TesseractEngine

_ENGINES: list[OcrEngine] = [TesseractEngine()]


def resolve_ocr_engine() -> OcrEngine | None:
    """Renvoie le premier moteur OCR disponible dans cet environnement.

    Returns:
        Un `OcrEngine` utilisable, ou `None` si aucun n'est disponible —
        jamais d'exception. L'appelant doit alors se comporter comme si
        l'OCR n'existait pas.
    """
    for engine in _ENGINES:
        if engine.is_available():
            return engine
    return None


def list_ocr_engines() -> list[OcrEngineInfo]:
    """Liste les moteurs OCR disponibles dans cet environnement."""
    return [engine.info for engine in _ENGINES if engine.is_available()]
