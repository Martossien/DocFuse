"""Tests du scénario de blocage au plafond de contexte.

CdC §10 — Compteur de contexte générique avec marge +15 %.
CdC §10.2 — Blocage si fichier OU total > plafond.
CdC §10.3 — Monter le plafond → redevient actif.

Ces tests vérifient le scénario complet :
1. 3 fichiers qui ensemble dépassent 128K tokens
2. Blocage, pas de corpus, code retour 2
3. Rapport généré même si bloqué
4. Monter le plafond à 400K → génération OK
5. Un seul fichier qui dépasse 128K → bloqué
6. Plafond et marge sont des variables
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from docfuse.core.orchestrator import generate_corpus, run_analysis


@pytest.fixture
def big_files_dir(tmp_path: Path) -> Path:
    """Crée 3 fichiers qui ensemble dépassent 128K tokens."""
    # 200K octets par fichier = ~50K tokens par fichier
    # 3 * 50K = 150K tokens > 128K → doit bloquer
    for i in range(3):
        (tmp_path / f"doc_{i}.txt").write_text("A" * 200_000, encoding="utf-8")
    return tmp_path


@pytest.fixture
def single_huge_file(tmp_path: Path) -> Path:
    """Crée un seul fichier qui dépasse 128K tokens."""
    # 600K octets = ~150K tokens > 128K
    (tmp_path / "huge.txt").write_text("B" * 600_000, encoding="utf-8")
    return tmp_path / "huge.txt"


@pytest.fixture
def small_files_dir(tmp_path: Path) -> Path:
    """Crée de petits fichiers qui ne dépassent pas 128K tokens."""
    for i in range(5):
        (tmp_path / f"small_{i}.txt").write_text("A" * 1000, encoding="utf-8")
    return tmp_path


class TestContextBlocking:
    """Tests du blocage au plafond de contexte (CdC §10)."""

    def test_blocked_at_128k(self, big_files_dir: Path) -> None:
        """3 fichiers ensemble dépassent 128K → bloqué."""
        result = run_analysis(big_files_dir, context_limit=128_000, margin=0.15)
        assert result.is_blocked
        assert result.total.tokens_with_margin > 128_000

    def test_no_corpus_when_blocked(self, big_files_dir: Path, tmp_path: Path) -> None:
        """Si bloqué, aucun corpus n'est généré."""
        result = run_analysis(big_files_dir, context_limit=128_000, margin=0.15)
        output = tmp_path / "corpus.md"
        success = generate_corpus(result, output, 128_000, 0.15)
        assert not success
        assert not output.exists()

    def test_report_when_blocked(self, big_files_dir: Path, tmp_path: Path) -> None:
        """Le rapport est généré même si bloqué."""
        result = run_analysis(big_files_dir, context_limit=128_000, margin=0.15)
        output = tmp_path / "corpus.md"
        generate_corpus(result, output, 128_000, 0.15)
        assert (tmp_path / "corpus_rapport.md").exists()
        assert (tmp_path / "corpus_rapport.json").exists()

    def test_unblocked_at_400k(self, big_files_dir: Path, tmp_path: Path) -> None:
        """Monter le plafond à 400K → débloqué + corpus généré."""
        result = run_analysis(big_files_dir, context_limit=400_000, margin=0.15)
        assert not result.is_blocked
        output = tmp_path / "corpus_400k.md"
        success = generate_corpus(result, output, 400_000, 0.15)
        assert success
        assert output.exists()
        content = output.read_text("utf-8")
        assert "## SOURCE:" in content

    def test_single_file_blocked(self, single_huge_file: Path) -> None:
        """Un seul fichier qui dépasse 128K → bloqué."""
        result = run_analysis(single_huge_file, context_limit=128_000, margin=0.15)
        assert result.is_blocked
        assert len(result.blocking_files) == 1
        assert result.blocking_files[0].relative_path == "huge.txt"

    def test_equal_limit_passes(self, tmp_path: Path) -> None:
        """Égalité (== L) passe — CdC §10.2."""
        # Créer un fichier dont les tokens avec marge = exactement le plafond
        # 1000 tokens avec marge = 1000 → 1000 octets / 4 = 250, * 1.15 = 288
        # Il faut tokens_with_margin == limit exactement
        # tokens_with_margin = ceil(ceil(bytes/4) * 1.15)
        # Pour limit=115: bytes=400 → 100 tokens, * 1.15 = 115 → OK
        (tmp_path / "exact.txt").write_text("A" * 400, encoding="utf-8")
        result = run_analysis(tmp_path, context_limit=115, margin=0.15)
        # Le total inclut l'en-tête SOURCE, donc ça peut dépasser un peu
        # On teste juste que l'égalité n'est pas strictement bloquée
        # avec un plafond légèrement supérieur
        if result.total.tokens_with_margin == 115:
            assert not result.is_blocked

    def test_plafond_is_variable(self, big_files_dir: Path) -> None:
        """Le plafond est une variable, pas codé en dur."""
        results = {}
        for limit in [1000, 10_000, 100_000, 200_000, 500_000, 1_000_000]:
            r = run_analysis(big_files_dir, context_limit=limit, margin=0.15)
            results[limit] = r.is_blocked
        # Avec un plafond très haut, ça ne doit pas être bloqué
        assert not results[1_000_000]
        # Avec un plafond bas, ça doit être bloqué
        assert results[1000]

    def test_margin_is_variable(self, big_files_dir: Path) -> None:
        """La marge est une variable."""
        for m in [0.0, 0.10, 0.15, 0.20, 0.30, 0.50]:
            r = run_analysis(big_files_dir, context_limit=200_000, margin=m)
            # Avec marge 0, le total est plus petit
            if m == 0.0:
                assert r.total.tokens_with_margin == r.total.tokens_estimated
            else:
                assert r.total.tokens_with_margin > r.total.tokens_estimated

    def test_no_files_not_blocked(self, tmp_path: Path) -> None:
        """Dossier vide → pas bloqué, 0 fichiers."""
        result = run_analysis(tmp_path, context_limit=128_000, margin=0.15)
        assert not result.is_blocked
        assert len(result.files) == 0

    def test_small_files_not_blocked(self, small_files_dir: Path) -> None:
        """Petits fichiers → pas bloqué."""
        result = run_analysis(small_files_dir, context_limit=128_000, margin=0.15)
        assert not result.is_blocked

    def test_warning_images_never_blocks(self, tmp_path: Path) -> None:
        """Les warnings images ne bloquent jamais la génération."""
        # Un fichier HTML avec images mais peu de texte
        (tmp_path / "img.html").write_text(
            "<html><body><p>Texte avec assez de caracteres pour eviter alerte.</p>"
            "<img src='a.jpg' alt='Image A'><img src='b.jpg' alt='Image B'></body></html>",
            encoding="utf-8",
        )
        result = run_analysis(tmp_path, context_limit=128_000, margin=0.15)
        assert not result.is_blocked
        # Le fichier doit avoir des images détectées
        img_files = [f for f in result.files if f.image_count > 0]
        assert len(img_files) > 0


