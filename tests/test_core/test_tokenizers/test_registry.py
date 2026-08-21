"""Tests du registre des moteurs de comptage.

Garantie centrale : `resolve_engine` ne lève jamais d'exception, quel que
soit l'identifiant fourni — un id inconnu ou indisponible retombe sur
`ApproxEngine`, toujours disponible.
"""

from __future__ import annotations

from docfuse.core.tokenizers.registry import list_engines, resolve_engine


class TestListEngines:
    def test_approx_is_always_listed_first(self) -> None:
        engines = list_engines()
        assert engines[0].id == "approx"

    def test_all_listed_engines_are_available(self) -> None:
        from docfuse.core.tokenizers.approx import ApproxEngine
        from docfuse.core.tokenizers.mistral import MistralEngine

        by_id = {ApproxEngine.info.id: ApproxEngine(), MistralEngine.info.id: MistralEngine()}
        for info in list_engines():
            assert by_id[info.id].is_available()


class TestResolveEngine:
    def test_resolve_approx(self) -> None:
        assert resolve_engine("approx").info.id == "approx"

    def test_resolve_mistral_or_graceful_fallback(self) -> None:
        # Doit résoudre vers "mistral" si disponible dans l'environnement de
        # test, sinon retomber silencieusement sur "approx" — jamais planter.
        assert resolve_engine("mistral").info.id in ("mistral", "approx")

    def test_unknown_id_falls_back_to_approx(self) -> None:
        assert resolve_engine("does-not-exist").info.id == "approx"

    def test_empty_id_falls_back_to_approx(self) -> None:
        assert resolve_engine("").info.id == "approx"

    def test_never_raises(self) -> None:
        for candidate in ("approx", "mistral", "", "APPROX", "Mistral", "unknown-engine"):
            resolve_engine(candidate)  # ne doit jamais lever
