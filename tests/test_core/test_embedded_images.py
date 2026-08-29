"""Tests des fonctions pures de nommage/marqueurs d'images intégrées (D-091)."""

from __future__ import annotations

from docfuse.core.embedded_images import (
    build_image_marker,
    build_image_tag,
    sanitize_filename_component,
)


class TestSanitizeFilenameComponent:
    def test_replaces_forbidden_windows_characters(self) -> None:
        assert sanitize_filename_component('a:b*c?d"e<f>g|h') == "a_b_c_d_e_f_g_h"

    def test_replaces_path_separators(self) -> None:
        assert sanitize_filename_component("Documents/Sub\\file") == "Documents_Sub_file"

    def test_leaves_safe_characters_untouched(self) -> None:
        assert sanitize_filename_component("rapport_2026-v2") == "rapport_2026-v2"


class TestBuildImageTag:
    def test_with_location(self) -> None:
        tag = build_image_tag("Téléchargements/deck.pptx", "slide12", 1, "png")
        assert tag == "Téléchargements_deck__slide12__img1.png"

    def test_without_location(self) -> None:
        tag = build_image_tag("report.docx", None, 3, "jpeg")
        assert tag == "report__img3.jpeg"

    def test_different_folders_same_filename_do_not_collide(self) -> None:
        tag_a = build_image_tag("DossierA/report.docx", None, 1, "png")
        tag_b = build_image_tag("DossierB/report.docx", None, 1, "png")
        assert tag_a != tag_b

    def test_extension_is_sanitized(self) -> None:
        tag = build_image_tag("a.docx", None, 1, "")
        assert tag.endswith(".png")


class TestBuildImageMarker:
    def test_tag_and_ocr_text(self) -> None:
        marker = build_image_marker("deck__slide1__img1.png", "Bonjour le monde", "fra+eng")
        assert marker == (
            "[[IMAGE: deck__slide1__img1.png — texte OCR (tesseract, fra+eng)]]\nBonjour le monde"
        )

    def test_tag_only(self) -> None:
        assert build_image_marker("deck__slide1__img1.png", "", "fra") == (
            "[[IMAGE: deck__slide1__img1.png]]"
        )

    def test_ocr_text_only(self) -> None:
        marker = build_image_marker(None, "Bonjour", "fra")
        assert marker == "[[IMAGE — texte OCR (tesseract, fra)]]\nBonjour"

    def test_nothing_returns_empty_string(self) -> None:
        assert build_image_marker(None, "", "fra") == ""
        assert build_image_marker(None, "   ", "fra") == ""
