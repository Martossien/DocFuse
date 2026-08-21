"""Tests du moteur OpenAI (o200k_base via tiktoken, vocabulaire vendoré).

Même discipline que pour le moteur Mistral : disponibilité, comptes
plausibles, et absence d'appel réseau (CdC §10.1).
"""

from __future__ import annotations

import socket
from typing import Any

import pytest

from docfuse.core.tokenizers import openai as openai_module
from docfuse.core.tokenizers.openai import OpenAIEngine


class TestOpenAIEngine:
    def test_is_available(self) -> None:
        assert OpenAIEngine().is_available() is True

    def test_info_id(self) -> None:
        assert OpenAIEngine.info.id == "openai"

    def test_empty_text(self) -> None:
        assert OpenAIEngine().count_tokens("") == 0

    def test_count_tokens_is_positive_for_real_text(self) -> None:
        engine = OpenAIEngine()
        assert engine.count_tokens("Bonjour, comment allez-vous aujourd'hui ?") > 0

    def test_count_tokens_is_deterministic(self) -> None:
        engine = OpenAIEngine()
        text = "Un texte de test répété plusieurs fois pour vérifier la stabilité."
        assert engine.count_tokens(text) == engine.count_tokens(text)

    def test_count_tokens_grows_with_text_length(self) -> None:
        engine = OpenAIEngine()
        short = engine.count_tokens("Bonjour.")
        long = engine.count_tokens("Bonjour. " * 50)
        assert long > short

    def test_special_token_string_does_not_raise(self) -> None:
        # tiktoken lève par défaut sur les chaînes de tokens spéciaux non
        # autorisées ; aucun token spécial n'est enregistré ici (cf. docstring
        # du module), donc un document qui contient littéralement ce texte
        # (ex: article technique sur les tokenizers) ne doit jamais planter.
        engine = OpenAIEngine()
        assert engine.count_tokens("Un texte qui mentionne <|endoftext|> en exemple.") > 0


class TestOpenAIOffline:
    def test_no_network_call_during_load_and_encode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _blocked_socket(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("Le moteur OpenAI a tenté d'ouvrir une connexion réseau")

        openai_module._load_encoding.cache_clear()
        monkeypatch.setattr(socket, "socket", _blocked_socket)
        try:
            engine = OpenAIEngine()
            assert engine.is_available() is True
            assert engine.count_tokens("Test entièrement hors ligne, sans réseau.") > 0
        finally:
            openai_module._load_encoding.cache_clear()
