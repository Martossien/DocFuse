"""Tests du moteur approximatif (comportement historique inchangé)."""

from __future__ import annotations

from docfuse.core.tokenizers.approx import ApproxEngine


class TestApproxEngine:
    def test_always_available(self) -> None:
        assert ApproxEngine().is_available() is True

    def test_info_id(self) -> None:
        assert ApproxEngine.info.id == "approx"

    def test_count_tokens_matches_bytes_over_four(self) -> None:
        engine = ApproxEngine()
        assert engine.count_tokens("") == 0
        assert engine.count_tokens("abcd") == 1
        assert engine.count_tokens("A" * 4000) == 1000
