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
