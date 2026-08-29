"""Tests de `output/image_writer.py` (D-091)."""

from __future__ import annotations

from pathlib import Path

from docfuse.models.extraction_result import EmbeddedImage, ExtractedFile
from docfuse.models.file_status import FileStatus
from docfuse.output.image_writer import write_embedded_images


def _file(embedded_images: list[EmbeddedImage]) -> ExtractedFile:
    return ExtractedFile(
        path=Path("source.pptx"),
        relative_path="source.pptx",
        extension="pptx",
        file_type="pptx",
        size_bytes=0,
        status=FileStatus.READY,
        embedded_images=embedded_images,
    )


class TestWriteEmbeddedImages:
    def test_no_images_writes_nothing_and_no_folder(self, tmp_path: Path) -> None:
        output_path = tmp_path / "corpus.md"
        written = write_embedded_images([_file([])], output_path)
        assert written == 0
        assert not (tmp_path / "corpus_images").exists()

    def test_writes_images_to_sibling_folder(self, tmp_path: Path) -> None:
        output_path = tmp_path / "corpus.md"
        images = [
            EmbeddedImage(filename="a__img1.png", data=b"PNGDATA1"),
            EmbeddedImage(filename="a__img2.png", data=b"PNGDATA2"),
        ]
        written = write_embedded_images([_file(images)], output_path)

        assert written == 2
        images_dir = tmp_path / "corpus_images"
        assert (images_dir / "a__img1.png").read_bytes() == b"PNGDATA1"
        assert (images_dir / "a__img2.png").read_bytes() == b"PNGDATA2"

    def test_images_from_multiple_files_go_to_same_folder(self, tmp_path: Path) -> None:
        output_path = tmp_path / "corpus.pdf"
        file_a = _file([EmbeddedImage(filename="a__img1.png", data=b"A")])
        file_b = _file([EmbeddedImage(filename="b__img1.png", data=b"B")])

        written = write_embedded_images([file_a, file_b], output_path)

        assert written == 2
        images_dir = tmp_path / "corpus_images"
        assert (images_dir / "a__img1.png").exists()
        assert (images_dir / "b__img1.png").exists()
