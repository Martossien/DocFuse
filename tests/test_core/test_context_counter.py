"""Tests du compteur de contexte.

CdC §10 — Formule : octets_utf8 / 4, marge +15 %.
"""

from __future__ import annotations

from docfuse.core.context_counter import (
    aggregate_tokens,
    check_limit,
    estimate_tokens,
)
from docfuse.core.tokenizers.base import TokenizerEngine, TokenizerEngineInfo


class _WordCountEngine(TokenizerEngine):
    """Moteur factice déterministe : 1 token par mot (test uniquement)."""

    info = TokenizerEngineInfo(id="fake", label_key="tokenizer.fake")

    def is_available(self) -> bool:
        return True

    def count_tokens(self, text: str) -> int:
        return len(text.split())


class TestEstimateTokens:
    """Tests de estimate_tokens()."""

    def test_empty_text(self) -> None:
        est = estimate_tokens("")
        assert est.bytes_utf8 == 0
        assert est.tokens_estimated == 0
        assert est.tokens_with_margin == 0

    def test_simple_ascii(self) -> None:
        # 4 octets → 1 token
        est = estimate_tokens("abcd")
        assert est.bytes_utf8 == 4
        assert est.tokens_estimated == 1
        # 1 * 1.15 = 1.15 → ceil = 2
        assert est.tokens_with_margin == 2

    def test_unicode_utf8(self) -> None:
        # "é" = 2 octets en UTF-8
        est = estimate_tokens("éé")
        assert est.bytes_utf8 == 4  # 2 * 2 octets
        assert est.tokens_estimated == 1

    def test_large_text(self) -> None:
        text = "A" * 4000  # 4000 octets → 1000 tokens
        est = estimate_tokens(text)
        assert est.tokens_estimated == 1000
        assert est.tokens_with_margin == 1150  # 1000 * 1.15

    def test_custom_margin(self) -> None:
        est = estimate_tokens("abcd", margin=0.0)
        assert est.tokens_with_margin == 1  # Pas de marge

    def test_default_margin(self) -> None:
        est = estimate_tokens("abcd")
        assert est.tokens_with_margin == 2  # ceil(1 * 1.15) = 2


class TestCheckLimit:
    """Tests de check_limit()."""

    def test_under_limit(self) -> None:
        assert check_limit(1000, 128000) is True

    def test_equal_limit(self) -> None:
        # CdC §10.2 : égalité (== L) passe
        assert check_limit(128000, 128000) is True

    def test_over_limit(self) -> None:
        assert check_limit(128001, 128000) is False


class TestAggregateTokens:
    """Tests de aggregate_tokens()."""

    def test_empty_list(self) -> None:
        total = aggregate_tokens([])
        assert total.tokens_estimated == 0
        assert total.tokens_with_margin == 0

    def test_multiple_estimates(self) -> None:
        e1 = estimate_tokens("abcd")  # 1 token, 2 avec marge
        e2 = estimate_tokens("efgh")  # 1 token, 2 avec marge
        total = aggregate_tokens([e1, e2])
        assert total.tokens_estimated == 2
        assert total.tokens_with_margin == 3  # ceil(2 * 1.15), marge appliquée au total


class TestEstimateTokensWithEngine:
    """Un moteur précis remplace tokens_estimated ; bytes_utf8 reste calculé."""

    def test_none_engine_keeps_historical_approx_behavior(self) -> None:
        est = estimate_tokens("abcd", margin=0.0, engine=None)
        assert est.tokens_estimated == 1  # ceil(4/4), inchangé

    def test_precise_engine_replaces_tokens_estimated(self) -> None:
        est = estimate_tokens("a b c d", margin=0.0, engine=_WordCountEngine())
        assert est.tokens_estimated == 4  # 4 mots, pas ceil(7 octets / 4)
        assert est.bytes_utf8 == 7  # toujours calculé (métadonnée)

    def test_precise_engine_margin_applied_after_count(self) -> None:
        est = estimate_tokens("a b c d", margin=0.5, engine=_WordCountEngine())
        assert est.tokens_estimated == 4
        assert est.tokens_with_margin == 6  # ceil(4 * 1.5)


class TestAggregateTokensWithEngine:
    """Avec un moteur précis, le total est la somme des tokens par fichier
    (pas un recalcul depuis le total d'octets, impossible pour un vrai BPE)."""

    def test_precise_engine_sums_per_file_tokens(self) -> None:
        engine = _WordCountEngine()
        e1 = estimate_tokens("a b", margin=0.0, engine=engine)  # 2 tokens
        e2 = estimate_tokens("c d e", margin=0.0, engine=engine)  # 3 tokens
        total = aggregate_tokens([e1, e2], margin=0.0, engine=engine)
        assert total.tokens_estimated == 5

    def test_approx_engine_still_recomputes_from_total_bytes(self) -> None:
        # Comportement historique inchangé : ceil(total_octets / 4), pas la
        # somme des ceil(octets_fichier / 4) — cf. formule CdC §10.
        e1 = estimate_tokens("ab", margin=0.0)  # 2 octets -> 1 token
        e2 = estimate_tokens("ab", margin=0.0)  # 2 octets -> 1 token
        total = aggregate_tokens([e1, e2], margin=0.0)
        assert total.tokens_estimated == 1  # ceil(4/4) = 1, pas 1+1
