"""Non-régression de l'audit D-099 (lot 4 : maintenabilité et cohérence).

Chaque test verrouille un comportement introduit ou corrigé par la
factorisation : politique unique de `file_type`, gardes conteneur, notes,
rapports, chemins partagés CLI/GUI, helpers purs de la GUI, CLI.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from docfuse import i18n
from docfuse.cli import main
from docfuse.core.embedded_images import dedupe_image_filenames
from docfuse.core.orchestrator import generate_corpus, run_analysis
from docfuse.core.progress import ProgressEmitter
from docfuse.core.report import write_report_pair
from docfuse.extractors.base import container_guard, error_result_message, file_type_for
from docfuse.extractors.odf import OdfExtractor
from docfuse.extractors.text import decode_text_with_note, mojibake_metadata
from docfuse.gui import build_summary_lines, gauge_color, parse_context_limit
from docfuse.i18n import t
from docfuse.models.extraction_result import EmbeddedImage, ExtractedFile
from docfuse.models.file_status import FileStatus
from docfuse.models.input_selection import InputSelection
from docfuse.output.paths import corpus_extension, default_corpus_path, report_base_path

_OLE_MAGIC = bytes((0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1))


def _write_odt(path: Path, paragraph: str) -> None:
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        f"<office:body><office:text><text:p>{paragraph}</text:p></office:text></office:body>"
        "</office:document-content>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        zf.writestr("content.xml", content)


class TestFileTypePolicy:
    def test_ready_and_error_share_the_same_file_type(self, tmp_path: Path) -> None:
        good = tmp_path / "bon.odt"
        _write_odt(good, "Bonjour")
        bad = tmp_path / "cassé.odt"
        bad.write_bytes(b"pas un zip du tout")

        ready = OdfExtractor.safe_extract(good, "bon.odt")
        error = OdfExtractor.safe_extract(bad, "cassé.odt")

        assert ready.status is FileStatus.READY
        assert error.status is FileStatus.ERROR
        # Avant D-099 : "odt" côté READY, "odf" côté ERREUR.
        assert ready.file_type == error.file_type == "odt"
        assert file_type_for(Path("X/Doc.YAML")) == "yaml"

    def test_container_guard(self, tmp_path: Path) -> None:
        locked = tmp_path / "secret.docx"
        locked.write_bytes(_OLE_MAGIC + b"\x00" * 64)
        guard = container_guard(locked, "secret.docx")
        assert guard is not None
        assert guard.status is FileStatus.ERROR
        assert guard.error_message == t("error.encrypted_office")
        assert guard.file_type == "docx"
        # ODF/EPUB : pas de détection OLE (un ODF n'est jamais chiffré ainsi).
        assert container_guard(locked, "secret.docx", check_ole=False) is None

        plain = tmp_path / "ok.pptx"
        with zipfile.ZipFile(plain, "w") as zf:
            zf.writestr("a.txt", "x")
        assert container_guard(plain, "ok.pptx") is None

    def test_error_result_message(self, tmp_path: Path) -> None:
        path = tmp_path / "f.xlsx"
        path.write_bytes(b"x")
        result = error_result_message(path, "f.xlsx", "message clair")
        assert (result.status, result.error_message, result.size_bytes) == (
            FileStatus.ERROR,
            "message clair",
            1,
        )


class TestSharedHelpers:
    def test_decode_text_with_note(self) -> None:
        encoding, text, meta = decode_text_with_note("Ã©tÃ©".encode())
        assert (encoding, text) == ("utf-8", "été")
        assert meta == {"mojibake_repaired": t("text.mojibake_repaired_note")}
        assert decode_text_with_note(b"plain ascii")[2] == {}
        assert mojibake_metadata(False) == {}

    def test_write_report_pair_always_writes_both(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("Un texte suffisamment long pour être compté.", "utf-8")
        result = run_analysis(tmp_path, context_limit=50_000, margin=0.2)

        md, js = write_report_pair(result, tmp_path / "out" / "rapport.json")

        assert (md.name, js.name) == ("rapport.md", "rapport.json")
        assert md.read_text("utf-8").startswith("# ")
        data = json.loads(js.read_text("utf-8"))
        assert (data["context_limit"], data["margin"]) == (50_000, 0.2)
        assert data["files"][0]["embedded_images_count"] == 0

    def test_output_paths_shared_by_cli_and_gui(self, tmp_path: Path) -> None:
        doc = tmp_path / "sub" / "note.txt"
        doc.parent.mkdir()
        doc.write_text("x", "utf-8")

        selection = InputSelection.from_paths([doc])
        assert (
            default_corpus_path(selection, "pdf") == doc.parent / "CorpusOne_output" / "corpus.pdf"
        )
        assert default_corpus_path(InputSelection.from_paths([tmp_path]), "md") == (
            tmp_path / "CorpusOne_output" / "corpus.md"
        )
        assert report_base_path(Path("/x/corpus.pdf")) == Path("/x/corpus_rapport.md")
        assert corpus_extension("md") == ".md"
        with pytest.raises(ValueError, match="docx"):
            corpus_extension("docx")

    def test_secrets_note_is_capped_per_kind(self, tmp_path: Path) -> None:
        lines = [f"AKIAABCDEFGHIJKLMN{i:02d}" for i in range(15)]
        (tmp_path / "keys.log").write_text("\n".join(lines), "utf-8")
        result = run_analysis(tmp_path, context_limit=128_000)

        note = result.files[0].extra_metadata["secrets_detected"]
        assert note.startswith(t("secret.kind_aws_key"))
        assert "1, 2, 3, 4, 5, 6, 7, 8, 9, 10" in note
        assert t("secret.finding_more", count=5) in note
        assert "11" not in note.split(t("secret.finding_more", count=5))[0]

    def test_dedupe_image_filenames_keeps_tag_and_file_consistent(self, tmp_path: Path) -> None:
        def make(rel: str) -> ExtractedFile:
            return ExtractedFile(
                path=tmp_path / rel,
                relative_path=rel,
                extension="docx",
                file_type="docx",
                size_bytes=1,
                text="[[IMAGE: r__img1.png — texte OCR (tesseract, fra+eng)]]\nfoo\n[[IMAGE: r__img2.png]]",
                embedded_images=[
                    EmbeddedImage("r__img1.png", b"1"),
                    EmbeddedImage("r__img2.png", b"2"),
                ],
            )

        first, second = make("r.docx"), make("r.docx")
        assert dedupe_image_filenames([first, second]) == 2
        assert [i.filename for i in first.embedded_images] == ["r__img1.png", "r__img2.png"]
        assert [i.filename for i in second.embedded_images] == ["r__img1_2.png", "r__img2_2.png"]
        assert "[[IMAGE: r__img1_2.png — texte OCR" in second.text
        assert "[[IMAGE: r__img2_2.png]]" in second.text
        assert first.text == make("r.docx").text


class TestOrchestrator:
    def test_progress_current_is_a_monotone_counter(self, tmp_path: Path) -> None:
        for i in range(8):
            (tmp_path / f"f{i}.txt").write_text(f"fichier {i} " * 20, "utf-8")
        emitter = ProgressEmitter()
        run_analysis(tmp_path, emitter=emitter)

        currents = [e.current for e in emitter.drain() if e.status != "pending"]
        assert currents == list(range(1, 9))

    def test_cancelled_analysis_returns_an_empty_flagged_result(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("x" * 100, "utf-8")
        emitter = ProgressEmitter()
        emitter.cancel()
        result = run_analysis(tmp_path, emitter=emitter)
        assert result.cancelled
        assert result.files == []
        assert not run_analysis(tmp_path).cancelled

    def test_markdown_included_verbatim_but_code_fenced(self, tmp_path: Path) -> None:
        (tmp_path / "doc.md").write_text("# Titre\n\n```python\nprint(1)\n```\n", "utf-8")
        (tmp_path / "mod.py").write_text('"""Exemple:\n```\nx\n```\n"""\n', "utf-8")
        result = run_analysis(tmp_path, context_limit=128_000)
        output = tmp_path / "corpus.md"
        assert generate_corpus(result, output)

        corpus = output.read_text("utf-8")
        md_block = corpus.split("doc.md")[1].split("mod.py")[0]
        py_block = corpus.split("mod.py")[1]
        assert "````" not in md_block  # inclus tel quel (CdC §7.3)
        assert "````" in py_block  # backticks adaptatifs
        assert (output.parent / "corpus_rapport.json").exists()


class TestGuiHelpers:
    def test_parse_context_limit(self) -> None:
        assert parse_context_limit(" 200000 ", 128_000) == 200_000
        assert parse_context_limit("abc", 128_000) == 128_000
        assert parse_context_limit("-5", 128_000) == 128_000
        assert parse_context_limit("", 128_000) == 128_000

    def test_gauge_color(self) -> None:
        assert gauge_color(0.0) == gauge_color(0.79)
        assert gauge_color(0.8) != gauge_color(0.79)
        assert gauge_color(1.0) != gauge_color(0.9)

    def test_build_summary_lines_uses_result_block_reason(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("mot " * 400, "utf-8")
        result = run_analysis(tmp_path, context_limit=128_000)
        assert build_summary_lines(result) == [
            t("summary.ok", count=1, limit=i18n.format_number(128_000))
        ]
        result.recompute_blocking(10)
        lines = build_summary_lines(result)
        assert lines == [result.block_reason]
        assert "a.txt" in lines[0]


class TestCli:
    def test_missing_input_returns_1_not_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([]) == 1
        assert t("cli.input_missing") in capsys.readouterr().err

    def test_output_with_unknown_extension_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "a.txt").write_text("x" * 100, "utf-8")
        bad = tmp_path / "notes.txt"
        assert main(["--input", str(tmp_path / "a.txt"), "--output", str(bad)]) == 1
        assert not bad.exists()  # avant : un dossier `notes.txt/` était créé
        assert "notes.txt" in capsys.readouterr().err

    def test_default_output_next_to_a_single_file(self, tmp_path: Path) -> None:
        doc = tmp_path / "seul.txt"
        doc.write_text("Un document seul, texte assez long pour compter." * 3, "utf-8")
        assert main(["--input", str(doc)]) == 0
        assert (tmp_path / "CorpusOne_output" / "corpus.md").exists()


class TestI18n:
    def test_missing_language_falls_back_to_default_and_is_cached(self) -> None:
        i18n.set_language("xx")
        try:
            assert t("app.title") == i18n._load_catalog("fr")["app.title"]
            assert i18n._CATALOGS["xx"] == {}
            assert t("clé.inconnue") == "clé.inconnue"
        finally:
            i18n.set_language("fr")
            i18n._CATALOGS.pop("xx", None)

    def test_dead_keys_removed_and_catalogs_aligned(self) -> None:
        fr, en = i18n._load_catalog("fr"), i18n._load_catalog("en")
        assert set(fr) == set(en)
        for dead in ("app.subtitle", "gui.change_folder", "exit.success", "secret.finding"):
            assert dead not in fr
        assert "secret.finding_lines" in fr
