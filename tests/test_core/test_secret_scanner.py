"""Tests de la détection heuristique de secrets potentiels."""

from __future__ import annotations

from docfuse.core.secret_scanner import scan_for_secrets


class TestScanForSecrets:
    def test_empty_text_no_findings(self) -> None:
        assert scan_for_secrets("") == []

    def test_plain_text_no_findings(self) -> None:
        text = "Ceci est un rapport tout a fait normal sans aucune information sensible."
        assert scan_for_secrets(text) == []

    def test_aws_key_detected(self) -> None:
        text = "Voici la config:\nAWS_ACCESS_KEY_ID=AKIAABCDEFGHIJKLMNOP\n"
        findings = scan_for_secrets(text)
        assert findings == [("secret.kind_aws_key", 2)]

    def test_private_key_detected(self) -> None:
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n"
        findings = scan_for_secrets(text)
        assert findings[0][0] == "secret.kind_private_key"
        assert findings[0][1] == 1

    def test_generic_api_key_assignment_detected(self) -> None:
        # Valeur factice volontairement générique (pas de préfixe connu type
        # "sk_live_") pour ne pas ressembler à un vrai format de fournisseur
        # et déclencher le secret-scanning de GitHub sur ce dépôt lui-même.
        text = 'api_key = "not_a_real_value_but_long_enough_1234567890"'
        findings = scan_for_secrets(text)
        assert findings[0][0] == "secret.kind_generic_api_key"

    def test_line_numbers_are_one_indexed(self) -> None:
        text = "ligne 1\nligne 2\nAKIAABCDEFGHIJKLMNOP\nligne 4"
        findings = scan_for_secrets(text)
        assert findings == [("secret.kind_aws_key", 3)]

    def test_multiple_findings_same_line(self) -> None:
        text = "AKIAABCDEFGHIJKLMNOP api_key=abcdefghijklmnopqrstuvwx"
        findings = scan_for_secrets(text)
        kinds = {kind for kind, _ in findings}
        assert "secret.kind_aws_key" in kinds
        assert "secret.kind_generic_api_key" in kinds
