"""Tests des extracteurs CSV/TSV, JSON, XML, HTML.

CdC §7.3 — Texte tabulaire, pretty-print.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.extractors.csv_tsv import CsvTsvExtractor
from docfuse.extractors.html import HtmlExtractor
from docfuse.extractors.xml_json import JsonExtractor, XmlExtractor
from docfuse.models.file_status import FileStatus


class TestCsvTsvExtractor:
    def test_csv(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("a,b,c\n1,2,3\n4,5,6\n", encoding="utf-8")

        result = CsvTsvExtractor.extract(f, "data.csv")
        assert result.status is FileStatus.READY
        assert "a | b | c" in result.text
        assert "1 | 2 | 3" in result.text

    def test_tsv(self, tmp_path: Path) -> None:
        f = tmp_path / "data.tsv"
        f.write_text("a\tb\tc\n1\t2\t3\n", encoding="utf-8")

        result = CsvTsvExtractor.extract(f, "data.tsv")
        assert result.status is FileStatus.READY
        assert "a | b | c" in result.text

    def test_accepts(self) -> None:
        assert CsvTsvExtractor.accepts(Path("test.csv")) is True
        assert CsvTsvExtractor.accepts(Path("test.tsv")) is True
        assert CsvTsvExtractor.accepts(Path("test.txt")) is False


class TestJsonExtractor:
    def test_json_pretty_print(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text('{"name":"test","value":42}', encoding="utf-8")

        result = JsonExtractor.extract(f, "data.json")
        assert result.status is FileStatus.READY
        assert '"name": "test"' in result.text
        assert '"value": 42' in result.text

    def test_json_array(self, tmp_path: Path) -> None:
        f = tmp_path / "arr.json"
        f.write_text("[1,2,3]", encoding="utf-8")

        result = JsonExtractor.extract(f, "arr.json")
        assert result.status is FileStatus.READY
        assert "1" in result.text

    def test_accepts(self) -> None:
        assert JsonExtractor.accepts(Path("test.json")) is True
        assert JsonExtractor.accepts(Path("test.xml")) is False


class TestXmlExtractor:
    def test_xml_pretty_print(self, tmp_path: Path) -> None:
        f = tmp_path / "data.xml"
        f.write_text("<root><item>text</item></root>", encoding="utf-8")

        result = XmlExtractor.extract(f, "data.xml")
        assert result.status is FileStatus.READY
        assert "<root>" in result.text
        assert "<item>text</item>" in result.text

    def test_accepts(self) -> None:
        assert XmlExtractor.accepts(Path("test.xml")) is True


class TestHtmlExtractor:
    def test_html_text_extraction(self, tmp_path: Path) -> None:
        f = tmp_path / "page.html"
        f.write_text(
            "<html><head><title>Test</title></head>"
            "<body><h1>Titre</h1><p>Paragraphe</p></body></html>",
            encoding="utf-8",
        )

        result = HtmlExtractor.extract(f, "page.html")
        assert result.status is FileStatus.READY
        assert "Titre" in result.text
        assert "Paragraphe" in result.text

    def test_html_strips_script(self, tmp_path: Path) -> None:
        f = tmp_path / "script.html"
        f.write_text(
            "<html><body><p>Texte</p><script>alert('xss')</script></body></html>",
            encoding="utf-8",
        )

        result = HtmlExtractor.extract(f, "script.html")
        assert result.status is FileStatus.READY
        assert "Texte" in result.text
        assert "alert" not in result.text

    def test_html_counts_images(self, tmp_path: Path) -> None:
        f = tmp_path / "images.html"
        f.write_text(
            "<html><body><p>Texte</p>"
            '<img src="a.jpg" alt="Image A">'
            '<img src="b.jpg" alt="Image B">'
            "</body></html>",
            encoding="utf-8",
        )

        result = HtmlExtractor.extract(f, "images.html")
        assert result.status is FileStatus.READY
        assert result.image_count == 2
        assert "Image A" in result.text
        assert "Image B" in result.text

    def test_accepts(self) -> None:
        assert HtmlExtractor.accepts(Path("test.html")) is True
        assert HtmlExtractor.accepts(Path("test.htm")) is True

    def test_meta_charset_legacy_encoding_is_respected(self, tmp_path: Path) -> None:
        """D-073 : <meta charset=...> doit primer sur la détection générique
        d'encodage. cp1252 décode presque tous les octets sans erreur, donc
        sans lire cette déclaration, un charset legacy mono-octet non latin
        (cyrillique ici) devient un mojibake total et silencieux."""
        html_str = (
            '<html><head><meta charset="windows-1251"></head>'
            "<body><p>Привет, тестовый русский текст.</p></body></html>"
        )
        f = tmp_path / "cyrillic.html"
        f.write_bytes(html_str.encode("windows-1251"))

        result = HtmlExtractor.extract(f, "cyrillic.html")
        assert result.status is FileStatus.READY
        assert "русский текст" in result.text
        assert HtmlExtractor.accepts(Path("test.txt")) is False
