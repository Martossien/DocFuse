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
