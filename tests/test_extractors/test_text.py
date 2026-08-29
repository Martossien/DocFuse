"""Tests de l'extracteur texte (.txt, .text, .log, fichiers de développement).

CdC §7.2 — Encodage : BOM, UTF-8, cp1252, latin-1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docfuse.constants import CODE_EXTENSIONS
from docfuse.core.registry import get_extractor_for
from docfuse.extractors.text import TextExtractor, decode_text, detect_encoding, repair_mojibake
from docfuse.models.file_status import FileStatus


class TestTextExtractor:
    """Tests de l'extracteur texte."""

    def test_utf8_text(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("Bonjour le monde.\nLigne 2.\n", encoding="utf-8")

        result = TextExtractor.extract(f, "test.txt")
        assert result.status is FileStatus.READY
        assert "Bonjour le monde" in result.text
        assert result.encoding == "utf-8"

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")

        result = TextExtractor.extract(f, "empty.txt")
        assert result.status is FileStatus.READY
        assert result.text == ""
        assert result.encoding == "utf-8"

    def test_cp1252_text(self, tmp_path: Path) -> None:
        f = tmp_path / "cp1252.txt"
        # Écrire un texte plus long en cp1252 pour que la détection soit fiable
        text = "Café réserver hôtel réunion"
        f.write_bytes(text.encode("cp1252"))

        result = TextExtractor.extract(f, "cp1252.txt")
        assert result.status is FileStatus.READY
        assert "Caf" in result.text

    def test_bom_utf8(self, tmp_path: Path) -> None:
        f = tmp_path / "bom.txt"
        f.write_bytes(b"\xef\xbb\xbfTexte avec BOM")

        result = TextExtractor.extract(f, "bom.txt")
        assert result.status is FileStatus.READY
        assert "Texte avec BOM" in result.text
        assert "utf-8" in (result.encoding or "")

    def test_accepts(self) -> None:
        assert TextExtractor.accepts(Path("test.txt")) is True
        assert TextExtractor.accepts(Path("test.log")) is True
        assert TextExtractor.accepts(Path("test.text")) is True
        assert TextExtractor.accepts(Path("test.pdf")) is False

    def test_safe_extract_no_crash(self, tmp_path: Path) -> None:
        """safe_extract ne doit JAMAIS crasher, même si le fichier n'existe pas."""
        f = tmp_path / "nonexistent.txt"
        result = TextExtractor.safe_extract(f, "nonexistent.txt")
        assert result.status is FileStatus.ERROR


class TestCodeExtensions:
    """Fichiers de développement (.py, .vba, .rs, ...) traités comme texte brut."""

    @pytest.mark.parametrize("ext", sorted(CODE_EXTENSIONS))
    def test_dispatches_to_text_extractor(self, ext: str) -> None:
        assert get_extractor_for(Path(f"fichier{ext}")) is TextExtractor

    def test_python_file_extracted_as_ready(self, tmp_path: Path) -> None:
        f = tmp_path / "script.py"
        f.write_text("def main() -> None:\n    print('hello')\n", encoding="utf-8")

        result = TextExtractor.extract(f, "script.py")
        assert result.status is FileStatus.READY
        assert "def main" in result.text
        assert result.file_type == "py"

    def test_vba_file_extracted_as_ready(self, tmp_path: Path) -> None:
        f = tmp_path / "Module1.vba"
        f.write_text('Sub Test()\n    MsgBox "Hello"\nEnd Sub\n', encoding="utf-8")

        result = TextExtractor.extract(f, "Module1.vba")
        assert result.status is FileStatus.READY
        assert "MsgBox" in result.text

    def test_dotfile_without_extension_is_not_matched(self) -> None:
        """Limite connue : dispatch par suffixe, pas par nom de fichier complet."""
        assert get_extractor_for(Path(".gitignore")) is None
        assert get_extractor_for(Path("Dockerfile")) is None


class TestMojibakeRepair:
    """D-093 : réparation du mojibake (ftfy)."""

    def test_repair_mojibake_fixes_known_pattern(self) -> None:
        # Schéma de corruption reproductible : UTF-8 encodé, mal décodé en
        # latin-1, ré-encodé en UTF-8 — même mécanisme que le double
        # encodage trouvé en conditions réelles (D-092/D-093).
        original = "café réservé à l'hôtel"
        corrupted = original.encode("utf-8").decode("latin-1")
        assert repair_mojibake(corrupted) == original

    def test_repair_mojibake_leaves_clean_text_untouched(self) -> None:
        clean = "Texte propre, sans aucune corruption."
        assert repair_mojibake(clean) == clean

    def test_repair_mojibake_does_not_uncurl_legitimate_smart_quotes(self) -> None:
        """Non-régression (trouvé en conditions réelles sur ~/Téléchargements,
        145 faux positifs) : la config ftfy par défaut convertit les
        guillemets typographiques légitimes (’) en guillemets ASCII (') —
        ce n'est pas une réparation de mojibake, c'est une altération de
        contenu correct. `uncurl_quotes=False` doit empêcher ça."""
        text = "L’API v2 pour un usage optimisé, c’est prêt."
        assert repair_mojibake(text) == text

    def test_repair_mojibake_does_not_convert_ligatures(self) -> None:
        text = "un fichier ﬁnal, très eﬃcace"  # ligatures ﬁ/ﬃ (U+FB01/U+FB03)
        assert repair_mojibake(text) == text

    def test_repair_mojibake_does_not_normalize_crlf(self) -> None:
        """Non-régression (trouvé en conditions réelles, ~75 faux positifs
        restants après le premier correctif) : `fix_line_breaks` convertit
        CRLF en LF sur tout fichier texte, sans lien avec le mojibake —
        la gestion des fins de ligne est un choix du corpus généré, pas de
        l'extraction."""
        text = "Ligne 1\r\nLigne 2\r\n"
        assert repair_mojibake(text) == text

    def test_repair_mojibake_does_not_normalize_fullwidth_punctuation(self) -> None:
        """Cas réel trouvé (JSON avec négatifs de prompt en chinois) :
        `fix_character_width` convertissait la ponctuation chinoise pleine
        chasse (`，`), correcte pour cette langue, en virgule ASCII — une
        altération de contenu correctement encodé dans sa propre langue."""
        text = "色调艳丽，过曝，静态"
        assert repair_mojibake(text) == text

    def test_repair_mojibake_does_not_collapse_fullwidth_space(self) -> None:
        """Cas réel trouvé (bundle JS minifié) : `fix_character_width`
        collapsait `\\u3000` (espace idéographique pleine chasse, distincte
        d'une espace normale) en simple espace ASCII — perte d'information
        dans du code source dont l'exactitude octet-par-octet compte.
        `\\u2000`/`\\u2001` ne sont volontairement pas testés ici : Unicode
        les définit comme des singletons canoniquement équivalents à
        `\\u2002`/`\\u2003` — leur fusion par la normalisation NFC
        (conservée, volontairement) est standard, pas une perte de sens."""
        text = "avant　apres"
        assert repair_mojibake(text) == text

    def test_repair_mojibake_fixes_stray_cp1252_bytes_in_utf8(self) -> None:
        """Cas réel trouvé (glpi.csv) : un octet Windows-1252 égaré dans un
        texte par ailleurs UTF-8 (ex: \\x92 pour une apostrophe
        typographique) doit être reconnu et corrigé — contrairement à
        uncurl_quotes, ceci est une vraie réparation de corruption, pas une
        préférence cosmétique."""
        corrupted = "D\x92avance merci"
        assert repair_mojibake(corrupted) == "D’avance merci"

    def test_decode_text_reports_no_change_on_clean_utf8(self) -> None:
        raw = b"Texte parfaitement propre."
        encoding, text, changed = decode_text(raw)
        assert encoding == "utf-8"
        assert text == "Texte parfaitement propre."
        assert changed is False

    def test_decode_text_reports_change_on_mojibake(self) -> None:
        original = "café réservé à l'hôtel"
        corrupted_bytes = original.encode("utf-8").decode("latin-1").encode("utf-8")
        encoding, text, changed = decode_text(corrupted_bytes)
        assert changed is True
        assert text == original

    def test_extractor_flags_repaired_text_in_extra_metadata(self, tmp_path: Path) -> None:
        original = "café réservé à l'hôtel, événement à Orléans"
        corrupted_bytes = original.encode("utf-8").decode("latin-1").encode("utf-8")
        f = tmp_path / "mojibake.txt"
        f.write_bytes(corrupted_bytes)

        result = TextExtractor.extract(f, "mojibake.txt")
        assert result.status is FileStatus.READY
        assert result.text == original
        assert "mojibake_repaired" in result.extra_metadata


class TestEncodingPlausibility:
    """D-093 : un décodage cp1252 plausible mais faux doit retomber sur
    charset-normalizer plutôt que d'être accepté aveuglément."""

    def test_legit_cp1252_text_still_accepted(self) -> None:
        """Non-régression : un texte cp1252 plausible (peu/pas de
        caractères de contrôle) reste accepté tel quel."""
        text = "Café réservé, hôtel, réunion".encode("cp1252")
        encoding, _ = detect_encoding(text)
        assert encoding == "cp1252"

    def test_binary_garbage_does_not_stay_on_cp1252(self) -> None:
        # Octets de contrôle en rafale : cp1252 décode sans erreur mais le
        # résultat n'est pas un texte plausible — doit continuer vers
        # charset-normalizer/latin-1, pas rester bloqué sur cp1252.
        garbage = bytes(range(1, 32)) * 20
        encoding, _ = detect_encoding(garbage)
        assert encoding != "cp1252"
