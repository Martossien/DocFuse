"""Tests de l'orchestrator (pipeline end-to-end).

CdC §13.3 — Pipeline : inventaire → extraction → compteur → décision.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.core.orchestrator import generate_corpus, run_analysis
from docfuse.core.progress import ProgressEmitter


class TestRunAnalysis:
    def test_basic_analysis(self, tmp_workspace: Path) -> None:
        result = run_analysis(tmp_workspace, context_limit=128000)
        assert len(result.files) > 0
        assert result.total.tokens_estimated > 0
        assert not result.is_blocked

    def test_blocking_single_file(self, tmp_path: Path) -> None:
        text = "A" * 10_000
        (tmp_path / "big.txt").write_text(text, encoding="utf-8")
        result = run_analysis(tmp_path, context_limit=100)
        assert result.is_blocked
        assert len(result.blocking_files) > 0

    def test_blocking_total(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text("A" * 500, encoding="utf-8")
        result = run_analysis(tmp_path, context_limit=200)
        assert result.is_blocked

    def test_ignored_files_listed(self, tmp_workspace: Path) -> None:
        result = run_analysis(tmp_workspace, context_limit=128000)
        ignored_names = {p.name for p, _ in result.ignored}
        assert "program.exe" in ignored_names

    def test_no_files(self, tmp_path: Path) -> None:
        result = run_analysis(tmp_path, context_limit=128000)
        assert len(result.files) == 0
        assert result.total.tokens_estimated == 0

    def test_inventory_events_precede_extraction_results(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("Premier texte.", encoding="utf-8")
        (tmp_path / "b.txt").write_text("Second texte.", encoding="utf-8")
        emitter = ProgressEmitter()

        run_analysis(tmp_path, emitter=emitter)
        events = emitter.drain()

        assert [event.file_path for event in events[:2]] == ["a.txt", "b.txt"]
        assert all(event.status == "pending" for event in events[:2])
        assert all(event.current == 0 for event in events[:2])

    def test_duplicate_content_deduplicated_and_flagged(self, tmp_path: Path) -> None:
        # Noms triés alphabétiquement (tri par défaut) pour fixer sans
        # ambiguïté lequel des deux est traité en premier et sert d'original.
        text = "Contenu strictement identique repete pour depasser le seuil minimum requis."
        (tmp_path / "1_original.txt").write_text(text, encoding="utf-8")
        (tmp_path / "2_copie.txt").write_text(text, encoding="utf-8")

        result = run_analysis(tmp_path, context_limit=128000)

        by_name = {f.relative_path: f for f in result.files}
        assert "duplicate_of" in by_name["2_copie.txt"].extra_metadata
        assert by_name["2_copie.txt"].extra_metadata["duplicate_of"] == "1_original.txt"
        assert text not in by_name["2_copie.txt"].text
        assert "duplicate_of" not in by_name["1_original.txt"].extra_metadata

    def test_secret_detected_flagged_without_blocking(self, tmp_path: Path) -> None:
        (tmp_path / "config.txt").write_text(
            "config:\nAWS_ACCESS_KEY_ID=AKIAABCDEFGHIJKLMNOP\n", encoding="utf-8"
        )

        result = run_analysis(tmp_path, context_limit=128000)

        assert not result.is_blocked
        by_name = {f.relative_path: f for f in result.files}
        assert "secrets_detected" in by_name["config.txt"].extra_metadata


class TestGenerateCorpus:
    def test_generate_markdown(self, tmp_workspace: Path) -> None:
        result = run_analysis(tmp_workspace, context_limit=128000)
        output = tmp_workspace / "corpus.md"
        success = generate_corpus(result, output, 128000, 0.15)
        assert success
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "SOURCE:" in content
        assert "corpus.md" not in content  # ne s'est pas réingéré

    def test_generate_blocked(self, tmp_path: Path) -> None:
        (tmp_path / "big.txt").write_text("A" * 10_000, encoding="utf-8")
        result = run_analysis(tmp_path, context_limit=100)
        output = tmp_path / "corpus.md"
        success = generate_corpus(result, output, 100, 0.15)
        assert not success
        assert not output.exists()

    def test_report_generated(self, tmp_workspace: Path) -> None:
        result = run_analysis(tmp_workspace, context_limit=128000)
        output = tmp_workspace / "corpus.md"
        generate_corpus(result, output, 128000, 0.15)
        report_md = tmp_workspace / "corpus_rapport.md"
        report_json = tmp_workspace / "corpus_rapport.json"
        assert report_md.exists()
        assert report_json.exists()


class TestTokenizerEngineIntegration:
    """Bout-en-bout avec un moteur de comptage précis (CdC §10 étendu)."""

    def test_default_engine_is_approx(self, tmp_workspace: Path) -> None:
        result = run_analysis(tmp_workspace, context_limit=128000)
        assert result.engine_id == "approx"

    def test_mistral_engine_resolves_and_produces_totals(self, tmp_workspace: Path) -> None:
        result = run_analysis(tmp_workspace, context_limit=128000, tokenizer_engine="mistral")
        assert result.engine_id == "mistral"
        assert result.total.tokens_estimated > 0
        assert not result.is_blocked

    def test_unknown_engine_falls_back_to_approx(self, tmp_workspace: Path) -> None:
        result = run_analysis(
            tmp_workspace, context_limit=128000, tokenizer_engine="does-not-exist"
        )
        assert result.engine_id == "approx"

    def test_mistral_report_mentions_engine(self, tmp_workspace: Path) -> None:
        result = run_analysis(tmp_workspace, context_limit=128000, tokenizer_engine="mistral")
        output = tmp_workspace / "corpus.md"
        generate_corpus(result, output, 128000, 0.15)
        report_json = tmp_workspace / "corpus_rapport.json"
        import json

        data = json.loads(report_json.read_text(encoding="utf-8"))
        assert data["tokenizer_engine"] == "mistral"
        assert data["files"][0]["tokens_estimated"] > 0


class TestRecomputeEngine:
    """OrchestratorResult.recompute_engine() : bascule de moteur sans ré-extraction.

    Régression : la GUI ne recalculait rien tant qu'on ne relançait pas
    l'analyse complète après avoir changé le menu déroulant — le tableau
    affichait encore les chiffres de l'ancien moteur sous le libellé du
    nouveau. `recompute_engine` doit produire, sans re-extraire, exactement
    le même résultat qu'un run_analysis direct avec ce moteur.
    """

    def test_recompute_matches_direct_run_with_same_engine(self, tmp_workspace: Path) -> None:
        result = run_analysis(tmp_workspace, context_limit=128000)
        assert result.engine_id == "approx"

        result.recompute_engine("mistral")

        direct = run_analysis(tmp_workspace, context_limit=128000, tokenizer_engine="mistral")
        assert result.engine_id == "mistral"
        assert result.total.tokens_estimated == direct.total.tokens_estimated
        assert [e.tokens_estimated for e in result.estimates] == [
            e.tokens_estimated for e in direct.estimates
        ]

    def test_recompute_does_not_touch_extracted_files(self, tmp_workspace: Path) -> None:
        result = run_analysis(tmp_workspace, context_limit=128000)
        files_before = result.files

        result.recompute_engine("mistral")

        assert result.files is files_before  # même liste, pas de ré-extraction

    def test_recompute_unknown_engine_falls_back_to_approx(self, tmp_workspace: Path) -> None:
        result = run_analysis(tmp_workspace, context_limit=128000, tokenizer_engine="mistral")
        assert result.engine_id == "mistral"

        result.recompute_engine("does-not-exist")

        assert result.engine_id == "approx"

    def test_recompute_updates_blocking_state(self, tmp_path: Path) -> None:
        (tmp_path / "big.txt").write_text("A" * 10_000, encoding="utf-8")
        result = run_analysis(tmp_path, context_limit=100)
        assert result.is_blocked

        # Remonter le plafond avant de rebasculer le moteur : recompute_engine
        # doit réappliquer la logique de blocage avec le plafond courant.
        result.recompute_blocking(1_000_000)
        assert not result.is_blocked

        result.recompute_engine("mistral")
        assert result.context_limit == 1_000_000