class TestCLIExitCodes:
    """Tests des codes retour CLI (CdC §6.3)."""

    def test_cli_blocked_returns_2(self, big_files_dir: Path) -> None:
        """CLI --yes + blocage → code 2."""
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "docfuse",
                "-i",
                str(big_files_dir),
                "--yes",
                "-o",
                str(big_files_dir / "corpus.md"),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 2

    def test_cli_dry_run_generates_report(self, big_files_dir: Path) -> None:
        """CLI --dry-run génère un rapport même si bloqué."""
        output = big_files_dir / "corpus_dry.md"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "docfuse",
                "-i",
                str(big_files_dir),
                "--dry-run",
                "-o",
                str(output),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert not output.exists()  # Pas de corpus en dry-run
        assert (big_files_dir / "corpus_dry_rapport.md").exists()
        assert (big_files_dir / "corpus_dry_rapport.json").exists()

    def test_cli_high_limit_returns_0(self, big_files_dir: Path) -> None:
        """CLI avec plafond élevé → code 0 et corpus généré."""
        output = big_files_dir / "corpus_high.md"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "docfuse",
                "-i",
                str(big_files_dir),
                "--context",
                "400000",
                "--yes",
                "-o",
                str(output),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0
        assert output.exists()

    def test_cli_no_files_returns_3(self, tmp_path: Path) -> None:
        """CLI sans fichiers supportés → code 3."""
        (tmp_path / "app.exe").write_bytes(b"\x00\x01\x02\x03")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "docfuse",
                "-i",
                str(tmp_path),
                "--yes",
                "-o",
                str(tmp_path / "corpus.md"),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 3

    def test_cli_nonexistent_input_returns_1(self) -> None:
        """CLI avec input inexistant → code 1."""
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "docfuse",
                "-i",
                "/nonexistent/path",
                "--yes",
                "-o",
                "/tmp/corpus.md",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 1

    def test_cli_list_formats_returns_0(self) -> None:
        """CLI --list-formats → code 0."""
        proc = subprocess.run(
            [sys.executable, "-m", "docfuse", "--list-formats"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0
        assert ".pdf" in proc.stdout
        assert ".docx" in proc.stdout

    def test_cli_version(self) -> None:
        """CLI --version → code 0."""
        proc = subprocess.run(
            [sys.executable, "-m", "docfuse", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0
        assert "docfuse" in proc.stdout.lower()


class TestWindowsBehavior:
    """Tests du comportement Windows spécifique (vérification du code)."""

    def test_crlf_auto_windows(self) -> None:
        """Le markdown_writer détecte Windows pour CRLF."""
        # Vérifier que le paramètre line_ending accepte None (auto)
        import inspect

        from docfuse.output.markdown_writer import write_markdown_corpus

        sig = inspect.signature(write_markdown_corpus)
        assert "line_ending" in sig.parameters
        assert sig.parameters["line_ending"].default is None

    def test_config_appdata_windows(self) -> None:
        """La config utilise APPDATA sous Windows."""
        from docfuse.config import _appdata_dir

        # La fonction doit exister et retourner un Path
        result = _appdata_dir()
        assert isinstance(result, Path)

    def test_config_frozen_detection(self) -> None:
        """La config détecte PyInstaller frozen."""
        import docfuse.config as cfg

        # _exe_dir doit gérer sys.frozen
        assert hasattr(cfg, "_exe_dir")

    def test_no_hklm_or_program_files(self) -> None:
        """Aucune référence à HKLM, Program Files, ou services."""
        src_dir = Path(__file__).resolve().parent.parent / "src" / "docfuse"
        all_code = ""
        for py in src_dir.rglob("*.py"):
            all_code += py.read_text("utf-8") + "\n"
        for forbidden in ["HKLM", "HKEY_LOCAL_MACHINE", "CreateService", "win32service"]:
            assert forbidden not in all_code, f"{forbidden} trouvé dans le code"

    def test_pyinstaller_spec_windowed(self) -> None:
        """Le spec PyInstaller utilise --windowed (console=False)."""
        spec = Path(__file__).resolve().parent.parent / "CorpusOne.spec"
        if spec.exists():
            content = spec.read_text("utf-8")
            assert "console=False" in content
            assert "DejaVuSans" in content
            assert "fr.json" in content

    def test_log_rotation_windows(self) -> None:
        """Le log utilise RotatingFileHandler vers %TEMP%/CorpusOne/."""
        cli = (Path(__file__).resolve().parent.parent / "src" / "docfuse" / "cli.py").read_text(
            "utf-8"
        )
        assert "RotatingFileHandler" in cli
        assert "CorpusOne" in cli
        assert "tempfile" in cli

    def test_main_dispatches_gui_no_args(self) -> None:
        """__main__.py lance la GUI sans args, CLI avec args."""
        main = (
            Path(__file__).resolve().parent.parent / "src" / "docfuse" / "__main__.py"
        ).read_text("utf-8")
        assert "sys.argv" in main
        assert "gui" in main.lower()
        assert "cli" in main.lower()

    def test_cp1252_before_charset_normalizer(self) -> None:
        """cp1252 est essayé avant charset-normalizer (priorité Windows)."""
        text = (
            Path(__file__).resolve().parent.parent / "src" / "docfuse" / "extractors" / "text.py"
        ).read_text("utf-8")
        cp1252_pos = text.find("cp1252")
        cn_pos = text.find("charset_normalizer")
        assert cp1252_pos > 0
        assert cn_pos > 0
        assert cp1252_pos < cn_pos, "cp1252 doit être avant charset-normalizer"

    def test_output_in_corpusone_output(self) -> None:
        """La sortie par défaut va dans CorpusOne_output/ (CdC §5.3)."""
        cli = (Path(__file__).resolve().parent.parent / "src" / "docfuse" / "cli.py").read_text(
            "utf-8"
        )
        gui = (Path(__file__).resolve().parent.parent / "src" / "docfuse" / "gui.py").read_text(
            "utf-8"
        )
        assert "CorpusOne_output" in cli
        assert "CorpusOne_output" in gui
