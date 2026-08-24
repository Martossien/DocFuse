"""Tests de l'extracteur Markdown (.md, .markdown).

CdC §7.3 — Tel quel.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.extractors.markdown import MarkdownExtractor
from docfuse.models.file_status import FileStatus


class TestMarkdownExtractor:
    def test_basic_markdown(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("# Titre\n\nParagraphe.\n\n- Item 1\n- Item 2\n", encoding="utf-8")

        result = MarkdownExtractor.extract(f, "test.md")
        assert result.status is FileStatus.READY
        assert "# Titre" in result.text
        assert "Paragraphe" in result.text
        assert "- Item 1" in result.text

    def test_markdown_with_code_block(self, tmp_path: Path) -> None:
        f = tmp_path / "code.md"
        content = "# Code\n\n```python\nprint('hello')\n```\n"
        f.write_text(content, encoding="utf-8")

        result = MarkdownExtractor.extract(f, "code.md")
        assert result.status is FileStatus.READY
        assert "```python" in result.text
        assert "print('hello')" in result.text

    def test_accepts(self) -> None:
        assert MarkdownExtractor.accepts(Path("test.md")) is True
        assert MarkdownExtractor.accepts(Path("test.markdown")) is True
        assert MarkdownExtractor.accepts(Path("test.txt")) is False

    def test_strips_base64_embedded_image(self, tmp_path: Path) -> None:
        payload = "iVBORw0KGgoAAAANSUhEUgAA" + "A" * 200
        f = tmp_path / "screenshot.md"
        f.write_text(
            f"# Titre\n\n![Capture](data:image/png;base64,{payload})\n\nTexte après.\n",
            encoding="utf-8",
        )

        result = MarkdownExtractor.extract(f, "screenshot.md")
        assert result.status is FileStatus.READY
        assert payload not in result.text
        assert "![Capture]" in result.text
        assert "Texte après." in result.text
        assert result.image_count == 1
        assert "markdown_base64_stripped" in result.extra_metadata

    def test_short_base64_like_string_not_stripped(self, tmp_path: Path) -> None:
        f = tmp_path / "short.md"
        f.write_text("data:image/png;base64,short\n", encoding="utf-8")

        result = MarkdownExtractor.extract(f, "short.md")
        assert "data:image/png;base64,short" in result.text
        assert result.image_count == 0

    def test_no_base64_no_note(self, tmp_path: Path) -> None:
        f = tmp_path / "plain.md"
        f.write_text("# Titre\n\nJuste du texte.\n", encoding="utf-8")

        result = MarkdownExtractor.extract(f, "plain.md")
        assert result.extra_metadata == {}
