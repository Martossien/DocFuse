"""Régressions sur la sélection multi-sources et le retrait de fichiers."""

from __future__ import annotations

from pathlib import Path

from docfuse.core.context_counter import TokenEstimate
from docfuse.core.orchestrator import OrchestratorResult, run_analysis
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus
from docfuse.models.input_selection import InputSelection


class TestInputSelection:
    def test_deduplicates_paths_and_uses_file_parent_for_output(self, tmp_path: Path) -> None:
        source = tmp_path / "source.txt"
        source.write_text("contenu", encoding="utf-8")

        selection = InputSelection.from_paths([source, source])

        assert selection.paths == (source.absolute(),)
        assert selection.output_directory == tmp_path

    def test_exclusion_is_immutable(self, tmp_path: Path) -> None:
        source = tmp_path / "source.txt"
        selection = InputSelection.from_paths([source])

        excluded = selection.exclude(source)

        assert not selection.is_excluded(source)
        assert excluded.is_excluded(source)


class TestMultipleInputs:
    def test_explicit_files_do_not_expand_to_parent_directory(self, tmp_path: Path) -> None:
        selected_a = tmp_path / "a.txt"
        not_selected = tmp_path / "b.txt"
        selected_c = tmp_path / "c.md"
        selected_a.write_text("Texte A suffisamment long pour extraction.", encoding="utf-8")
        not_selected.write_text("Ce fichier ne doit jamais entrer.", encoding="utf-8")
        selected_c.write_text("# Texte C\n\nContenu sélectionné.", encoding="utf-8")

        result = run_analysis([selected_a, selected_c])

        assert [file.path for file in result.files] == [selected_a, selected_c]
        assert not_selected not in {file.path for file in result.files}

    def test_multiple_directories_have_unambiguous_source_paths(self, tmp_path: Path) -> None:
        first = tmp_path / "premier"
        second = tmp_path / "second"
        first.mkdir()
        second.mkdir()
        (first / "document.txt").write_text("Premier contenu.", encoding="utf-8")
        (second / "document.txt").write_text("Second contenu.", encoding="utf-8")

        result = run_analysis([first, second])

        assert {file.relative_path for file in result.files} == {
            str(Path("premier") / "document.txt"),
            str(Path("second") / "document.txt"),
        }

    def test_same_file_is_not_extracted_twice(self, tmp_path: Path) -> None:
        source = tmp_path / "document.txt"
        source.write_text("Contenu unique.", encoding="utf-8")

        result = run_analysis([tmp_path, source])

        assert len(result.files) == 1

    def test_excluded_file_is_reported_and_not_counted(self, tmp_path: Path) -> None:
        kept = tmp_path / "conserve.txt"
        removed = tmp_path / "retire.txt"
        kept.write_text("Texte conservé.", encoding="utf-8")
        removed.write_text("Texte retiré.", encoding="utf-8")
        selection = InputSelection.from_paths([tmp_path]).exclude(removed)

        result = run_analysis(selection)

        assert [file.path for file in result.files] == [kept]
        assert any(path == removed and reason for path, reason in result.ignored)

    def test_each_file_keeps_its_own_token_estimate(self, tmp_path: Path) -> None:
        small = tmp_path / "petit.txt"
        large = tmp_path / "grand.txt"
        small.write_text("Petit texte.", encoding="utf-8")
        large.write_text("Texte beaucoup plus long. " * 100, encoding="utf-8")

        result = run_analysis([small, large])
        estimates_by_name = {
            file.path.name: estimate
            for file, estimate in zip(result.files, result.estimates, strict=True)
        }

        assert (
            estimates_by_name["grand.txt"].tokens_estimated
            > estimates_by_name["petit.txt"].tokens_estimated
        )
        assert result.total.tokens_with_margin == sum(
            estimate.tokens_with_margin for estimate in result.estimates
        )


class TestResultRemoval:
    def test_remove_file_recomputes_total_and_unblocks(self, tmp_path: Path) -> None:
        first = _file(tmp_path / "first.txt", FileStatus.READY)
        second = _file(tmp_path / "second.txt", FileStatus.READY)
        estimates = [TokenEstimate(400, 100, 115), TokenEstimate(400, 100, 115)]
        result = OrchestratorResult(
            [first, second],
            [],
            estimates,
            TokenEstimate(800, 200, 230),
            context_limit=150,
        )
        assert result.is_blocked

        assert result.remove_file(second.path, "retiré")

        assert not result.is_blocked
        assert result.total.tokens_with_margin == 115
        assert result.files == [first]

    def test_recompute_restores_image_warning_after_blocking(self, tmp_path: Path) -> None:
        image_file = _file(tmp_path / "images.pdf", FileStatus.IMAGES)
        estimate = TokenEstimate(800, 200, 230)
        result = OrchestratorResult([image_file], [], [estimate], estimate, context_limit=100)
        assert image_file.status is FileStatus.TOO_LARGE

        result.recompute_blocking(500)

        assert image_file.status is FileStatus.IMAGES
        assert result.count_base_status(FileStatus.IMAGES) == 1


def _file(path: Path, status: FileStatus) -> ExtractedFile:
    return ExtractedFile(
        path=path,
        relative_path=path.name,
        extension="txt",
        file_type="txt",
        size_bytes=400,
        text="contenu",
        status=status,
    )
