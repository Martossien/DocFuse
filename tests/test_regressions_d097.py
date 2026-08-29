"""Non-régression de l'audit D-097 (lot 2 : encodage / réparation mojibake).

Chaque test reproduit le cas constaté pendant l'audit puis vérifie le
correctif. Voir docs/journal-decisions.md — D-097.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.extractors.text import decode_text, detect_encoding, repair_mojibake
from docfuse.models.file_status import FileStatus


class TestFtfyOnlyRepairsCorruption:
    def test_html_entities_are_left_alone(self) -> None:
        """`unescape_html="auto"` décodait `&amp;` → `&` ligne par ligne,
        AVANT `json.loads` : un JSON sain était réécrit."""
        assert repair_mojibake('{"t": "Tom &amp; Jerry"}') == '{"t": "Tom &amp; Jerry"}'
        assert repair_mojibake("&lt;div&gt; &copy; &nbsp;") == "&lt;div&gt; &copy; &nbsp;"

    def test_ansi_escapes_and_nfd_are_preserved(self) -> None:
        log_line = "\x1b[31mERROR\x1b[0m: échec"
        assert repair_mojibake(log_line) == log_line
        nfd = "é"  # « é » décomposé
        assert repair_mojibake(nfd) == nfd

    def test_real_mojibake_is_still_repaired(self) -> None:
        corrupted = "café".encode().decode("latin-1")
        assert repair_mojibake(corrupted) == "café"
        assert repair_mojibake("D\x92avance") == "D’avance"

    def test_ascii_fast_path_is_identity(self) -> None:
        text = "\n".join(f"def f{i}(x): return x + {i}  # &amp; ok" for i in range(2000))
        assert repair_mojibake(text) is text


class TestNearlyUtf8:
    def test_truncated_trailing_sequence_stays_utf8(self) -> None:
        """Un « é » coupé en fin de fichier faisait basculer TOUT le texte
        en cp1252 (`cafÃ©…`), ensuite « réparé » par ftfy et signalé comme
        mojibake — doublement trompeur."""
        data = ("café réservé à l'hôtel " * 50).encode() + "é".encode()[:1]
        encoding, _ = detect_encoding(data)
        assert encoding == "utf-8"

        enc, text, repaired = decode_text(data)
        assert enc == "utf-8"
        assert text.startswith("café réservé à l'hôtel")
        assert repaired is False

    def test_genuine_cp1252_is_still_cp1252(self) -> None:
        data = "Café réservé, hôtel, réunion — « guillemets »".encode("cp1252")
        encoding, _ = detect_encoding(data)
        assert encoding == "cp1252"


class TestHtmlUndeclaredCharset:
    def test_cp1252_page_without_meta_charset(self, tmp_path: Path) -> None:
        """Sans `<meta charset>`, Dammit devinait `johab` et mangeait la
        balise fermante."""
        from docfuse.extractors.html import HtmlExtractor

        f = tmp_path / "page.html"
        f.write_bytes(
            "<html><body><p>Résumé de la réunion à Orléans</p></body></html>".encode("cp1252")
        )

        result = HtmlExtractor.extract(f, "page.html")
        assert result.status is FileStatus.READY
        assert "Résumé de la réunion à Orléans" in result.text

    def test_declared_charset_still_wins(self, tmp_path: Path) -> None:
        from docfuse.extractors.html import HtmlExtractor

        f = tmp_path / "ru.html"
        f.write_bytes(
            '<html><head><meta charset="windows-1251"></head><body><p>Привет мир</p></body></html>'.encode(
                "cp1251"
            )
        )
        result = HtmlExtractor.extract(f, "ru.html")
        assert "Привет мир" in result.text
