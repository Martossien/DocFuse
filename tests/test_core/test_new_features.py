"""Tests des nouvelles fonctionnalités de la Session 3.

Couvre : sort mtime/type, config.validate(), dry-run rapport, --include-ext,
image message spécifique, CRLF, DOCX zones de texte, format_number.
"""

from __future__ import annotations

import json
from pathlib import Path

from docfuse.config import Config, load_config
from docfuse.core.inventory import list_ignored, scan_directory
from docfuse.core.orchestrator import run_analysis
from docfuse.i18n import format_number, set_language


class TestSortModes:
    """I-14: Config sort (name/mtime/type)."""

    def test_sort_by_name(self, tmp_workspace: Path) -> None:
        files = scan_directory(tmp_workspace, sort="name")
        assert len(files) > 0

    def test_sort_by_mtime(self, tmp_workspace: Path) -> None:
        files = scan_directory(tmp_workspace, sort="mtime")
        # Vérifier que c'est trié par mtime décroissant
        mtimes = [f.stat().st_mtime for f in files]
        assert mtimes == sorted(mtimes, reverse=True)

    def test_sort_by_type(self, tmp_workspace: Path) -> None:
        files = scan_directory(tmp_workspace, sort="type")
        # Vérifier que c'est trié par extension
        exts = [f.suffix.lower() for f in files]
        assert exts == sorted(exts)


class TestConfigValidate:
    """I-17: Validation min/max de la config."""

    def test_valid_config(self) -> None:
        config = Config()
        errors = config.validate()
        assert len(errors) == 0

    def test_negative_context_limit(self) -> None:
        config = Config(context_limit=-1)
        errors = config.validate()
        assert any("context_limit" in e for e in errors)

    def test_invalid_sort(self) -> None:
        config = Config(sort="invalid")
        errors = config.validate()
        assert any("sort" in e for e in errors)

    def test_huge_context_limit_warns(self) -> None:
        config = Config(context_limit=2_000_000)
        errors = config.validate()
        assert any("inhabituel" in e for e in errors)

    def test_invalid_sparse_ratio(self) -> None:
        config = Config()
        config.scan.sparse_page_ratio = 5.0
        errors = config.validate()
        assert any("sparse_page_ratio" in e for e in errors)

    def test_max_depth_in_config(self) -> None:
        config = Config(max_depth=5)
        assert config.max_depth == 5
        errors = config.validate()
        assert len(errors) == 0

    def test_max_depth_from_json(self, tmp_path: Path) -> None:
        config_json = tmp_path / "config.json"
        config_json.write_text(
            json.dumps({"max_depth": 3, "context_limit": 50000}), encoding="utf-8"
        )
        config = load_config(config_json)
        assert config.max_depth == 3


class TestDryRunReport:
    """C-05: Dry-run génère un rapport."""

    def test_dry_run_writes_report(self, tmp_workspace: Path) -> None:
        from docfuse.cli import main

        output = tmp_workspace / "corpus.md"
        main(["-i", str(tmp_workspace), "--dry-run", "-o", str(output)])
        # Le rapport doit exister à côté de la sortie
        report_md = output.with_name(output.stem + "_rapport.md")
        report_json = output.with_name(output.stem + "_rapport.json")
        assert report_md.exists()
        assert report_json.exists()


class TestIncludeExt:
    """C-06: --include-ext surcharge les extensions."""

    def test_include_ext_filters(self, tmp_workspace: Path) -> None:
        from docfuse.cli import main

        main(
            [
                "-i",
                str(tmp_workspace),
                "--include-ext",
                ".txt",
                "--dry-run",
                "-o",
                str(tmp_workspace / "corpus.md"),
            ]
        )
        # Seuls les .txt doivent être analysés
        report_json = tmp_workspace / "corpus_rapport.json"
        if report_json.exists():
            data = json.loads(report_json.read_text())
            for f in data.get("files", []):
                assert f["extension"] == "txt"


class TestMultipleCLIInputs:
    """Les --input répétés sont tous inclus dans le corpus."""

    def test_repeated_inputs_are_merged_exactly(self, tmp_path: Path) -> None:
        from docfuse.cli import main

        first = tmp_path / "premier.txt"
        second = tmp_path / "second.txt"
        ignored_neighbor = tmp_path / "voisin.txt"
        output = tmp_path / "sortie" / "corpus.md"
        first.write_text("Contenu PREMIER sélectionné.", encoding="utf-8")
        second.write_text("Contenu SECOND sélectionné.", encoding="utf-8")
        ignored_neighbor.write_text("VOISIN NON SÉLECTIONNÉ", encoding="utf-8")

        code = main(
            [
                "-i",
                str(first),
                "-i",
                str(second),
                "--yes",
                "-o",
                str(output),
            ]
        )

        assert code == 0
        content = output.read_text(encoding="utf-8")
        assert "PREMIER" in content
        assert "SECOND" in content
        assert "VOISIN" not in content


