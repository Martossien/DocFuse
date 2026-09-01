"""Tests de la détection de doublons de contenu entre fichiers."""

from __future__ import annotations

from pathlib import Path

from docfuse.core.duplicate_detector import detect_duplicates
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus


def _file(relative_path: str, text: str, status: FileStatus = FileStatus.READY) -> ExtractedFile:
    return ExtractedFile(
        path=Path(relative_path),
        relative_path=relative_path,
        extension="txt",
        file_type="text",
        size_bytes=len(text.encode("utf-8")),
        text=text,
        status=status,
    )


class TestDetectDuplicates:
    def test_identical_content_marked_as_duplicate(self) -> None:
        long_text = "Contenu identique repete pour depasser le seuil minimum de caracteres requis."
        a = _file("dossier1/rapport.docx", long_text)
        b = _file("dossier2/copie_rapport.docx", long_text)

        detect_duplicates([a, b])

        assert "duplicate_of" not in a.extra_metadata
        assert a.text == long_text
        assert b.extra_metadata["duplicate_of"] == "dossier1/rapport.docx"
        assert "dossier1/rapport.docx" in b.text
        assert long_text not in b.text

    def test_different_content_not_marked(self) -> None:
        a = _file("a.txt", "Un texte suffisamment long pour depasser le seuil de detection ici.")
        b = _file("b.txt", "Un autre texte totalement different, aussi assez long pour le seuil.")

        detect_duplicates([a, b])

        assert "duplicate_of" not in a.extra_metadata
        assert "duplicate_of" not in b.extra_metadata

    def test_short_texts_never_compared(self) -> None:
        a = _file("a.txt", "court")
        b = _file("b.txt", "court")

        detect_duplicates([a, b])

        assert "duplicate_of" not in b.extra_metadata

    def test_non_extracted_files_skipped(self) -> None:
        long_text = "Contenu identique repete pour depasser le seuil minimum de caracteres requis."
        a = _file("a.txt", long_text)
        b = _file("b.txt", long_text, status=FileStatus.ERROR)

        detect_duplicates([a, b])

        assert "duplicate_of" not in b.extra_metadata

    def test_three_way_duplicate_all_point_to_first(self) -> None:
        long_text = "Contenu identique repete pour depasser le seuil minimum de caracteres requis."
        a = _file("a.txt", long_text)
        b = _file("b.txt", long_text)
        c = _file("c.txt", long_text)

        detect_duplicates([a, b, c])

        assert b.extra_metadata["duplicate_of"] == "a.txt"
        assert c.extra_metadata["duplicate_of"] == "a.txt"


class TestMarqueursNeFondentPasUneIdentite:
    """D-107 — un texte fait uniquement de marqueurs d'absence de contenu ne
    dit rien du document : il ne peut pas fonder une identité.

    Constaté en production (déploiement à 36 échecs Tesseract) : trois PDF
    scannés de deux pages, sans OCR, produisent le même texte de
    72 caractères et se retrouvaient déclarés « contenu identique » — un
    dossier médical et une facture portant `doublon_de: contrat de
    travail` sur un rapport qui sert à décider de suppressions de fichiers.
    """

    PAGES_VIDES = "[[PAGE 1: aucun texte extractible]]\n\n[[PAGE 2: aucun texte extractible]]"

    def test_pdf_scannes_sans_ocr_ne_sont_pas_des_doublons(self) -> None:
        # Le texte dépasse bien DUPLICATE_MIN_CHARS : c'est ce qui rendait
        # la faute atteignable.
        assert len(self.PAGES_VIDES) > 50

        contrat = _file("contrat_travail_DUPONT.pdf", self.PAGES_VIDES, FileStatus.LOW_TEXT)
        medical = _file("dossier_medical_MARTIN.pdf", self.PAGES_VIDES, FileStatus.LOW_TEXT)
        facture = _file("facture_fournisseur_2019.pdf", self.PAGES_VIDES, FileStatus.LOW_TEXT)

        detect_duplicates([contrat, medical, facture])

        for fichier in (contrat, medical, facture):
            # Ni présenté comme un doublon…
            assert "duplicate_of" not in fichier.extra_metadata
            # …ni amputé de son texte : le fichier reste entier dans le corpus.
            assert fichier.text == self.PAGES_VIDES

    def test_diapos_vides_avec_echafaudage_pptx_non_plus(self) -> None:
        """L'échafaudage `## Diapo N` + `---` fait franchir le seuil à un
        PPTX entièrement scanné dès quelques diapos."""
        texte = "\n\n---\n\n".join(
            f"## Diapo {i}\n\n[[DIAPO {i}: aucun texte extractible]]" for i in range(1, 5)
        )
        assert len(texte) > 50

        a = _file("budget_2024.pptx", texte, FileStatus.LOW_TEXT)
        b = _file("plan_social_RH.pptx", texte, FileStatus.LOW_TEXT)

        detect_duplicates([a, b])

        assert "duplicate_of" not in b.extra_metadata
        assert b.text == texte

    def test_libelle_de_marqueur_different_reste_ecarte(self) -> None:
        """Le critère porte sur les délimiteurs `[[...]]`, pas sur le
        libellé français : reformuler un marqueur ne rouvre pas la faille."""
        texte = "[[PAGE 1 : rien à extraire]]\n\n[[PAGE 2 : rien à extraire]]\n\n[[PAGE 3 : x]]"
        assert len(texte) > 50

        a = _file("a.pdf", texte, FileStatus.LOW_TEXT)
        b = _file("b.pdf", texte, FileStatus.LOW_TEXT)

        detect_duplicates([a, b])

        assert "duplicate_of" not in b.extra_metadata

    def test_ocr_reussi_reste_dedoublonne(self) -> None:
        """Contre-épreuve : le texte reconnu par OCR suit son marqueur et
        compte comme du contenu — deux scans réellement identiques dont
        l'OCR a réussi restent détectés."""
        texte = (
            "[[PAGE 1 — texte OCR (tesseract, fra)]]\n"
            "Contrat de travail a duree indeterminee entre la societe et le salarie."
        )
        a = _file("dossier1/contrat.pdf", texte, FileStatus.READY)
        b = _file("dossier2/contrat.pdf", texte, FileStatus.READY)

        detect_duplicates([a, b])

        assert b.extra_metadata["duplicate_of"] == "dossier1/contrat.pdf"

    def test_vrai_titre_markdown_reste_du_contenu(self) -> None:
        """Seuls les titres purement numérotés (`## Diapo 1`) sont de
        l'échafaudage ; un vrai titre de document porte des mots."""
        texte = "# Rapport annuel de la direction financiere\n## Synthese des resultats 2024"
        a = _file("a.md", texte)
        b = _file("b.md", texte)

        detect_duplicates([a, b])

        assert b.extra_metadata["duplicate_of"] == "a.md"
