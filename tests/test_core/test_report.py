"""Tests du rapport d'exécution (MD + JSON).

CdC §11.3 — Rapport toujours émis.
"""

from __future__ import annotations

import json
from pathlib import Path

from docfuse.core.context_counter import TokenEstimate
from docfuse.core.report import generate_json_report, generate_markdown_report
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus


class TestReport:
    def _make_files(self) -> list[ExtractedFile]:
        return [
            ExtractedFile(
                path=Path("/tmp/doc1.txt"),
                relative_path="doc1.txt",
                extension="txt",
                file_type="text",
                size_bytes=100,
                text="Texte de test avec assez de caracteres pour le rapport.",
                status=FileStatus.READY,
            ),
            ExtractedFile(
                path=Path("/tmp/bad.pdf"),
                relative_path="bad.pdf",
                extension="pdf",
                file_type="pdf",
                size_bytes=200,
                text="",
                status=FileStatus.ERROR,
                error_message="PDF corrompu",
            ),
        ]

    def test_json_report(self, tmp_path: Path) -> None:
        files = self._make_files()
        ignored = [(Path("/tmp/app.exe"), "Extension non supportée: .exe")]
        output = tmp_path / "report.json"

        generate_json_report(files, ignored, 128000, 0.15, 500, 575, output)

        assert output.exists()
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["context_limit"] == 128000
        assert data["margin"] == 0.15
        assert data["total_files"] == 2
        assert data["total_ignored"] == 1
        assert len(data["files"]) == 2
        assert data["files"][0]["relative_path"] == "doc1.txt"
        assert data["files"][1]["status"] == "error"
        assert data["ignored"][0]["reason"] == "Extension non supportée: .exe"

    def test_markdown_report(self, tmp_path: Path) -> None:
        files = self._make_files()
        ignored = [(Path("/tmp/app.exe"), "Extension non supportée: .exe")]
        output = tmp_path / "report.md"

        generate_markdown_report(files, ignored, 128000, 0.15, 500, 575, output)

        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "Rapport" in content
        assert "doc1.txt" in content
        assert "app.exe" in content
        assert "PDF corrompu" in content  # Section erreurs

    def test_json_report_defaults_to_approx_engine(self, tmp_path: Path) -> None:
        files = self._make_files()
        output = tmp_path / "report.json"

        generate_json_report(files, [], 128000, 0.15, 500, 575, output)

        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["tokenizer_engine"] == "approx"
        assert "tokens_estimated" not in data["files"][0]  # pas d'estimates fournies

    def test_json_report_with_estimates_uses_engine_per_file_tokens(self, tmp_path: Path) -> None:
        files = self._make_files()
        estimates = [TokenEstimate(400, 100, 115), TokenEstimate(0, 0, 0)]
        output = tmp_path / "report.json"

        generate_json_report(
            files, [], 128000, 0.15, 100, 115, output, estimates=estimates, engine_id="mistral"
        )

        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["tokenizer_engine"] == "mistral"
        assert data["files"][0]["tokens_estimated"] == 100
        assert data["files"][0]["tokens_with_margin"] == 115

    def test_markdown_report_uses_estimates_instead_of_recomputing(self, tmp_path: Path) -> None:
        # Le premier fichier a un texte non vide ; sans `estimates`, le rapport
        # recalculerait ceil(octets/4). On vérifie qu'avec `estimates`, c'est
        # bien cette valeur (et pas le recalcul) qui apparaît dans le tableau.
        files = self._make_files()
        estimates = [TokenEstimate(400, 999, 1149), TokenEstimate(0, 0, 0)]
        output = tmp_path / "report.md"

        generate_markdown_report(
            files, [], 128000, 0.15, 999, 1149, output, estimates=estimates, engine_id="mistral"
        )

        from docfuse.i18n import format_number

        content = output.read_text(encoding="utf-8")
        assert format_number(999) in content
        assert format_number(1149) in content
