"""Tests de l'extracteur DOCX.

CdC §8.3 — Body, tableaux, headers/footers, footnotes, endnotes.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.extractors.docx import DocxExtractor
from docfuse.models.file_status import FileStatus


class TestDocxExtractor:
    def test_extract_basic_text(self, tmp_path: Path) -> None:
        from docx import Document

        f = tmp_path / "test.docx"
        doc = Document()
        doc.add_paragraph(
            "Ceci est un paragraphe de test avec suffisamment de texte "
            "pour depasser le seuil de quatre-vingt caracteres."
        )
        doc.save(str(f))

        result = DocxExtractor.extract(f, "test.docx")
        assert result.status is FileStatus.READY
        assert "paragraphe de test" in result.text
        assert result.file_type == "docx"

    def test_extract_table(self, tmp_path: Path) -> None:
        from docx import Document

        f = tmp_path / "table.docx"
        doc = Document()
        doc.add_paragraph("Texte avant le tableau " * 10)
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Nom"
        table.cell(0, 1).text = "Valeur"
        table.cell(1, 0).text = "Alpha"
        table.cell(1, 1).text = "Beta"
        doc.save(str(f))

        result = DocxExtractor.extract(f, "table.docx")
        assert result.status is FileStatus.READY
        assert "Nom" in result.text
        assert "Alpha" in result.text

    def test_accepts(self) -> None:
        assert DocxExtractor.accepts(Path("test.docx")) is True
        assert DocxExtractor.accepts(Path("test.pdf")) is False

    def test_safe_extract_no_crash(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.docx"
        result = DocxExtractor.safe_extract(f, "nonexistent.docx")
        assert result.status is FileStatus.ERROR

    def test_count_media_images_empty(self, tmp_path: Path) -> None:
        from docx import Document

        f = tmp_path / "no_images.docx"
        Document().save(str(f))
        result = DocxExtractor.extract(f, "no_images.docx")
        assert result.image_count == 0

    def test_fixture_file(self) -> None:
        fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample.docx"
        if fixture.exists():
            result = DocxExtractor.extract(fixture, "sample.docx")
            assert result.status is FileStatus.READY
            assert "Titre Test" in result.text or "Titre" in result.text

    def test_tracked_changes_insertion_is_extracted(self, tmp_path: Path) -> None:
        """D-069 : le texte inséré en suivi des modifications (w:ins) ne doit
        pas disparaître — `Paragraph.text` de python-docx ne regarde que les
        runs enfants directs de w:p, pas ceux imbriqués sous w:ins."""
        from docx import Document
        from docx.oxml.ns import qn
        from lxml import etree

        f = tmp_path / "tracked_changes.docx"
        doc = Document()
        doc.add_paragraph("Texte normal avant.")
        p = doc.add_paragraph()
        ins = etree.SubElement(p._p, qn("w:ins"))
        ins.set(qn("w:id"), "1")
        ins.set(qn("w:author"), "Test")
        r = etree.SubElement(ins, qn("w:r"))
        t = etree.SubElement(r, qn("w:t"))
        t.text = "TEXTE_INSERE_SUIVI_MODIFS"
        doc.save(str(f))

        result = DocxExtractor.extract(f, "tracked_changes.docx")
        assert result.status is FileStatus.READY
        assert "TEXTE_INSERE_SUIVI_MODIFS" in result.text

    def test_content_control_block_is_extracted(self, tmp_path: Path) -> None:
        """D-069 : un paragraphe entier enveloppé dans un contrôle de contenu
        Word (w:sdt, niveau bloc — omniprésent dans les modèles RH/juridique)
        ne doit pas disparaître : ni "}p" ni "}tbl" ne matchent "}sdt"."""
        from docx import Document
        from docx.oxml.ns import qn
        from lxml import etree

        f = tmp_path / "content_control.docx"
        doc = Document()
        doc.add_paragraph("Texte normal avant.")
        sdt = etree.SubElement(doc.element.body, qn("w:sdt"))
        sdt_content = etree.SubElement(sdt, qn("w:sdtContent"))
        inner_p = etree.SubElement(sdt_content, qn("w:p"))
        inner_r = etree.SubElement(inner_p, qn("w:r"))
        inner_t = etree.SubElement(inner_r, qn("w:t"))
        inner_t.text = "TEXTE_CONTROLE_DE_CONTENU_BLOC"
        # Le sectPr final doit rester le dernier enfant du body (contrat OOXML)
        sect_pr = doc.element.body.find(qn("w:sectPr"))
        if sect_pr is not None:
            doc.element.body.append(sect_pr)
        doc.save(str(f))

        result = DocxExtractor.extract(f, "content_control.docx")
        assert result.status is FileStatus.READY
        assert "TEXTE_CONTROLE_DE_CONTENU_BLOC" in result.text
