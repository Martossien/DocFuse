"""Registre des moteurs OCR, même principe que `core/tokenizers/registry.py`.

Un seul moteur pour l'instant (Tesseract) ; la liste est prête à en accueillir
d'autres sans changer l'appelant.
"""

from __future__ import annotations

import threading
from typing import Any

from docfuse.constants import OCR_MAX_CONCURRENCY
from docfuse.core.ocr.base import OcrEngine, OcrEngineInfo
from docfuse.core.ocr.tesseract import TesseractEngine

_ENGINES: list[OcrEngine] = [TesseractEngine()]

# D-098 : borne globale du nombre de processus OCR simultanés, partagée par
# l'OCR des pages PDF (`extractors/pdf.py`) et celui des images intégrées
# (`core/embedded_images.py`). Sans elle, MAX_WORKERS fichiers en parallèle
# lançant chacun leurs propres appels donnaient jusqu'à MAX_WORKERS² processus
# Tesseract (sur-souscription CPU + mémoire ×N).
OCR_SLOTS: Any = threading.BoundedSemaphore(OCR_MAX_CONCURRENCY)
"""Sémaphore de ce processus ; dans un travailleur du pool d'extraction, il est
remplacé par un sémaphore **inter-processus** (`set_ocr_gate`, D-111) pour que
la borne vaille pour tout le pool et non par processus."""


def set_ocr_gate(gate: Any) -> None:
    """Remplace le sémaphore OCR (objet à `__enter__`/`__exit__`)."""
    global OCR_SLOTS
    OCR_SLOTS = gate


def ocr_with_slot(engine: OcrEngine, image_bytes: bytes, lang: str) -> str:
    """`engine.ocr_image` sous le sémaphore global — jamais d'exception
    (un échec vaut texte vide, comme le moteur lui-même)."""
    with OCR_SLOTS:
        try:
            return engine.ocr_image(image_bytes, lang)
        except Exception:
            return ""


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
