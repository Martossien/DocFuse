"""Tests de l'extracteur MHTML/MHT.

CdC §7.3 — .mhtml/.mht : Corps HTML→texte si simple.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.extractors.mhtml import MhtmlExtractor
from docfuse.models.file_status import FileStatus


class TestMhtmlExtractor:
    def test_extract_basic_mhtml(self, tmp_path: Path) -> None:
        f = tmp_path / "test.mhtml"
        # Créer un MHTML minimal valide
        mhtml = """From: <Saved by Blink>
Subject: Test Page
MIME-Version: 1.0
Content-Type: multipart/related; boundary="----=_NextPart_000_0000_00000000"

------=_NextPart_000_0000_00000000
Content-Type: text/html; charset=utf-8

<html><body><h1>Titre MHTML</h1><p>Paragraphe de test avec assez de caracteres pour eviter l alerte.</p></body></html>

------=_NextPart_000_0000_00000000
Content-Type: image/png
Content-Transfer-Encoding: base64

iVBORw0KGgoAAAANSUhEUg==

------=_NextPart_000_0000_00000000--
"""
        f.write_text(mhtml, encoding="utf-8")

        result = MhtmlExtractor.extract(f, "test.mhtml")
        assert result.status is FileStatus.READY
        assert "Titre MHTML" in result.text or "Titre" in result.text
        assert result.image_count >= 1

    def test_accepts(self) -> None:
        assert MhtmlExtractor.accepts(Path("test.mhtml")) is True
        assert MhtmlExtractor.accepts(Path("test.mht")) is True
        assert MhtmlExtractor.accepts(Path("test.html")) is False

    def test_safe_extract_no_crash(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.mhtml"
        result = MhtmlExtractor.safe_extract(f, "nonexistent.mhtml")
        assert result.status is FileStatus.ERROR

    def test_empty_mhtml(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.mht"
        f.write_text(
            "MIME-Version: 1.0\nContent-Type: text/plain\n\nTexte simple.", encoding="utf-8"
        )

        result = MhtmlExtractor.extract(f, "empty.mht")
        # MHTML sans multipart — peut retourner READY ou LOW_TEXT
        assert result.status in (FileStatus.READY, FileStatus.LOW_TEXT)
