"""Tests des fonctions GUI pures, sans ouvrir de fenêtre."""

from dataclasses import dataclass

from docfuse.gui import _parse_dnd_paths, resolve_tokenizer_choice, sort_file_pairs
from docfuse.models.file_status import FileStatus


@dataclass
class _FakeFile:
    relative_path: str
    file_type: str
    status: FileStatus


@dataclass
class _FakeEstimate:
    tokens_estimated: int
    tokens_with_margin: int


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


def _pairs() -> list[tuple[_FakeFile, _FakeEstimate]]:
    return [
        (_FakeFile("zzz_last.txt", "txt", FileStatus.LOW_TEXT), _FakeEstimate(42, 49)),
        (_FakeFile("aaa_first.txt", "txt", FileStatus.READY), _FakeEstimate(54, 63)),
        (_FakeFile("mmm_middle.py", "py", FileStatus.LOW_TEXT), _FakeEstimate(41, 48)),
    ]


def test_sort_file_pairs_none_column_keeps_original_order() -> None:
    pairs = _pairs()
    assert sort_file_pairs(pairs, None, False) == pairs


def test_sort_file_pairs_by_file_name() -> None:
    result = sort_file_pairs(_pairs(), "file", False)
    assert [f.relative_path for f, _ in result] == [
        "aaa_first.txt",
        "mmm_middle.py",
        "zzz_last.txt",
    ]


def test_sort_file_pairs_by_text_estimated_ascending_then_descending() -> None:
    asc = sort_file_pairs(_pairs(), "text_estimated", False)
    assert [est.tokens_estimated for _, est in asc] == [41, 42, 54]

    desc = sort_file_pairs(_pairs(), "text_estimated", True)
    assert [est.tokens_estimated for _, est in desc] == [54, 42, 41]


def test_sort_file_pairs_by_status_uses_severity_not_label() -> None:
    """D-090 : le tri par statut regroupe par sévérité (READY < LOW_TEXT),
    pas par ordre alphabétique du libellé traduit affiché."""
    result = sort_file_pairs(_pairs(), "status", False)
    assert [f.status for f, _ in result] == [
        FileStatus.READY,
        FileStatus.LOW_TEXT,
        FileStatus.LOW_TEXT,
    ]
