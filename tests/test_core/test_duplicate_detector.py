"""Tests de la détection de doublons de contenu entre fichiers."""

from __future__ import annotations

from pathlib import Path

from docfuse.core.duplicate_detector import detect_duplicates
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus


def _file(relative_path: str, text: str, status: FileStatus = FileStatus.READY) -> ExtractedFile:
    return ExtractedFile(
        path=Path(relative_path),
        relative_path=relative_path,
        extension="txt",
        file_type="text",
        size_bytes=len(text.encode("utf-8")),
        text=text,
        status=status,
    )


class TestDetectDuplicates:
    def test_identical_content_marked_as_duplicate(self) -> None:
        long_text = "Contenu identique repete pour depasser le seuil minimum de caracteres requis."
        a = _file("dossier1/rapport.docx", long_text)
        b = _file("dossier2/copie_rapport.docx", long_text)

        detect_duplicates([a, b])

        assert "duplicate_of" not in a.extra_metadata
        assert a.text == long_text
        assert b.extra_metadata["duplicate_of"] == "dossier1/rapport.docx"
        assert "dossier1/rapport.docx" in b.text
        assert long_text not in b.text

    def test_different_content_not_marked(self) -> None:
        a = _file("a.txt", "Un texte suffisamment long pour depasser le seuil de detection ici.")
        b = _file("b.txt", "Un autre texte totalement different, aussi assez long pour le seuil.")

        detect_duplicates([a, b])

        assert "duplicate_of" not in a.extra_metadata
        assert "duplicate_of" not in b.extra_metadata

    def test_short_texts_never_compared(self) -> None:
        a = _file("a.txt", "court")
        b = _file("b.txt", "court")

        detect_duplicates([a, b])

        assert "duplicate_of" not in b.extra_metadata

    def test_non_extracted_files_skipped(self) -> None:
        long_text = "Contenu identique repete pour depasser le seuil minimum de caracteres requis."
        a = _file("a.txt", long_text)
        b = _file("b.txt", long_text, status=FileStatus.ERROR)

        detect_duplicates([a, b])

        assert "duplicate_of" not in b.extra_metadata

    def test_three_way_duplicate_all_point_to_first(self) -> None:
        long_text = "Contenu identique repete pour depasser le seuil minimum de caracteres requis."
        a = _file("a.txt", long_text)
        b = _file("b.txt", long_text)
        c = _file("c.txt", long_text)

        detect_duplicates([a, b, c])

        assert b.extra_metadata["duplicate_of"] == "a.txt"
        assert c.extra_metadata["duplicate_of"] == "a.txt"
