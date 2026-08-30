"""Découpage d'un résultat d'analyse en plusieurs corpus par budget de tokens (D-101).

Règles : remplissage séquentiel dans l'ordre du tri (first-fit, jamais de
réordonnancement), un fichier n'est jamais coupé, un fichier qui dépasse à
lui seul le plafond est isolé dans sa propre partie et signalé — jamais
abandonné en silence (règle 12.4).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from docfuse.core.orchestrator import generate_corpus, generate_corpus_parts, run_analysis
from docfuse.core.splitter import CorpusPart, split_by_budget


def _write(tmp_path: Path, name: str, chars: int) -> Path:
    """Fichier texte de `chars` caractères au contenu propre à `name` — des
    contenus identiques seraient dédupliqués (D-064) et leur estimation
    réduite à une note, ce qui fausserait les budgets."""
    path = tmp_path / name
    unit = f"{name} "
    path.write_text((unit * (chars // len(unit) + 1))[:chars], encoding="utf-8")
    return path


class TestSplitByBudget:
    def test_everything_fits_gives_a_single_part(self, tmp_path: Path) -> None:
        for i in range(3):
            _write(tmp_path, f"f{i}.txt", 400)
        result = run_analysis(tmp_path, context_limit=100_000, split_context=True)

        parts = split_by_budget(result)

        assert len(parts) == 1
        assert parts[0].index == 1
        assert parts[0].file_indices == (0, 1, 2)
        assert parts[0].oversized is False
        assert parts[0].tokens_with_margin <= 100_000

    def test_sequential_first_fit_never_reorders(self, tmp_path: Path) -> None:
        # ~100 tokens estimés chacun (400 octets / 4), +15 % → 115 + en-tête.
        for i in range(6):
            _write(tmp_path, f"f{i}.txt", 400)
        result = run_analysis(tmp_path, context_limit=100_000, split_context=True)
        per_file = result.estimates[0].tokens_with_margin
        limit = per_file * 2 + 1  # deux fichiers par partie, jamais trois

        parts = split_by_budget(result, context_limit=limit)

        assert [p.file_indices for p in parts] == [(0, 1), (2, 3), (4, 5)]
        assert [p.index for p in parts] == [1, 2, 3]
        assert all(p.tokens_with_margin <= limit for p in parts)
        assert all(p.oversized is False for p in parts)

    def test_oversized_file_is_isolated_and_flagged(self, tmp_path: Path) -> None:
        _write(tmp_path, "a_small.txt", 200)
        _write(tmp_path, "b_huge.txt", 20_000)
        _write(tmp_path, "c_small.txt", 200)
        result = run_analysis(tmp_path, context_limit=1_000, split_context=True)

        parts = split_by_budget(result)

        assert [p.file_indices for p in parts] == [(0,), (1,), (2,)]
        assert [p.oversized for p in parts] == [False, True, False]
        # Jamais de perte silencieuse : le fichier hors plafond est bien présent.
        assert result.files[1].relative_path == "b_huge.txt"

    def test_split_mode_never_blocks(self, tmp_path: Path) -> None:
        _write(tmp_path, "huge.txt", 20_000)
        _write(tmp_path, "small.txt", 200)

        blocked = run_analysis(tmp_path, context_limit=1_000)
        split = run_analysis(tmp_path, context_limit=1_000, split_context=True)

        assert blocked.is_blocked
        assert not split.is_blocked
        assert split.block_reason is None
        # Le fichier hors plafond reste extractible (pas de statut TOO_LARGE).
        assert all(f.status.is_extracted() for f in split.files)
        # Mais il est connu : les writers et le rapport peuvent le signaler.
        assert [f.relative_path for f in split.oversized_files] == ["huge.txt"]

    def test_recompute_blocking_keeps_split_mode(self, tmp_path: Path) -> None:
        _write(tmp_path, "huge.txt", 20_000)
        result = run_analysis(tmp_path, context_limit=1_000, split_context=True)

        result.recompute_blocking(500)

        assert not result.is_blocked
        result.split_context = False
        result.recompute_blocking(500)
        assert result.is_blocked

    def test_non_extracted_files_are_skipped(self, tmp_path: Path) -> None:
        _write(tmp_path, "ok.txt", 400)
        (tmp_path / "broken.docx").write_bytes(b"not a zip")
        result = run_analysis(tmp_path, context_limit=100_000, split_context=True)

        parts = split_by_budget(result)

        extracted = [i for i, f in enumerate(result.files) if f.status.is_extracted()]
        assert [i for p in parts for i in p.file_indices] == extracted

    def test_empty_result_gives_no_part(self, tmp_path: Path) -> None:
        result = run_analysis(tmp_path, context_limit=100_000, split_context=True)
        assert split_by_budget(result) == []

    def test_part_is_immutable_value_object(self) -> None:
        part = CorpusPart(index=1, file_indices=(0, 1), tokens_estimated=10, tokens_with_margin=12)
        assert part.oversized is False
        with pytest.raises(AttributeError):
            part.index = 2  # type: ignore[misc]


class TestGenerateCorpusParts:
    def test_each_source_appears_exactly_once_across_parts(self, tmp_path: Path) -> None:
        for i in range(5):
            _write(tmp_path, f"f{i}.txt", 400)
        result = run_analysis(tmp_path, context_limit=100_000, split_context=True)
        limit = result.estimates[0].tokens_with_margin * 2 + 1
        result.recompute_blocking(limit)
        out = tmp_path / "out" / "corpus.md"

        paths = generate_corpus_parts(result, out)

        assert [p.name for p in paths] == ["corpus_001.md", "corpus_002.md", "corpus_003.md"]
        seen: list[str] = []
        for path in paths:
            text = path.read_text(encoding="utf-8")
            seen += [
                line.split("## SOURCE: ", 1)[1]
                for line in text.splitlines()
                if line.startswith("## SOURCE: ")
            ]
        assert sorted(seen) == sorted(f.relative_path for f in result.files)
        assert len(seen) == len(set(seen))
        preamble = "\n".join(paths[0].read_text(encoding="utf-8").splitlines()[:14])
        assert "1/3" in preamble

    def test_report_lists_parts_and_part_per_file(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.txt", 400)
        _write(tmp_path, "b_huge.txt", 20_000)
        _write(tmp_path, "c.txt", 400)
        result = run_analysis(tmp_path, context_limit=1_000, split_context=True)
        out = tmp_path / "corpus.md"

        generate_corpus_parts(result, out)

        data = json.loads((tmp_path / "corpus_rapport.json").read_text(encoding="utf-8"))
        assert data["split_context"] is True
        assert [p["index"] for p in data["parts"]] == [1, 2, 3]
        assert [p["oversized"] for p in data["parts"]] == [False, True, False]
        assert data["parts"][1]["files"] == ["b_huge.txt"]
        assert [f["part"] for f in data["files"]] == [1, 2, 3]
        report_md = (tmp_path / "corpus_rapport.md").read_text(encoding="utf-8")
        assert "corpus_002" in report_md

    def test_pdf_parts(self, tmp_path: Path) -> None:
        for i in range(4):
            _write(tmp_path, f"f{i}.txt", 400)
        result = run_analysis(tmp_path, context_limit=100_000, split_context=True)
        result.recompute_blocking(result.estimates[0].tokens_with_margin * 2 + 1)

        paths = generate_corpus_parts(result, tmp_path / "corpus.pdf")

        assert [p.name for p in paths] == ["corpus_001.pdf", "corpus_002.pdf"]
        assert all(p.read_bytes().startswith(b"%PDF") for p in paths)

    def test_generate_corpus_delegates_in_split_mode(self, tmp_path: Path) -> None:
        for i in range(4):
            _write(tmp_path, f"f{i}.txt", 400)
        result = run_analysis(tmp_path, context_limit=100_000, split_context=True)
        result.recompute_blocking(result.estimates[0].tokens_with_margin * 2 + 1)

        assert generate_corpus(result, tmp_path / "corpus.md") is True

        assert (tmp_path / "corpus_001.md").exists()
        assert (tmp_path / "corpus_002.md").exists()
        assert not (tmp_path / "corpus.md").exists()

    def test_single_part_keeps_numbered_name(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.txt", 400)
        result = run_analysis(tmp_path, context_limit=100_000, split_context=True)

        paths = generate_corpus_parts(result, tmp_path / "corpus.md")

        assert [p.name for p in paths] == ["corpus_001.md"]
