"""Tests exhaustifs sur fichiers réels — 75 fichiers de test.

Teste l'extraction de tous les fichiers dans tests/samples_real/ et vérifie
qu'aucun bug n'est présent : pas de corruption, pas de tags visibles,
pas de code RTF, pas de duplication, pas de caractères null.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from docfuse.core.registry import get_extractor_for
from docfuse.models.file_status import FileStatus

SAMPLES_DIR = Path(__file__).resolve().parent / "samples_real"


def _get_test_files() -> list[Path]:
    """Retourne tous les fichiers de test réels."""
    if not SAMPLES_DIR.exists():
        return []
    result = []
    for f in sorted(SAMPLES_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() not in (".exe", ".jpg", ".png", ".bmp", ".tif"):
            result.append(f)
    return result


# Générer dynamiquement les paramètres de test
_test_files = _get_test_files()


@pytest.mark.parametrize("filepath", _test_files, ids=lambda p: p.name)
class TestRealFilesExtraction:
    """Teste l'extraction de chaque fichier réel."""

    def test_no_crash(self, filepath: Path) -> None:
        """L'extraction ne doit jamais crasher."""
        extractor = get_extractor_for(filepath)
        if extractor is None:
            pytest.skip(f"Pas d'extracteur pour {filepath.suffix}")
        result = extractor.safe_extract(filepath, filepath.name)
        assert result is not None

    def test_no_unicode_replacement(self, filepath: Path) -> None:
        """Pas de caractères de remplacement Unicode (corruption)."""
        extractor = get_extractor_for(filepath)
        if extractor is None:
            pytest.skip(f"Pas d'extracteur pour {filepath.suffix}")
        result = extractor.safe_extract(filepath, filepath.name)
        assert "\ufffd" not in result.text, f"{filepath.name}: caractères de remplacement Unicode"

    def test_no_null_chars(self, filepath: Path) -> None:
        """Pas de caractères null dans le texte extrait."""
        extractor = get_extractor_for(filepath)
        if extractor is None:
            pytest.skip(f"Pas d'extracteur pour {filepath.suffix}")
        result = extractor.safe_extract(filepath, filepath.name)
        assert "\x00" not in result.text, f"{filepath.name}: caractères null dans le texte"

    def test_error_has_message(self, filepath: Path) -> None:
        """Si statut ERROR, un message d'erreur doit être présent."""
        extractor = get_extractor_for(filepath)
        if extractor is None:
            pytest.skip(f"Pas d'extracteur pour {filepath.suffix}")
        result = extractor.safe_extract(filepath, filepath.name)
        if result.status is FileStatus.ERROR:
            assert result.error_message, f"{filepath.name}: statut ERROR sans message"

    def test_text_not_empty_for_real_files(self, filepath: Path) -> None:
        """Les fichiers réels (non corrompus) doivent produire du texte."""
        extractor = get_extractor_for(filepath)
        if extractor is None:
            pytest.skip(f"Pas d'extracteur pour {filepath.suffix}")
        # Ignorer les fichiers corrompus et les edge cases
        if any(
            x in filepath.name.lower()
            for x in ["corrupt", "empty", "malform", "garbage", "test_pattern"]
        ):
            pytest.skip(f"Fichier edge case: {filepath.name}")
        result = extractor.safe_extract(filepath, filepath.name)
        if result.status is FileStatus.READY:
            assert len(result.text.strip()) > 0, f"{filepath.name}: texte vide mais statut READY"


