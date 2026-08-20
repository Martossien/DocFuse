"""Fixtures partagées pour les tests de DocFuse."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Crée un dossier de travail temporaire avec des fichiers de test."""
    (tmp_path / "subdir").mkdir()

    # Fichier texte simple
    (tmp_path / "doc1.txt").write_text(
        "Ceci est un document texte avec suffisamment de caracteres pour eviter l alerte.\nLigne 2.\n",
        encoding="utf-8",
    )

    # Fichier Markdown
    (tmp_path / "notes.md").write_text(
        "# Titre\n\nParagraphe de notes avec suffisamment de caracteres pour eviter l alerte.\n",
        encoding="utf-8",
    )

    # Fichier JSON
    (tmp_path / "data.json").write_text(
        '{"cle": "valeur avec du texte", "nombre": 42, "description": "test donnees"}',
        encoding="utf-8",
    )

    # Fichier CSV
    (tmp_path / "table.csv").write_text("nom,valeur,description\n1,2,3\n4,5,6\n", encoding="utf-8")

    # Fichier HTML
    (tmp_path / "page.html").write_text(
        "<html><body><h1>Titre</h1><p>Paragraphe avec suffisamment de texte pour eviter l alerte.</p></body></html>",
        encoding="utf-8",
    )

    # Fichier ignoré (extension non supportée)
    (tmp_path / "program.exe").write_bytes(b"\x00\x01\x02\x03")

    # Fichier de verrouillage Office
    (tmp_path / "~$locked.docx").write_bytes(b"\x00")

    # Fichier dans un sous-dossier
    (tmp_path / "subdir" / "deep.txt").write_text(
        "Texte en profondeur avec assez de caracteres pour eviter l alerte.\n",
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture
def fixtures_dir() -> Path:
    """Retourne le dossier des fixtures binaires pré-générées."""
    return FIXTURES_DIR


@pytest.fixture
def large_text(tmp_path: Path) -> Path:
    """Crée un fichier texte qui dépasse le plafond (simulé bas)."""
    # 200 000 caractères → ~50 000 tokens → avec marge 57 500
    # Si plafond = 1000, ça bloque
    text = "A" * 200_000
    (tmp_path / "huge.txt").write_text(text, encoding="utf-8")
    return tmp_path / "huge.txt"
