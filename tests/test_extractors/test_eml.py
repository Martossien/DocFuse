"""Tests de l'extracteur EML.

CdC §7.3 — En-têtes utiles + corps texte/html→texte.
"""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

from docfuse.extractors.eml import EmlExtractor
from docfuse.models.file_status import FileStatus


class TestEmlExtractor:
    def test_extract_basic_email(self, tmp_path: Path) -> None:
        f = tmp_path / "test.eml"
        msg = EmailMessage()
        msg["Subject"] = "Test Subject"
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg.set_content(
            "Ceci est le corps de l email avec suffisamment de texte "
            "pour depasser le seuil de quatre-vingt caracteres."
        )
        f.write_bytes(bytes(msg))

        result = EmlExtractor.extract(f, "test.eml")
        assert result.status is FileStatus.READY
        assert "Test Subject" in result.text
        assert "corps de l email" in result.text

    def test_accepts(self) -> None:
        assert EmlExtractor.accepts(Path("test.eml")) is True
        assert EmlExtractor.accepts(Path("test.txt")) is False

    def test_safe_extract_no_crash(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.eml"
        result = EmlExtractor.safe_extract(f, "nonexistent.eml")
        assert result.status is FileStatus.ERROR

    def test_fixture_file(self) -> None:
        fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample.eml"
        if fixture.exists():
            result = EmlExtractor.extract(fixture, "sample.eml")
            assert result.status is FileStatus.READY
            assert "Test" in result.text
