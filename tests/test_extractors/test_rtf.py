"""Tests de l'extracteur RTF.

Utilise striprtf (MIT).
"""

from __future__ import annotations

from pathlib import Path

from docfuse.extractors.rtf import RtfExtractor
from docfuse.models.file_status import FileStatus


class TestRtfExtractor:
    def test_extract_basic_rtf(self, tmp_path: Path) -> None:
        f = tmp_path / "test.rtf"
        rtf = (
            r"{\rtf1\ansi\deff0 {\fonttbl {\f0 Arial;}}"
            r" \f0\fs24 Ceci est un texte RTF de test avec assez de caracteres.}"
        )
        f.write_bytes(rtf.encode("latin-1"))

        result = RtfExtractor.extract(f, "test.rtf")
        assert result.status is FileStatus.READY
        assert "Ceci est un texte RTF" in result.text or "Ceci" in result.text

    def test_accepts(self) -> None:
        assert RtfExtractor.accepts(Path("test.rtf")) is True
        assert RtfExtractor.accepts(Path("test.txt")) is False

    def test_safe_extract_no_crash(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.rtf"
        result = RtfExtractor.safe_extract(f, "nonexistent.rtf")
        assert result.status is FileStatus.ERROR

    def test_fixture_file(self) -> None:
        fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample.rtf"
        if fixture.exists():
            result = RtfExtractor.extract(fixture, "sample.rtf")
            assert result.status is FileStatus.READY
            assert "Ceci" in result.text or "texte" in result.text

    def test_ole_object_fallback_text_is_recovered(self, tmp_path: Path) -> None:
        """D-075 : le texte de repli (\\result) d'un objet OLE incrusté
        (ex. tableau Excel collé en objet) ne doit pas disparaître avec les
        données binaires (\\objdata) — striprtf traite les deux comme des
        "destinations ignorables" indistinctement."""
        f = tmp_path / "ole.rtf"
        rtf = (
            r"{\rtf1\ansi "
            r"Texte avant.\par "
            r"{\object\objemb "
            r"{\*\objdata 0105000002000000}"
            r"{\result{\rtf1\ansi CONTENU_DE_REPLI_TABLEAU_EXCEL\par}}"
            r"}"
            r"Texte apres.\par"
            r"}"
        )
        f.write_bytes(rtf.encode("latin-1"))

        result = RtfExtractor.extract(f, "ole.rtf")
        assert result.status is FileStatus.READY
        assert "Texte avant" in result.text
        assert "Texte apres" in result.text
        assert "CONTENU_DE_REPLI_TABLEAU_EXCEL" in result.text
