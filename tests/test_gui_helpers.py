"""Tests des fonctions GUI pures, sans ouvrir de fenêtre."""

from docfuse.gui import _parse_dnd_paths, resolve_tokenizer_choice


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


def test_resolve_tokenizer_choice_known_label() -> None:
    label_to_id = {"Approximation générique (rapide)": "approx", "Précis (Mistral)": "mistral"}
    assert resolve_tokenizer_choice("Précis (Mistral)", label_to_id) == "mistral"


def test_resolve_tokenizer_choice_unknown_label_falls_back_to_approx() -> None:
    label_to_id = {"Approximation générique (rapide)": "approx"}
    assert resolve_tokenizer_choice("libellé inconnu", label_to_id) == "approx"
