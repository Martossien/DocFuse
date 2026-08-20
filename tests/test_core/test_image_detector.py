"""Tests du détecteur d'images et de pauvreté de texte.

CdC §9 — Deux niveaux d'alerte.
"""

from __future__ import annotations

from docfuse.core.image_detector import check_low_text, determine_status
from docfuse.models.file_status import FileStatus


class TestCheckLowText:
    def test_empty_text_is_low(self) -> None:
        assert check_low_text("") is True

    def test_short_text_is_low(self) -> None:
        assert check_low_text("abc") is True  # < 80 chars

    def test_normal_text_not_low(self) -> None:
        text = "A" * 200
        assert check_low_text(text) is False

    def test_pdf_low_avg_chars_per_page(self) -> None:
        # 10 pages avec 10 caractères chacune → moyenne 10 < 50
        chars_per_page = [10] * 10
        assert check_low_text("A" * 100, chars_per_page=chars_per_page) is True

    def test_pdf_normal_chars_per_page(self) -> None:
        # 10 pages avec 200 caractères chacune
        chars_per_page = [200] * 10
        text = "A" * 2000
        assert check_low_text(text, chars_per_page=chars_per_page) is False

    def test_pdf_sparse_pages_with_images(self) -> None:
        # 10 pages, 4 sparse (< 20 chars) + images → 40% >= 30%
        chars_per_page = [5, 5, 5, 5, 200, 200, 200, 200, 200, 200]
        text = "A" * 1000
        assert check_low_text(text, chars_per_page=chars_per_page, image_count=3) is True

    def test_pdf_sparse_pages_without_images(self) -> None:
        # Sans images, pas d'alerte sparse
        chars_per_page = [5, 5, 5, 5, 200, 200, 200, 200, 200, 200]
        text = "A" * 1000
        assert check_low_text(text, chars_per_page=chars_per_page, image_count=0) is False


class TestDetermineStatus:
    def test_ready_status(self) -> None:
        text = "A" * 200
        status = determine_status(text, image_count=0)
        assert status is FileStatus.READY

    def test_images_status(self) -> None:
        text = "A" * 200
        status = determine_status(text, image_count=3)
        assert status is FileStatus.IMAGES

    def test_low_text_status(self) -> None:
        text = "abc"
        status = determine_status(text, image_count=0)
        assert status is FileStatus.LOW_TEXT

    def test_low_text_with_images(self) -> None:
        # Low text + images → LOW_TEXT (le plus grave)
        text = "abc"
        status = determine_status(text, image_count=5)
        assert status is FileStatus.LOW_TEXT

    def test_error_overrides(self) -> None:
        status = determine_status("", image_count=0, has_error=True)
        assert status is FileStatus.ERROR

    def test_ignored_overrides(self) -> None:
        status = determine_status("", image_count=0, is_ignored=True)
        assert status is FileStatus.IGNORED
