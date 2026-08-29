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

    def test_forwarded_message_rfc822_is_extracted(self, tmp_path: Path) -> None:
        """D-070 : un email transféré en pièce jointe (message/rfc822) ne
        doit pas disparaître. Avant le correctif, la logique "premier
        text/plain gagne" faisait que seul le corps du message englobant
        survivait — le sujet et le corps du message transféré, souvent le
        contenu le plus important du fichier, étaient silencieusement
        perdus."""
        nested = EmailMessage()
        nested["Subject"] = "Donnees financieres Q3 SECRET"
        nested["From"] = "financier@example.com"
        nested["To"] = "direction@example.com"
        nested.set_content("CONTENU ORIGINAL CRUCIAL: chiffre affaires confidentiel.")

        outer = EmailMessage()
        outer["Subject"] = "Fwd: Donnees financieres Q3"
        outer["From"] = "alice@example.com"
        outer["To"] = "bob@example.com"
        outer.set_content("Bonjour, voir email transfere ci-dessous.")
        outer.add_attachment(nested, subtype="rfc822")

        f = tmp_path / "forward.eml"
        f.write_bytes(bytes(outer))

        result = EmlExtractor.extract(f, "forward.eml")
        assert result.status is FileStatus.READY
        assert "Donnees financieres Q3 SECRET" in result.text
        assert "CONTENU ORIGINAL CRUCIAL" in result.text
        assert "Bonjour, voir email transfere" in result.text
