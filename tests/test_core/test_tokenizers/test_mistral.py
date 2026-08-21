"""Tests du moteur Mistral (Tekken via tiktoken, vocabulaire vendoré).

CdC ligne 637 (anticipant l'ajout d'un moteur type tiktoken) : "tests avec
réseau coupé". `test_no_network_call` en est l'implémentation directe pour
le moteur Mistral.
"""

from __future__ import annotations

import socket
from typing import Any

import pytest

from docfuse.core.tokenizers import mistral as mistral_module
from docfuse.core.tokenizers.mistral import MistralEngine


class TestMistralEngine:
    def test_is_available(self) -> None:
        assert MistralEngine().is_available() is True

    def test_info_id(self) -> None:
        assert MistralEngine.info.id == "mistral"

    def test_empty_text(self) -> None:
        assert MistralEngine().count_tokens("") == 0

    def test_count_tokens_is_positive_for_real_text(self) -> None:
        engine = MistralEngine()
        assert engine.count_tokens("Bonjour, comment allez-vous aujourd'hui ?") > 0

    def test_count_tokens_is_deterministic(self) -> None:
        engine = MistralEngine()
        text = "Un texte de test répété plusieurs fois pour vérifier la stabilité."
        assert engine.count_tokens(text) == engine.count_tokens(text)

    def test_count_tokens_grows_with_text_length(self) -> None:
        engine = MistralEngine()
        short = engine.count_tokens("Bonjour.")
        long = engine.count_tokens("Bonjour. " * 50)
        assert long > short


class TestMistralOffline:
    def test_no_network_call_during_load_and_encode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Le chargement du vocabulaire et l'encodage ne doivent jamais ouvrir de socket."""

        def _blocked_socket(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("Le moteur Mistral a tenté d'ouvrir une connexion réseau")

        mistral_module._load_encoding.cache_clear()
        monkeypatch.setattr(socket, "socket", _blocked_socket)
        try:
            engine = MistralEngine()
            assert engine.is_available() is True
            assert engine.count_tokens("Test entièrement hors ligne, sans réseau.") > 0
        finally:
            mistral_module._load_encoding.cache_clear()
