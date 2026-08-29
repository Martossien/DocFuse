"""D-100 : chaque page du corpus PDF porte le fichier source qu'elle contient.

Les assistants qui indexent un PDF le découpent page par page : une page
autoporteuse (« fichier (i/N) » en en-tête) reste attribuable à sa source
après découpage, ce qu'un `.md` découpé à taille fixe ne garantit pas.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from docfuse.core.orchestrator import generate_corpus, run_analysis
from docfuse.i18n import t
from docfuse.output.pdf_writer import source_position_label


def _page_texts(path: Path) -> list[str]:
    return [page.extract_text() for page in PdfReader(str(path)).pages]


def test_each_page_names_its_source_file(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a_long.txt").write_text("\n".join(f"ligne {i} du premier fichier" for i in range(220)))
    (src / "b.txt").write_text("Second fichier, court.")
    result = run_analysis(src, context_limit=500_000)
    output = tmp_path / "corpus.pdf"
    assert generate_corpus(result, output)

    pages = _page_texts(output)
    assert len(pages) >= 3  # a_long.txt déborde sur plusieurs pages
    a_label = source_position_label("a_long.txt", 1, 2)
    b_label = source_position_label("b.txt", 2, 2)
    a_pages = [p for p in pages if a_label in p]
    b_pages = [p for p in pages if b_label in p]
    assert len(a_pages) >= 2
    assert len(b_pages) == 1
    assert "Second fichier, court." in b_pages[0]
    assert all(b_label not in p for p in a_pages)
    assert t("corpus.page", num=1) in pages[0]
    assert t("corpus.title") in pages[0]


def test_long_relative_path_is_shortened_from_the_left() -> None:
    label = source_position_label("a/" * 60 + "rapport_final.docx", 3, 12)
    assert label.endswith("rapport_final.docx (3/12)")
    assert label.startswith("…")
    assert len(label) < 90
