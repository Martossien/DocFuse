"""Tests des fonctions GUI pures, sans ouvrir de fenêtre."""

from docfuse.gui import _parse_dnd_paths


def test_parse_multiple_dropped_files_with_spaces() -> None:
    data = "{C:\\Mes Docs\\premier.pdf} {D:\\Autres Docs\\second.docx}"

    assert _parse_dnd_paths(data) == [
        "C:\\Mes Docs\\premier.pdf",
        "D:\\Autres Docs\\second.docx",
    ]


def test_parse_multiple_dropped_files_without_spaces() -> None:
    data = "C:\\Docs\\premier.pdf D:\\Docs\\second.docx"

    assert _parse_dnd_paths(data) == [
        "C:\\Docs\\premier.pdf",
        "D:\\Docs\\second.docx",
    ]
