"""Tests du service de décodage `core/encoding.py`.

D-107 : le seuil `ENCODING_MAX_UTF8_REPLACEMENT_RATIO` faisait croître le
budget d'octets illisibles avec la taille du fichier, alors que D-097 le
justifiait par « une seule séquence multi-octets tronquée ». Un export ERP
français en cp1252, majoritairement ASCII, était déclaré UTF-8 et perdait
tous ses accents en silence.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.core.encoding import (
    decode_text,
    decode_text_with_note,
    detect_encoding,
    replacement_metadata,
)
from docfuse.core.notes import ordered_notes
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

LIGNE_ERP = "Salarie : Mme \xc9lodie Lef\xe8vre, n\xe9e \xe0 N\xeemes - dossier m\xe9dical"
ACCENTS_PAR_LIGNE = sum(1 for c in LIGNE_ERP if ord(c) > 127)
LIGNE_ASCII = "ligne de journal purement ascii, montant 1234.56 eur\n"


def _export_erp(nb_ascii: int, nb_accents: int) -> bytes:
    """Export cp1252 de ~`nb_ascii` caractères ASCII et `nb_accents` accents."""
    nb_lignes = max(1, nb_accents // ACCENTS_PAR_LIGNE)
    bourrage = LIGNE_ASCII * (nb_ascii // len(LIGNE_ASCII))
    return (bourrage + "\n".join([LIGNE_ERP] * nb_lignes) + "\n").encode("cp1252")


class TestUtf8TronqueEnFin:
    """Le budget d'octets illisibles ne doit pas dépendre de la taille."""

    def test_export_cp1252_majoritairement_ascii_reste_cp1252(self) -> None:
        """3 Mo d'ASCII + un millier d'accents = 0,035 % d'octets non-ASCII,
        sous l'ancien ratio de 0,1 % : le fichier sortait en `utf-8` avec
        1 050 U+FFFD, et le corpus affirmait `encodage: utf-8`."""
        brut = _export_erp(3_000_000, 1_050)

        assert detect_encoding(brut)[0] == "cp1252"

        encodage, texte, _repare = decode_text(brut)
        assert encodage == "cp1252"
        assert "�" not in texte
        assert "Mme \xc9lodie Lef\xe8vre, n\xe9e \xe0 N\xeemes" in texte

    def test_le_verdict_ne_depend_pas_de_la_taille(self) -> None:
        """1 000 caractères → cp1252 ; 10 000 → `utf-8` avant le correctif,
        pour exactement le même contenu accentué."""
        petit = _export_erp(1_000, ACCENTS_PAR_LIGNE)
        gros = _export_erp(10_000, ACCENTS_PAR_LIGNE)

        assert detect_encoding(petit)[0] == detect_encoding(gros)[0] == "cp1252"

    def test_sequence_tronquee_en_fin_reste_lisible_en_utf8(self) -> None:
        """Non-régression D-097 : le cas que le seuil protégeait
        légitimement. Un « é » coupé au bout du fichier ne doit pas faire
        basculer TOUT le texte en cp1252 (`cafÃ©…`)."""
        data = ("caf\xe9 r\xe9serv\xe9 \xe0 l'h\xf4tel " * 50).encode() + "\xe9".encode()[:1]

        encodage, texte, repare = decode_text(data)
        assert encodage == "utf-8"
        assert texte.startswith("caf\xe9 r\xe9serv\xe9 \xe0 l'h\xf4tel")
        assert repare is False

    def test_octet_invalide_ailleurs_qu_en_fin_nest_pas_de_l_utf8(self) -> None:
        """Un octet cp1252 égaré au milieu d'un fichier UTF-8 par ailleurs
        valide n'est pas une troncature de fin : le verdict `utf-8` serait
        une perte silencieuse."""
        data = "caf\xe9 ".encode() * 200 + b"\xe9 fin" + "caf\xe9".encode() * 200

        assert detect_encoding(data)[0] != "utf-8"

    def test_flux_reduit_a_une_sequence_incomplete(self) -> None:
        """Cas limite : rien à décoder du tout, on ne conclut pas `utf-8`."""
        assert detect_encoding(b"\xc3")[0] != "utf-8"


class TestNoteCaracteresPerdus:
    """Un remplacement qui subsiste doit se voir dans les métadonnées du
    document, pas seulement dans un journal (D-107)."""

    def test_note_absente_sur_un_fichier_propre(self) -> None:
        assert replacement_metadata("Texte propre, sans souci.") == {}
        assert decode_text_with_note(b"Texte propre, sans souci.")[2] == {}

    def test_note_presente_et_chiffree_quand_un_caractere_est_perdu(self) -> None:
        data = ("caf\xe9 r\xe9serv\xe9 \xe0 l'h\xf4tel " * 50).encode() + "\xe9".encode()[:1]

        encodage, texte, meta = decode_text_with_note(data)
        assert encodage == "utf-8"
        assert texte.count("�") == 1
        assert "1" in meta["encoding_replacements"]

    def test_la_note_remonte_dans_l_en_tete_du_corpus(self) -> None:
        """`core/notes.py` la publie : l'affirmation `encodage: utf-8`
        n'est plus seule face à un texte amputé."""
        data = ("caf\xe9 r\xe9serv\xe9 \xe0 l'h\xf4tel " * 50).encode() + "\xe9".encode()[:1]
        encodage, texte, meta = decode_text_with_note(data)
        fichier = ExtractedFile(
            path=Path("journal.txt"),
            relative_path="journal.txt",
            extension="txt",
            file_type="txt",
            size_bytes=len(data),
            text=texte,
            status=FileStatus.READY,
            encoding=encodage,
            extra_metadata=dict(meta),
        )

        notes = ordered_notes(fichier)
        assert any("encodage_caracteres_perdus" in note for note in notes)
