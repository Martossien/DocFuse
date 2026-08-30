"""Nom d'application paramétrable et dérivés (D-102)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from docfuse import branding
from docfuse.branding import DEFAULT_APP_NAME, LEGACY_APP_NAME, resolve_app_name

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "docfuse"


class TestResolveAppName:
    def test_default_when_unset_or_blank(self) -> None:
        assert resolve_app_name(None) == DEFAULT_APP_NAME
        assert resolve_app_name("") == DEFAULT_APP_NAME
        assert resolve_app_name("   ") == DEFAULT_APP_NAME

    def test_valid_names_are_kept_stripped(self) -> None:
        assert resolve_app_name("MonOutil") == "MonOutil"
        assert resolve_app_name("  Doc-IA_v2.0 ") == "Doc-IA_v2.0"

    def test_unsafe_names_fall_back(self) -> None:
        for bad in ("a/b", "a\\b", "..", ".hidden", "x" * 65, "nom avec espace", "é"):
            assert resolve_app_name(bad) == DEFAULT_APP_NAME, bad


class TestDerivedNames:
    def test_everything_derives_from_app_name(self) -> None:
        name = branding.APP_NAME
        assert f"{name}_output" == branding.OUTPUT_DIR_NAME
        assert f"{name}.json" == branding.CONFIG_FILENAME
        assert name == branding.APPDATA_DIR_NAME
        assert name == branding.LOG_DIR_NAME
        assert f"{name.lower()}.log" == branding.LOG_FILENAME
        assert f"{name}-OCR" == branding.OCR_VARIANT_NAME
        assert name == branding.PDF_AUTHOR

    def test_legacy_names_are_frozen(self) -> None:
        assert LEGACY_APP_NAME == "CorpusOne"
        assert branding.LEGACY_OUTPUT_DIR_NAME == "CorpusOne_output"
        assert branding.LEGACY_CONFIG_FILENAME == "CorpusOne.json"

    def test_env_override_in_fresh_interpreter(self) -> None:
        code = "from docfuse import branding; print(branding.APP_NAME, branding.OUTPUT_DIR_NAME)"
        out = subprocess.run(
            [sys.executable, "-c", code],
            env={**_base_env(), "DOCFUSE_APP_NAME": "Marque"},
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        assert out == ["Marque", "Marque_output"]


class TestNoHardcodedLegacyName:
    def test_runtime_code_has_no_corpusone_literal(self) -> None:
        """Seul `branding.py` a le droit de connaître l'ancien nom (D-102)."""
        offenders: list[str] = []
        for py in SRC.rglob("*.py"):
            if py.name == "branding.py":
                continue
            for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
                if "CorpusOne" in line or "corpusone" in line:
                    offenders.append(f"{py.relative_to(ROOT)}:{lineno}: {line.strip()}")
        assert offenders == [], "\n".join(offenders)

    def test_i18n_catalogs_have_no_hardcoded_name(self) -> None:
        for lang in ("fr", "en"):
            text = (SRC / "i18n" / f"{lang}.json").read_text(encoding="utf-8")
            assert "CorpusOne" not in text, lang


def _base_env() -> dict[str, str]:
    import os

    env = {k: v for k, v in os.environ.items() if k != "DOCFUSE_APP_NAME"}
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return env
