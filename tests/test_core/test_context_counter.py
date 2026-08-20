"""Tests du compteur de contexte.

CdC §10 — Formule : octets_utf8 / 4, marge +15 %.
"""

from __future__ import annotations

from docfuse.core.context_counter import (
    aggregate_tokens,
    check_limit,
    estimate_tokens,
)


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
