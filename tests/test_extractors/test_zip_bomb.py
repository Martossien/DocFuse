"""Tests du garde-fou "bombe zip" (D-093, `extractors/base.py::is_zip_bomb`).

Les constantes réelles (300 Mo minimum) sont monkeypatchées à une valeur
minuscule pour tester la logique sans construire un fichier énorme.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from docfuse.extractors import base as base_module
from docfuse.extractors.base import is_zip_bomb


@pytest.fixture(autouse=True)
def _small_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seuils abaissés pour tester sans fichier de 300 Mo réel."""
    monkeypatch.setattr(base_module, "ZIP_BOMB_MIN_UNCOMPRESSED_BYTES", 1000)
    monkeypatch.setattr(base_module, "ZIP_BOMB_MAX_RATIO", 10.0)


class TestIsZipBomb:
    def test_highly_compressed_large_member_is_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "bomb.zip"
        with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("huge.xml", b"0" * 100_000)  # compresse à un ratio énorme

        assert is_zip_bomb(f) is True

    def test_normal_docx_like_file_not_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "normal.zip"
        with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("word/document.xml", "<w:document>Texte normal</w:document>")

        assert is_zip_bomb(f) is False

    def test_high_ratio_but_small_volume_not_flagged(self, tmp_path: Path) -> None:
        """Un petit fichier très répétitif (ratio élevé) n'est jamais
        dangereux — seul le volume décompressé réel compte aussi."""
        f = tmp_path / "small_repetitive.zip"
        with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("data.txt", b"0" * 500)  # < ZIP_BOMB_MIN_UNCOMPRESSED_BYTES (1000)

        assert is_zip_bomb(f) is False

    def test_non_zip_file_returns_false(self, tmp_path: Path) -> None:
        f = tmp_path / "not_a_zip.docx"
        f.write_bytes(b"this is not a zip file at all")

        assert is_zip_bomb(f) is False

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        assert is_zip_bomb(tmp_path / "nonexistent.docx") is False


class TestZipBombWiredIntoExtractors:
    """Vérifie que le garde-fou est bien appelé par les extracteurs ZIP."""

    def test_docx_extractor_rejects_zip_bomb(self, tmp_path: Path) -> None:
        from docfuse.extractors.docx import DocxExtractor
        from docfuse.models.file_status import FileStatus

        f = tmp_path / "bomb.docx"
        with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("huge.xml", b"0" * 100_000)

        result = DocxExtractor.extract(f, "bomb.docx")
        assert result.status is FileStatus.ERROR
        assert result.error_message is not None
        assert "suspect" in result.error_message.lower()

    def test_xlsx_extractor_rejects_zip_bomb(self, tmp_path: Path) -> None:
        from docfuse.extractors.xlsx import XlsxExtractor
        from docfuse.models.file_status import FileStatus

        f = tmp_path / "bomb.xlsx"
        with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("huge.xml", b"0" * 100_000)

        result = XlsxExtractor.extract(f, "bomb.xlsx")
        assert result.status is FileStatus.ERROR

    def test_odf_extractor_rejects_zip_bomb(self, tmp_path: Path) -> None:
        from docfuse.extractors.odf import OdfExtractor
        from docfuse.models.file_status import FileStatus

        f = tmp_path / "bomb.odt"
        with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("huge.xml", b"0" * 100_000)

        result = OdfExtractor.extract(f, "bomb.odt")
        assert result.status is FileStatus.ERROR

    def test_epub_extractor_rejects_zip_bomb(self, tmp_path: Path) -> None:
        from docfuse.extractors.epub import EpubExtractor
        from docfuse.models.file_status import FileStatus

        f = tmp_path / "bomb.epub"
        with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("huge.xml", b"0" * 100_000)

        result = EpubExtractor.extract(f, "bomb.epub")
        assert result.status is FileStatus.ERROR
