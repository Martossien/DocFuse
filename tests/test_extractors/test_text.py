"""Tests de l'extracteur texte (.txt, .text, .log, fichiers de développement).

CdC §7.2 — Encodage : BOM, UTF-8, cp1252, latin-1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docfuse.constants import CODE_EXTENSIONS
from docfuse.core.registry import get_extractor_for
from docfuse.extractors.text import TextExtractor
from docfuse.models.file_status import FileStatus


class TestTextExtractor:
    """Tests de l'extracteur texte."""

    def test_utf8_text(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("Bonjour le monde.\nLigne 2.\n", encoding="utf-8")

        result = TextExtractor.extract(f, "test.txt")
        assert result.status is FileStatus.READY
        assert "Bonjour le monde" in result.text
        assert result.encoding == "utf-8"

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")

        result = TextExtractor.extract(f, "empty.txt")
        assert result.status is FileStatus.READY
        assert result.text == ""
        assert result.encoding == "utf-8"

    def test_cp1252_text(self, tmp_path: Path) -> None:
        f = tmp_path / "cp1252.txt"
        # Écrire un texte plus long en cp1252 pour que la détection soit fiable
        text = "Café réserver hôtel réunion"
        f.write_bytes(text.encode("cp1252"))

        result = TextExtractor.extract(f, "cp1252.txt")
        assert result.status is FileStatus.READY
        assert "Caf" in result.text

    def test_bom_utf8(self, tmp_path: Path) -> None:
        f = tmp_path / "bom.txt"
        f.write_bytes(b"\xef\xbb\xbfTexte avec BOM")

        result = TextExtractor.extract(f, "bom.txt")
        assert result.status is FileStatus.READY
        assert "Texte avec BOM" in result.text
        assert "utf-8" in (result.encoding or "")

    def test_accepts(self) -> None:
        assert TextExtractor.accepts(Path("test.txt")) is True
        assert TextExtractor.accepts(Path("test.log")) is True
        assert TextExtractor.accepts(Path("test.text")) is True
        assert TextExtractor.accepts(Path("test.pdf")) is False

    def test_safe_extract_no_crash(self, tmp_path: Path) -> None:
        """safe_extract ne doit JAMAIS crasher, même si le fichier n'existe pas."""
        f = tmp_path / "nonexistent.txt"
        result = TextExtractor.safe_extract(f, "nonexistent.txt")
        assert result.status is FileStatus.ERROR


class TestCodeExtensions:
    """Fichiers de développement (.py, .vba, .rs, ...) traités comme texte brut."""

    @pytest.mark.parametrize("ext", sorted(CODE_EXTENSIONS))
    def test_dispatches_to_text_extractor(self, ext: str) -> None:
        assert get_extractor_for(Path(f"fichier{ext}")) is TextExtractor

    def test_python_file_extracted_as_ready(self, tmp_path: Path) -> None:
        f = tmp_path / "script.py"
        f.write_text("def main() -> None:\n    print('hello')\n", encoding="utf-8")

        result = TextExtractor.extract(f, "script.py")
        assert result.status is FileStatus.READY
        assert "def main" in result.text
        assert result.file_type == "py"

    def test_vba_file_extracted_as_ready(self, tmp_path: Path) -> None:
        f = tmp_path / "Module1.vba"
        f.write_text('Sub Test()\n    MsgBox "Hello"\nEnd Sub\n', encoding="utf-8")

        result = TextExtractor.extract(f, "Module1.vba")
        assert result.status is FileStatus.READY
        assert "MsgBox" in result.text

    def test_dotfile_without_extension_is_not_matched(self) -> None:
        """Limite connue : dispatch par suffixe, pas par nom de fichier complet."""
        assert get_extractor_for(Path(".gitignore")) is None
        assert get_extractor_for(Path("Dockerfile")) is None
