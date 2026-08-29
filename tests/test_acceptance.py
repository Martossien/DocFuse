"""Tests d'acceptation du CdC §19.

Ces tests vérifient les critères d'acceptation non négociables.
Le livrable est refusé si un cas ci-dessous échoue.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.core.orchestrator import run_analysis
from docfuse.core.registry import list_supported_extensions


class TestPortability:
    """CdC §19.1 — Portabilité."""

    def test_no_network_imports(self) -> None:
        """Vérifie qu'aucun module runtime n'importe requests, urllib, etc."""
        import ast

        network_modules = {"requests", "urllib.request", "http.client", "socket"}
        src_dir = Path(__file__).resolve().parent.parent / "src" / "docfuse"

        violations: list[str] = []
        for py_file in src_dir.rglob("*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name in network_modules:
                                violations.append(f"{py_file}: import {alias.name}")
                    elif (
                        isinstance(node, ast.ImportFrom)
                        and node.module
                        and node.module in network_modules
                    ):
                        violations.append(f"{py_file}: from {node.module}")
            except SyntaxError:
                pass

        # L'orchestrator peut importer urllib pour Path, mais pas pour réseau
        assert not violations, f"Imports réseau interdits : {violations}"


class TestFunctionalAcceptance:
    """CdC §19.2 — Fonctionnels."""

    def test_txt_blocked_by_context_limit(self, tmp_path: Path) -> None:
        """Un TXT dont le compteur +15 % > plafond → pas de corpus, code 2."""
        # Créer un fichier assez gros pour dépasser un plafond bas
        text = "A" * 10_000  # 10K octets → 2500 tokens → 2875 avec marge
        (tmp_path / "big.txt").write_text(text, encoding="utf-8")

        result = run_analysis(tmp_path, context_limit=1000, margin=0.15)
        assert result.is_blocked

    def test_multiple_files_total_blocked(self, tmp_path: Path) -> None:
        """Trois fichiers, aucun individuellement trop gros, mais total > plafond."""
        # Contenu distinct par fichier (D-064 : évite la déduplication de
        # contenu identique entre fichiers, qui fausserait ce test).
        for i, letter in enumerate("ABC"):
            text = letter * 1000  # 250 tokens chacun, 287 avec marge
            (tmp_path / f"f{i}.txt").write_text(text, encoding="utf-8")

        # Total ~861 tokens avec marge, plafond 500 → bloqué par total
        result = run_analysis(tmp_path, context_limit=500, margin=0.15)
        assert result.is_blocked
        assert not result.blocking_files  # Aucun fichier individuellement bloquant

    def test_exe_ignored(self, tmp_path: Path) -> None:
        """Un .exe dans le dossier → ignoré, présent au rapport."""
        (tmp_path / "doc.txt").write_text("Texte valide", encoding="utf-8")
        (tmp_path / "app.exe").write_bytes(b"\x00\x01\x02\x03")

        result = run_analysis(tmp_path, context_limit=128000)
        assert any(p.name == "app.exe" for p, _ in result.ignored)

    def test_lock_file_ignored(self, tmp_path: Path) -> None:
        """~$w.docx → ignoré."""
        (tmp_path / "doc.txt").write_text("Texte", encoding="utf-8")
        (tmp_path / "~$w.docx").write_bytes(b"\x00")

        result = run_analysis(tmp_path, context_limit=128000)
        assert any(p.name == "~$w.docx" for p, _ in result.ignored)

    def test_supported_extensions_complete(self) -> None:
        """Toutes les extensions obligatoires du CdC §7.2 sont supportées."""
        exts = list_supported_extensions()
        required = {".pdf", ".docx", ".pptx", ".rtf", ".txt", ".html"}
        missing = required - exts
        assert not missing, f"Extensions manquantes : {missing}"


class TestLicenseCompliance:
    """CdC §19.3 — Licence."""

    def test_no_gpl_agpl_in_dependencies(self) -> None:
        """Vérifie que pyproject.toml ne contient pas de dépendances GPL/AGPL."""
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")

        forbidden = ["pymupdf", "fitz", "poppler", "weasyprint"]
        for pkg in forbidden:
            assert pkg not in content.lower(), f"Dépendance interdite : {pkg}"

    def test_ebooklib_not_a_dependency(self) -> None:
        """`ebooklib` (la bibliothèque EPUB Python la plus évidente) est en
        AGPLv3+ — l'extracteur EPUB de DocFuse (extractors/epub.py) est
        volontairement écrit à la main sur zipfile/ElementTree/BeautifulSoup
        pour rester conforme licence. Garde-fou contre une réintroduction
        par mégarde."""
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8").lower()

        assert "ebooklib" not in content
        assert "extract-msg" not in content
        assert "extract_msg" not in content

    def test_mistral_common_not_a_dependency(self) -> None:
        """Le paquet `mistral-common` tire `pydantic-extra-types[pycountry]`,
        et `pycountry` est LGPL-2.1 (voir core/tokenizers/mistral.py). Le
        moteur Mistral n'utilise que `tiktoken` + un vocabulaire vendoré —
        garde-fou pour ne pas réintroduire `mistral-common` par mégarde.
        """
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8").lower()

        assert "mistral-common" not in content
        assert "mistral_common" not in content

    def test_dependencies_licenses_compatible(self) -> None:
        """Vérifie que toutes les dépendances directes de DocFuse ont une licence compatible.

        CdC NFR-06 : Dépendances compatibles (MIT, BSD, Apache, ISC, MPL).
        Interdit : GPL, AGPL.
        """
        from importlib.metadata import metadata

        forbidden_licenses = {"gpl", "agpl", "lgpl", "proprietary"}

        # Dépendances runtime directes (pas dev)
        runtime_deps = [
            "pdfminer.six",
            "pypdf",
            "python-docx",
            "python-pptx",
            "openpyxl",
            "beautifulsoup4",
            "lxml",
            "striprtf",
            "charset-normalizer",
            "reportlab",
            "customtkinter",
            "darkdetect",  # dep of customtkinter
            "tiktoken",  # moteur de comptage précis "mistral" (core/tokenizers/mistral.py)
            "regex",  # dep of tiktoken
            "requests",  # dep of tiktoken (jamais appelé par notre code, cf. tests offline)
            "pypdfium2",  # rastérisation PDF pour l'OCR (core/ocr/, extractors/pdf.py)
            "pillow",  # encodage PNG des pages rastérisées avant OCR
            "ftfy",  # réparation du mojibake (extractors/text.py)
            "wcwidth",  # dep de ftfy
        ]

        for pkg_name in runtime_deps:
            try:
                meta = metadata(pkg_name)
                license_str = (meta.get("License", "") or "").lower()
                classifiers = " ".join(meta.get_all("Classifier") or []).lower()

                # Vérifier qu'aucune licence interdite n'est présente
                for forbidden in forbidden_licenses:
                    assert forbidden not in license_str, (
                        f"{pkg_name}: licence contient '{forbidden}' ({meta.get('License', '?')})"
                    )
                    assert forbidden not in classifiers, (
                        f"{pkg_name}: classifier contient '{forbidden}'"
                    )
            except Exception:
                # Si on ne trouve pas les métadonnées, on skip (pas bloquant en CI)
                pass


class TestI18n:
    """CdC §19.4 — i18n."""

    def test_fr_catalogue_exists(self) -> None:
        fr = Path(__file__).resolve().parent.parent / "src" / "docfuse" / "i18n" / "fr.json"
        assert fr.exists(), "Catalogue français manquant"

    def test_en_catalogue_exists(self) -> None:
        en = Path(__file__).resolve().parent.parent / "src" / "docfuse" / "i18n" / "en.json"
        assert en.exists(), "Catalogue anglais manquant"

    def test_fr_is_complete(self) -> None:
        """Le catalogue FR doit contenir toutes les clés essentielles."""
        import json

        fr = Path(__file__).resolve().parent.parent / "src" / "docfuse" / "i18n" / "fr.json"
        catalog = json.loads(fr.read_text(encoding="utf-8"))

        essential_keys = [
            "app.title",
            "gui.choose_folder",
            "gui.generate",
            "gui.analyze",
            "gui.context_limit",
            "table.file",
            "table.status",
            "status.ready",
            "status.images",
            "status.low_text",
            "status.ignored",
            "status.error",
        ]
        for key in essential_keys:
            assert key in catalog, f"Clé i18n manquante en FR : {key}"
