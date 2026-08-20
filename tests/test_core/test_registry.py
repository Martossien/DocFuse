"""Tests du registre d'extracteurs.

CdC §4 — Registration automatique par @register.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.core.registry import get_extractor_for, list_supported_extensions


class TestRegistry:
    """Tests du registre d'extracteurs."""

    def test_pdf_extractor_registered(self) -> None:
        from docfuse.extractors.pdf import PdfExtractor

        ext = get_extractor_for(Path("test.pdf"))
        assert ext is not None
        assert ext is PdfExtractor

    def test_docx_extractor_registered(self) -> None:
        from docfuse.extractors.docx import DocxExtractor

        ext = get_extractor_for(Path("test.docx"))
        assert ext is not None
        assert ext is DocxExtractor

    def test_txt_extractor_registered(self) -> None:
        from docfuse.extractors.text import TextExtractor

        ext = get_extractor_for(Path("test.txt"))
        assert ext is not None
        assert ext is TextExtractor

    def test_html_extractor_registered(self) -> None:
        from docfuse.extractors.html import HtmlExtractor

        ext = get_extractor_for(Path("test.html"))
        assert ext is not None
        assert ext is HtmlExtractor

    def test_unknown_extension_returns_none(self) -> None:
        ext = get_extractor_for(Path("test.unknown"))
        assert ext is None

    def test_all_extensions_registered(self) -> None:
        exts = list_supported_extensions()
        assert ".pdf" in exts
        assert ".docx" in exts
        assert ".pptx" in exts
        assert ".xlsx" in exts
        assert ".html" in exts
        assert ".txt" in exts
        assert ".md" in exts
        assert ".csv" in exts
        assert ".rtf" in exts
        assert ".eml" in exts

    def test_case_insensitive_extension(self) -> None:
        ext = get_extractor_for(Path("TEST.PDF"))
        assert ext is not None
