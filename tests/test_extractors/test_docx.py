"""Tests de l'extracteur DOCX.

CdC §8.3 — Body, tableaux, headers/footers, footnotes, endnotes.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.extractors.docx import DocxExtractor
from docfuse.models.file_status import FileStatus


def _inject_textbox(docx_path: Path, part_name: str, before_closing_tag: str, text: str) -> None:
    """Injecte un `w:txbxContent` minimal (VML legacy `w:pict`, comme
    produit par Word) dans une partie ZIP d'un .docx déjà sauvegardé —
    python-docx ne permet pas de créer des zones de texte par API."""
    import zipfile

    with zipfile.ZipFile(str(docx_path)) as zf:
        xml = zf.read(part_name).decode("utf-8")

    textbox_xml = (
        "<w:p><w:r><w:pict><v:shape><v:textbox><w:txbxContent>"
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"
        "</w:txbxContent></v:textbox></v:shape></w:pict></w:r></w:p>"
    )
    new_xml = xml.replace(before_closing_tag, textbox_xml + before_closing_tag)
    assert new_xml != xml, f"balise de fermeture {before_closing_tag!r} introuvable"

    with zipfile.ZipFile(str(docx_path)) as zin:
        items = zin.infolist()
        contents = {item.filename: zin.read(item.filename) for item in items}
    contents[part_name] = new_xml.encode("utf-8")
    with zipfile.ZipFile(str(docx_path), "w", zipfile.ZIP_DEFLATED) as zout:
        for item in items:
            zout.writestr(item, contents[item.filename])


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

    def test_textbox_in_body_is_extracted(self, tmp_path: Path) -> None:
        """D-082 : `find_all("w:txbxcontent")` (minuscules) ne matchait
        jamais `<w:txbxContent>` (casse réelle produite par Word, sensible
        à la casse dans le parseur XML BeautifulSoup) — l'extraction des
        zones de texte ne trouvait donc jamais rien, sur aucun fichier."""
        from docx import Document

        f = tmp_path / "textbox_body.docx"
        doc = Document()
        doc.add_paragraph("Corps normal.")
        doc.save(str(f))

        _inject_textbox(f, "word/document.xml", "</w:body>", "TEXTE_BOITE_CORPS")

        result = DocxExtractor.extract(f, "textbox_body.docx")
        assert result.status is FileStatus.READY
        assert "TEXTE_BOITE_CORPS" in result.text

    def test_textbox_in_header_is_extracted(self, tmp_path: Path) -> None:
        """D-082 : une zone de texte dans un en-tête/pied de page (logo +
        bloc adresse en papier à en-tête) était invisible — seul
        document.xml était lu, jamais word/header*.xml."""
        from docx import Document

        f = tmp_path / "textbox_header.docx"
        doc = Document()
        doc.add_paragraph("Corps normal.")
        section = doc.sections[0]
        section.header.is_linked_to_previous = False
        section.header.paragraphs[0].text = "En-tete texte normal"
        doc.save(str(f))

        _inject_textbox(f, "word/header1.xml", "</w:hdr>", "TEXTE_BOITE_EN_TETE")

        result = DocxExtractor.extract(f, "textbox_header.docx")
        assert result.status is FileStatus.READY
        assert "TEXTE_BOITE_EN_TETE" in result.text

    def test_nested_table_in_cell_is_extracted(self, tmp_path: Path) -> None:
        """D-083 : `_Cell.paragraphs` ne liste que les paragraphes directs
        d'une cellule, jamais un tableau imbriqué (fréquent dans les
        gabarits de rapports/formulaires complexes)."""
        from docx import Document

        f = tmp_path / "nested_table.docx"
        doc = Document()
        table = doc.add_table(rows=1, cols=1)
        cell = table.cell(0, 0)
        cell.text = "TEXTE_CELLULE_EXTERNE"
        inner = cell.add_table(rows=1, cols=1)
        inner.cell(0, 0).text = "TEXTE_TABLEAU_IMBRIQUE"
        doc.save(str(f))

        result = DocxExtractor.extract(f, "nested_table.docx")
        assert result.status is FileStatus.READY
        assert "TEXTE_CELLULE_EXTERNE" in result.text
        assert "TEXTE_TABLEAU_IMBRIQUE" in result.text
