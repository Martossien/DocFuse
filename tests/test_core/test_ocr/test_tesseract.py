"""Tests du moteur OCR Tesseract (binaire CLI, subprocess).

Ces tests s'exécutent que Tesseract soit installé ou non sur la machine de
test : `is_available()` reflète l'environnement réel, et les tests qui ont
besoin d'un vrai OCR sont sous `skipif(not is_available())` — même idiome
que les moteurs de comptage optionnels (`test_tokenizers/test_mistral.py`).
"""

from __future__ import annotations

import io

import pytest

from docfuse.core.ocr.tesseract import TesseractEngine, _resolve_binary

_ENGINE = TesseractEngine()


class TestTesseractEngine:
    def test_info_id(self) -> None:
        assert TesseractEngine.info.id == "tesseract"

    def test_is_available_reflects_environment(self) -> None:
        import shutil

        expected = shutil.which("tesseract") is not None
        assert _ENGINE.is_available() is expected

    def test_unavailable_when_binary_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("shutil.which", lambda _name: None)
        _resolve_binary.cache_clear()
        try:
            assert _ENGINE.is_available() is False
            assert _ENGINE.ocr_image(b"not a real png", "fra") == ""
        finally:
            _resolve_binary.cache_clear()

    @pytest.mark.skipif(not _ENGINE.is_available(), reason="Tesseract non installé")
    def test_ocr_image_recognizes_rendered_text(self) -> None:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (600, 150), "white")
        draw = ImageDraw.Draw(img)
        draw.text((10, 50), "Bonjour le monde", fill="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        text = _ENGINE.ocr_image(buf.getvalue(), "fra+eng")
        assert "onjour" in text or "monde" in text

    @pytest.mark.skipif(not _ENGINE.is_available(), reason="Tesseract non installé")
    def test_ocr_image_invalid_data_returns_empty_not_raises(self) -> None:
        assert _ENGINE.ocr_image(b"clearly not a png", "fra") == ""