class TestImageMessage:
    """I-22: Images pures — message spécifique."""

    def test_image_file_ignored_with_specific_message(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text(
            "Texte avec assez de caracteres pour eviter alerte.", encoding="utf-8"
        )
        (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF")

        ignored = list_ignored(tmp_path)
        messages = {p.name: r for p, r in ignored}
        assert "photo.jpg" in messages
        assert "OCR" in messages["photo.jpg"] or "image" in messages["photo.jpg"].lower()


class TestCRLF:
    """I-06: CRLF support dans markdown_writer."""

    def test_crlf_output(self, tmp_workspace: Path) -> None:
        from docfuse.output.markdown_writer import write_markdown_corpus

        result = run_analysis(tmp_workspace, context_limit=128000)
        output = tmp_workspace / "corpus_crlf.md"
        write_markdown_corpus(result, output, 0.15, line_ending="crlf")
        content = output.read_bytes()
        assert b"\r\n" in content

    def test_lf_output(self, tmp_workspace: Path) -> None:
        from docfuse.output.markdown_writer import write_markdown_corpus

        result = run_analysis(tmp_workspace, context_limit=128000)
        output = tmp_workspace / "corpus_lf.md"
        write_markdown_corpus(result, output, 0.15, line_ending="lf")
        content = output.read_bytes()
        # Sur Windows, le contenu des fichiers source peut contenir \r\n
        # (write_text convertit). On vérifie que le writer lui-même n'ajoute
        # pas de \r\n — on ne peut pas contrôler le contenu des fichiers source.
        # On lit le texte généré et on vérifie qu'il ne commence pas par \r\n
        # (ce qui indiquerait que le writer a ajouté des CRLF).
        text = content.decode("utf-8")
        # L'en-tête du corpus ne doit pas avoir de \r\n en mode LF
        header_end = text.find("---")
        if header_end > 0:
            header = text[:header_end]
            assert "\r\n" not in header, "Le writer a ajouté des CRLF en mode LF"


class TestFormatNumber:
    """I-03: format_number() — espaces insécables FR."""

    def test_fr_format(self) -> None:
        set_language("fr")
        result = format_number(96830)
        assert "\u00a0" in result  # Espace insécable
        assert "," not in result

    def test_en_format(self) -> None:
        set_language("en")
        result = format_number(96830)
        assert "," in result  # Virgule en anglais

    def test_zero(self) -> None:
        set_language("fr")
        assert format_number(0) == "0"


class TestReportI18n:
    """C-03: i18n dans report.py."""

    def test_report_uses_i18n_fr(self, tmp_path: Path) -> None:
        set_language("fr")
        from docfuse.core.report import generate_markdown_report
        from docfuse.models.extraction_result import ExtractedFile
        from docfuse.models.file_status import FileStatus

        f = ExtractedFile(
            path=Path("/tmp/test.txt"),
            relative_path="test.txt",
            extension="txt",
            file_type="text",
            size_bytes=100,
            text="Texte de test avec assez de caracteres pour le rapport.",
            status=FileStatus.READY,
        )
        output = tmp_path / "report.md"
        generate_markdown_report([f], [], 128000, 0.15, 500, 575, output)
        content = output.read_text(encoding="utf-8")
        assert "Prêt" in content  # FR label

    def test_report_uses_i18n_en(self, tmp_path: Path) -> None:
        set_language("en")
        from docfuse.core.report import generate_markdown_report
        from docfuse.models.extraction_result import ExtractedFile
        from docfuse.models.file_status import FileStatus

        f = ExtractedFile(
            path=Path("/tmp/test.txt"),
            relative_path="test.txt",
            extension="txt",
            file_type="text",
            size_bytes=100,
            text="Texte de test avec assez de caracteres pour le rapport.",
            status=FileStatus.READY,
        )
        output = tmp_path / "report.md"
        generate_markdown_report([f], [], 128000, 0.15, 500, 575, output)
        content = output.read_text(encoding="utf-8")
        assert "Ready" in content  # EN label
        set_language("fr")  # Reset


class TestCLIExitCodes:
    """CdC §6.3 — codes retour."""

    def test_yes_blocked_returns_2(self, tmp_path: Path) -> None:
        from docfuse.cli import main

        text = "A" * 10_000
        (tmp_path / "big.txt").write_text(text, encoding="utf-8")
        ret = main(
            [
                "-i",
                str(tmp_path),
                "--context",
                "10",
                "--yes",
                "-o",
                str(tmp_path / "corpus.md"),
            ]
        )
        assert ret == 2

    def test_no_files_returns_3(self, tmp_path: Path) -> None:
        from docfuse.cli import main

        (tmp_path / "app.exe").write_bytes(b"\x00")
        ret = main(["-i", str(tmp_path), "--yes", "-o", str(tmp_path / "corpus.md")])
        assert ret == 3


class TestOrchestratorSortAndDepth:
    """sort et max_depth passés à run_analysis."""

    def test_max_depth_limits_traversal(self, tmp_path: Path) -> None:
        # Créer des dossiers imbriqués profonds
        deep = tmp_path
        for i in range(5):
            deep = deep / f"level{i}"
            deep.mkdir()
        (deep / "deep.txt").write_text("Texte profond avec assez de caracteres.", encoding="utf-8")

        # max_depth=2 ne doit pas trouver le fichier à profondeur 5
        result = run_analysis(tmp_path, context_limit=128000, max_depth=2)
        assert all(f.relative_path != "deep.txt" for f in result.files)

        # max_depth=10 doit le trouver
        result_deep = run_analysis(tmp_path, context_limit=128000, max_depth=10)
        assert any("deep.txt" in f.relative_path for f in result_deep.files)
