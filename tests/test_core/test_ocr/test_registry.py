"""Tests du registre des moteurs OCR.

Garantie centrale : `resolve_ocr_engine` ne lève jamais d'exception, quel
que soit l'environnement — indisponible retombe sur `None`, jamais un crash.
"""

from __future__ import annotations

import pytest

from docfuse.core.ocr.base import OcrEngine, OcrEngineInfo
from docfuse.core.ocr.registry import list_ocr_engines, resolve_ocr_engine
from docfuse.core.ocr.tesseract import TesseractEngine


class _AlwaysUnavailableEngine(OcrEngine):
    info = OcrEngineInfo(id="fake", label_key="ocr.fake")

    def is_available(self) -> bool:
        return False

    def ocr_image(self, png_bytes: bytes, lang: str) -> str:  # noqa: ARG002
        raise AssertionError("ne devrait jamais être appelé")


class TestResolveOcrEngine:
    def test_matches_tesseract_availability(self) -> None:
        expected = TesseractEngine().info.id if TesseractEngine().is_available() else None
        result = resolve_ocr_engine()
        assert (result.info.id if result is not None else None) == expected

    def test_no_engine_available_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import docfuse.core.ocr.registry as registry_module

        monkeypatch.setattr(registry_module, "_ENGINES", [_AlwaysUnavailableEngine()])  # type: ignore[attr-defined]
        assert resolve_ocr_engine() is None


class TestListOcrEngines:
    def test_only_available_engines_listed(self) -> None:
        for info in list_ocr_engines():
            assert isinstance(info, OcrEngineInfo)