class TestHTMLExtraction:
    """Tests spécifiques HTML — pas de tags visibles."""

    def test_no_html_tags_in_html_output(self) -> None:
        f = SAMPLES_DIR / "page_complexe.html"
        if not f.exists():
            pytest.skip("page_complexe.html non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        # Les tags HTML ne doivent pas être visibles
        tags = re.findall(
            r"<(?:html|body|head|div|span|script|style)\b", result.text, re.IGNORECASE
        )
        assert not tags, f"Tags HTML visibles: {tags[:3]}"

    def test_no_css_in_html_output(self) -> None:
        f = SAMPLES_DIR / "page_complexe.html"
        if not f.exists():
            pytest.skip("page_complexe.html non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "font-family" not in result.text
        assert "background:" not in result.text
        assert "border:" not in result.text

    def test_no_javascript_in_html_output(self) -> None:
        f = SAMPLES_DIR / "page_complexe.html"
        if not f.exists():
            pytest.skip("page_complexe.html non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "toggleVisibility" not in result.text
        assert (
            "function" not in result.text.lower()
            or "function" in result.text.lower().count("function") < 2
        )

    def test_html_table_extracted(self) -> None:
        f = SAMPLES_DIR / "page_complexe.html"
        if not f.exists():
            pytest.skip("page_complexe.html non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "pdfminer.six" in result.text
        assert "python-docx" in result.text
        assert "MIT" in result.text

    def test_html_images_counted(self) -> None:
        f = SAMPLES_DIR / "page_complexe.html"
        if not f.exists():
            pytest.skip("page_complexe.html non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert result.image_count >= 2  # architecture.png + logo.png


class TestEMLExtraction:
    """Tests spécifiques EML."""

    def test_no_mime_boundary(self) -> None:
        f = SAMPLES_DIR / "rapport_mensuel.eml"
        if not f.exists():
            pytest.skip("rapport_mensuel.eml non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "----=_Part" not in result.text
        assert "Content-Type:" not in result.text
        assert "Content-Transfer" not in result.text

    def test_subject_extracted(self) -> None:
        f = SAMPLES_DIR / "rapport_mensuel.eml"
        if not f.exists():
            pytest.skip("rapport_mensuel.eml non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "Rapport mensuel" in result.text

    def test_body_not_duplicated(self) -> None:
        """Le corps multipart ne doit pas être dupliqué."""
        f = SAMPLES_DIR / "rapport_mensuel.eml"
        if not f.exists():
            pytest.skip("rapport_mensuel.eml non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        # "Bonjour" ne doit apparaître qu'une fois
        assert result.text.count("Bonjour") <= 1


class TestRTFExtraction:
    """Tests spécifiques RTF."""

    def test_no_rtf_code(self) -> None:
        f = SAMPLES_DIR / "rapport_technique.rtf"
        if not f.exists():
            pytest.skip("rapport_technique.rtf non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "\\rtf" not in result.text
        assert "\\par" not in result.text
        assert "\\fonttbl" not in result.text
        assert "\\f0" not in result.text


class TestODTExtraction:
    """Tests spécifiques ODT."""

    def test_table_not_duplicated(self) -> None:
        f = SAMPLES_DIR / "rapport_audit.odt"
        if not f.exists():
            pytest.skip("rapport_audit.odt non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        # "Firewall" ne doit apparaître qu'une fois (pas de duplication)
        assert result.text.count("Firewall") == 1

    def test_headings_extracted(self) -> None:
        f = SAMPLES_DIR / "rapport_audit.odt"
        if not f.exists():
            pytest.skip("rapport_audit.odt non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "Rapport d'Audit" in result.text
        assert "Perimetre" in result.text


class TestDOCXExtraction:
    """Tests spécifiques DOCX."""

    def test_table_in_document_order(self) -> None:
        """Le tableau doit apparaître dans l'ordre du document."""
        f = SAMPLES_DIR / "analyse_complete.docx"
        if not f.exists():
            pytest.skip("analyse_complete.docx non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        text = result.text
        # Le tableau (Trimestre/module) doit être entre "Résultats" et "Conclusion"
        table_pos = text.find("Module")
        conclusion_pos = text.find("Conclusion")
        assert table_pos > 0
        assert conclusion_pos > table_pos, "Tableau après la conclusion (ordre cassé)"

    def test_headers_footers_extracted(self) -> None:
        f = SAMPLES_DIR / "analyse_complete.docx"
        if not f.exists():
            pytest.skip("analyse_complete.docx non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        # Les headers/footers doivent être présents
        assert "Confidentiel" in result.text or "réservés" in result.text.lower()

    def test_lists_extracted(self) -> None:
        f = SAMPLES_DIR / "analyse_complete.docx"
        if not f.exists():
            pytest.skip("analyse_complete.docx non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "Remplacer" in result.text or "serveurs" in result.text.lower()


class TestPPTXExtraction:
    """Tests spécifiques PPTX."""

    def test_notes_extracted(self) -> None:
        f = SAMPLES_DIR / "presentation_complete.pptx"
        if not f.exists():
            pytest.skip("presentation_complete.pptx non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "Notes" in result.text or "presentateur" in result.text.lower()

    def test_empty_slide_marker(self) -> None:
        f = SAMPLES_DIR / "presentation_complete.pptx"
        if not f.exists():
            pytest.skip("presentation_complete.pptx non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "[[DIAPO" in result.text or "Diapo 4" in result.text

    def test_table_in_pptx(self) -> None:
        f = SAMPLES_DIR / "presentation_complete.pptx"
        if not f.exists():
            pytest.skip("presentation_complete.pptx non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "Solution A" in result.text
        assert "50 000" in result.text or "50000" in result.text


class TestXLSXExtraction:
    """Tests spécifiques XLSX."""

    def test_multiple_sheets(self) -> None:
        f = SAMPLES_DIR / "donnees_completes.xlsx"
        if not f.exists():
            pytest.skip("donnees_completes.xlsx non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "Données" in result.text or "Donnees" in result.text
        assert "Statistiques" in result.text
        assert result.page_count >= 2

    def test_data_values(self) -> None:
        f = SAMPLES_DIR / "donnees_completes.xlsx"
        if not f.exists():
            pytest.skip("donnees_completes.xlsx non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "Dupont" in result.text
        assert "45000" in result.text
        assert "Marketing" in result.text

    def test_empty_sheet_signaled(self) -> None:
        f = SAMPLES_DIR / "donnees_completes.xlsx"
        if not f.exists():
            pytest.skip("donnees_completes.xlsx non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        # La feuille "Graphique" a peu de données
        assert "Graphique" in result.text or "graphique" in result.text.lower()


class TestCSVExtraction:
    """Tests spécifiques CSV."""

    def test_semicolon_delimiter(self) -> None:
        f = SAMPLES_DIR / "donnees_semicolon.csv"
        if not f.exists():
            pytest.skip("donnees_semicolon.csv non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "Dupont" in result.text
        assert "jean.dupont" in result.text
        assert "45000" in result.text

    def test_comma_with_quotes(self) -> None:
        f = SAMPLES_DIR / "donnees_comma.csv"
        if not f.exists():
            pytest.skip("donnees_comma.csv non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "Widget" in result.text
        assert "19.99" in result.text
        # Les guillemets ne doivent pas apparaître dans le texte
        assert '"' not in result.text


class TestEncodingDetection:
    """Tests d'encodage de fichiers texte."""

    def test_utf8_bom(self) -> None:
        f = SAMPLES_DIR / "enc_utf8_bom.txt"
        if not f.exists():
            pytest.skip("enc_utf8_bom.txt non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "BOM" in result.text
        assert "\ufeff" not in result.text  # Le BOM ne doit pas être dans le texte
        assert "utf-8" in (result.encoding or "")

    def test_latin1(self) -> None:
        f = SAMPLES_DIR / "enc_latin1.txt"
        if not f.exists():
            pytest.skip("enc_latin1.txt non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "Latin" in result.text or "ISO" in result.text
        assert "\ufffd" not in result.text

    def test_cp1252(self) -> None:
        f = SAMPLES_DIR / "enc_cp1252.txt"
        if not f.exists():
            pytest.skip("enc_cp1252.txt non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "CP1252" in result.text or "Windows" in result.text
        assert "\ufffd" not in result.text


class TestMarkdownExtraction:
    """Tests spécifiques Markdown."""

    def test_code_blocks_preserved(self) -> None:
        f = SAMPLES_DIR / "doc_api.md"
        if not f.exists():
            pytest.skip("doc_api.md non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "GET /api/documents" in result.text
        assert "Bearer" in result.text

    def test_tables_preserved(self) -> None:
        f = SAMPLES_DIR / "doc_api.md"
        if not f.exists():
            pytest.skip("doc_api.md non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "Méthode" in result.text
        assert "Endpoint" in result.text
        assert "DELETE" in result.text

    def test_not_wrapped_in_backticks(self) -> None:
        """Le markdown ne doit pas être encapsulé dans des backticks."""
        f = SAMPLES_DIR / "guide_installation.md"
        if not f.exists():
            pytest.skip("guide_installation.md non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert not result.text.strip().startswith("````"), "Markdown encapsulé dans des backticks"


class TestXMLExtraction:
    """Tests spécifiques XML."""

    def test_rss_feed(self) -> None:
        f = SAMPLES_DIR / "feed_rss.xml"
        if not f.exists():
            pytest.skip("feed_rss.xml non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "microservices" in result.text
        assert "GitHub Actions" in result.text


class TestJSONExtraction:
    """Tests spécifiques JSON."""

    def test_complex_json(self) -> None:
        f = SAMPLES_DIR / "config_complete.json"
        if not f.exists():
            pytest.skip("config_complete.json non trouvé")
        result = get_extractor_for(f).safe_extract(f, f.name)
        assert "metadata" in result.text
        assert "version" in result.text
        assert "features" in result.text
        assert "extraction" in result.text


class TestEdgeCases:
    """Tests des cas limites."""

    @pytest.fixture
    def tmp_edge_files(self, tmp_path: Path) -> Path:
        """Crée des fichiers edge case dans un dossier temporaire."""
        # PDF corrompu
        (tmp_path / "corrupt.pdf").write_bytes(b"\x89PDF-1.4\nGARBAGE")
        # DOCX corrompu (pas un ZIP)
        (tmp_path / "corrupt.docx").write_bytes(b"Not a DOCX file")
        # HTML avec <br> seulement
        (tmp_path / "br_only.html").write_text(
            "<html><body><br><hr><img src='x.jpg'></body></html>", encoding="utf-8"
        )
        # XML malformé
        (tmp_path / "malformed.xml").write_text("<root><unclosed>Text</root>", encoding="utf-8")
        # JSON malformé
        (tmp_path / "malformed.json").write_text('{"unclosed": ', encoding="utf-8")
        # EML sans sujet
        (tmp_path / "no_subject.eml").write_text(
            "From: test@test.com\n\nCorps du message avec assez de texte pour eviter alerte.",
            encoding="utf-8",
        )
        # CSV vide
        (tmp_path / "empty.csv").write_text("", encoding="utf-8")
        return tmp_path

    def test_corrupt_pdf_returns_error(self, tmp_edge_files: Path) -> None:
        result = get_extractor_for(tmp_edge_files / "corrupt.pdf").safe_extract(
            tmp_edge_files / "corrupt.pdf", "corrupt.pdf"
        )
        assert result.status is FileStatus.ERROR

    def test_corrupt_docx_returns_error(self, tmp_edge_files: Path) -> None:
        result = get_extractor_for(tmp_edge_files / "corrupt.docx").safe_extract(
            tmp_edge_files / "corrupt.docx", "corrupt.docx"
        )
        assert result.status is FileStatus.ERROR

    def test_br_only_html_no_crash(self, tmp_edge_files: Path) -> None:
        """Le HTML avec seulement <br> ne doit pas crasher."""
        result = get_extractor_for(tmp_edge_files / "br_only.html").safe_extract(
            tmp_edge_files / "br_only.html", "br_only.html"
        )
        assert result.status in (FileStatus.READY, FileStatus.LOW_TEXT, FileStatus.ERROR)

    def test_malformed_xml_returns_error(self, tmp_edge_files: Path) -> None:
        result = get_extractor_for(tmp_edge_files / "malformed.xml").safe_extract(
            tmp_edge_files / "malformed.xml", "malformed.xml"
        )
        assert result.status is FileStatus.ERROR

    def test_malformed_json_returns_error(self, tmp_edge_files: Path) -> None:
        result = get_extractor_for(tmp_edge_files / "malformed.json").safe_extract(
            tmp_edge_files / "malformed.json", "malformed.json"
        )
        assert result.status is FileStatus.ERROR

    def test_empty_csv_ready(self, tmp_edge_files: Path) -> None:
        result = get_extractor_for(tmp_edge_files / "empty.csv").safe_extract(
            tmp_edge_files / "empty.csv", "empty.csv"
        )
        assert result.status is FileStatus.READY

    def test_pdf_encrypted_returns_error(self, tmp_path: Path) -> None:
        from pypdf import PdfWriter

        f = tmp_path / "encrypted.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.encrypt("password")
        with open(f, "wb") as out:
            writer.write(out)
        result = get_extractor_for(f).safe_extract(f, "encrypted.pdf")
        assert result.status is FileStatus.ERROR
        assert (
            "mot de passe" in (result.error_message or "").lower()
            or "chiffr" in (result.error_message or "").lower()
        )

    def test_pdf_empty_user_password_is_readable(self, tmp_path: Path) -> None:
        """D-071 : un PDF chiffré avec un mot de passe UTILISATEUR VIDE (juste
        des permissions restreintes — copie/impression) est parfaitement
        lisible et ne doit pas être rejeté comme un PDF réellement protégé.
        `reader.is_encrypted` reste `True` même après déchiffrement réussi ;
        c'est `reader.decrypt("")` qui fait la différence."""
        from pypdf import PdfWriter

        f = tmp_path / "empty_user_password.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.encrypt(user_password="", owner_password="secret_owner_pw")
        with open(f, "wb") as out:
            writer.write(out)

        result = get_extractor_for(f).safe_extract(f, "empty_user_password.pdf")
        assert result.status is not FileStatus.ERROR


class TestCorpusGeneration:
    """Tests de génération de corpus complet."""

    def test_full_corpus_markdown(self, tmp_path: Path) -> None:
        """Génère un corpus Markdown avec tous les fichiers de test."""
        if not SAMPLES_DIR.exists():
            pytest.skip("samples_real non trouvé")

        from docfuse.core.orchestrator import generate_corpus, run_analysis

        result = run_analysis(SAMPLES_DIR, context_limit=999999)  # Plafond très haut
        output = tmp_path / "corpus.md"
        success = generate_corpus(result, output, 999999, 0.15)
        assert success
        assert output.exists()
        content = output.read_text("utf-8")
        assert "# Corpus DocFuse" in content
        assert "## SOURCE:" in content
        # Le rapport doit aussi être généré
        assert (tmp_path / "corpus_rapport.md").exists()
        assert (tmp_path / "corpus_rapport.json").exists()

    def test_corpus_blocked_by_context(self) -> None:
        """Le corpus doit être bloqué si le plafond est trop bas."""
        if not SAMPLES_DIR.exists():
            pytest.skip("samples_real non trouvé")

        from docfuse.core.orchestrator import run_analysis

        result = run_analysis(SAMPLES_DIR, context_limit=10)
        assert result.is_blocked

    def test_corpus_pdf_generation(self, tmp_path: Path) -> None:
        """Génère un corpus PDF avec police Unicode."""
        if not SAMPLES_DIR.exists():
            pytest.skip("samples_real non trouvé")

        from docfuse.core.orchestrator import generate_corpus, run_analysis

        result = run_analysis(SAMPLES_DIR, context_limit=999999)
        output = tmp_path / "corpus.pdf"
        success = generate_corpus(result, output, 999999, 0.15)
        assert success
        assert output.exists()
        assert output.stat().st_size > 1000  # Le PDF ne doit pas être vide
