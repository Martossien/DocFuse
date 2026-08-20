#!/usr/bin/env python3
"""Script de recette DocFuse (CdC §21.4).

Lance une série de tests fonctionnels sur le jeu de fichiers de test anonymisé.
Vérifie que les cas d'acceptation du CdC §19 fonctionnent correctement.

Usage:
    python tests/recette/run_recette.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

RECETTE_DIR = Path(__file__).resolve().parent
DOSSIER_MIXTE = RECETTE_DIR / "dossier_mixte"
DOSSIER_BLOCAGE = RECETTE_DIR / "dossier_blocage"
DOSSIER_IMAGES = RECETTE_DIR / "dossier_images"

DOSSIER_MIXTE, DOSSIER_BLOCAGE, DOSSIER_IMAGES = (
    RECETTE_DIR / "dossier_mixte",
    RECETTE_DIR / "dossier_blocage",
    RECETTE_DIR / "dossier_images",
)

# ──────────────────────────────────────────────────────────────────────────────
# Utilitaires
# ──────────────────────────────────────────────────────────────────────────────


class Result:
    """Résultat d'un test de recette."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.passed = False
        self.message = ""

    def ok(self, msg: str = "") -> None:
        self.passed = True
        self.message = msg

    def fail(self, msg: str) -> None:
        self.passed = False
        self.message = msg


def run_cli(args: list[str]) -> tuple[int, str, str]:
    """Lance la CLI et retourne (code retour, stdout, stderr)."""
    cmd = [sys.executable, "-m", "docfuse"] + args
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return proc.returncode, proc.stdout, proc.stderr


# ──────────────────────────────────────────────────────────────────────────────
# Tests de recette (CdC §19)
# ──────────────────────────────────────────────────────────────────────────────


def test_dossier_mixte_md() -> Result:
    """§19.2 — Dossier mixte → un MD unique, chaque source identifiable."""
    r = Result("Dossier mixte → Markdown")
    output = DOSSIER_MIXTE / "CorpusOne_output" / "corpus.md"
    if output.exists():
        output.unlink()
    code, out, err = run_cli(
        [
            "-i",
            str(DOSSIER_MIXTE),
            "-o",
            str(output),
            "--yes",
        ]
    )
    if code != 0:
        r.fail(f"Code {code}: {err}")
        return r
    if not output.exists():
        r.fail("Corpus non généré")
        return r
    content = output.read_text(encoding="utf-8")
    if "SOURCE:" not in content:
        r.fail("En-tête SOURCE manquant")
        return r
    r.ok("Corpus MD généré avec en-têtes SOURCE")
    return r


def test_dossier_mixte_pdf() -> Result:
    """§19.2 — Même dossier → un PDF unique, texte sélectionnable."""
    r = Result("Dossier mixte → PDF")
    output = DOSSIER_MIXTE / "CorpusOne_output" / "corpus.pdf"
    if output.exists():
        output.unlink()
    code, out, err = run_cli(
        [
            "-i",
            str(DOSSIER_MIXTE),
            "-o",
            str(output),
            "--format",
            "pdf",
            "--yes",
        ]
    )
    if code != 0:
        r.fail(f"Code {code}: {err}")
        return r
    if not output.exists():
        r.fail("PDF non généré")
        return r
    if output.stat().st_size < 100:
        r.fail("PDF trop petit (vide ?)")
        return r
    r.ok("PDF généré")
    return r


def test_blocage_context() -> Result:
    """§19.2 — TXT dont le compteur +15% > plafond → pas de corpus, code 2."""
    r = Result("Blocage par plafond")
    output = DOSSIER_BLOCAGE / "corpus.md"
    if output.exists():
        output.unlink()
    code, out, err = run_cli(
        [
            "-i",
            str(DOSSIER_BLOCAGE),
            "-o",
            str(output),
            "--context",
            "100",
            "--yes",
        ]
    )
    if code != 2:
        r.fail(f"Code attendu: 2, obtenu: {code}")
        return r
    if output.exists():
        r.fail("Corpus ne devrait pas être généré")
        return r
    r.ok("Blocage correct (code 2)")
    return r


def test_fichier_exe_ignore() -> Result:
    """§19.2 — Fichier .exe dans le dossier → ignoré, présent au rapport."""
    r = Result("Fichier .exe ignoré")
    output = DOSSIER_MIXTE / "CorpusOne_output" / "corpus_test.md"
    code, out, err = run_cli(
        [
            "-i",
            str(DOSSIER_MIXTE),
            "-o",
            str(output),
            "--dry-run",
            "--yes",
        ]
    )
    report = DOSSIER_MIXTE / "CorpusOne_output" / "corpus_test_rapport.json"
    if not report.exists():
        r.fail("Rapport non généré")
        return r
    import json

    data = json.loads(report.read_text(encoding="utf-8"))
    ignored_names = [i["path"].split("/")[-1].split("\\")[-1] for i in data.get("ignored", [])]
    if "app.exe" not in ignored_names:
        r.fail(f"app.exe non listé dans ignorés: {ignored_names}")
        return r
    r.ok("app.exe ignoré et présent au rapport")
    return r


def test_lock_file_ignore() -> Result:
    """§19.2 — ~$w.docx → ignoré."""
    r = Result("Fichier verrou ~$ ignoré")
    output = DOSSIER_MIXTE / "CorpusOne_output" / "corpus_lock.md"
    code, out, err = run_cli(
        [
            "-i",
            str(DOSSIER_MIXTE),
            "-o",
            str(output),
            "--dry-run",
            "--yes",
        ]
    )
    report = DOSSIER_MIXTE / "CorpusOne_output" / "corpus_lock_rapport.json"
    if not report.exists():
        r.fail("Rapport non généré")
        return r
    import json

    data = json.loads(report.read_text(encoding="utf-8"))
    ignored_names = [i["path"].split("/")[-1].split("\\")[-1] for i in data.get("ignored", [])]
    if "~$locked.docx" not in ignored_names:
        r.fail(f"~$locked.docx non listé: {ignored_names}")
        return r
    r.ok("~$locked.docx ignoré")
    return r


def test_dry_run() -> Result:
    """§19.2 — CLI --dry-run → pas de corpus, rapport stats."""
    r = Result("Dry-run avec rapport")
    output = DOSSIER_MIXTE / "CorpusOne_output" / "corpus_dry.md"
    code, out, err = run_cli(
        [
            "-i",
            str(DOSSIER_MIXTE),
            "-o",
            str(output),
            "--dry-run",
        ]
    )
    if output.exists():
        r.fail("Corpus ne devrait pas exister en dry-run")
        return r
    report_md = DOSSIER_MIXTE / "CorpusOne_output" / "corpus_dry_rapport.md"
    if not report_md.exists():
        r.fail("Rapport MD non généré en dry-run")
        return r
    r.ok("Dry-run: pas de corpus, rapport généré")
    return r


def test_list_formats() -> Result:
    """§6.3 — --list-formats affiche les extensions."""
    r = Result("--list-formats")
    code, out, err = run_cli(["--list-formats"])
    if code != 0:
        r.fail(f"Code {code}")
        return r
    if ".pdf" not in out or ".docx" not in out:
        r.fail("Extensions manquantes")
        return r
    r.ok(f"Formats listés ({out.count('.')}) extensions)")
    return r


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main() -> int:
    print("=" * 60)
    print("Script de recette DocFuse / CorpusOne (CdC §21.4)")
    print("=" * 60)
    print()

    tests = [
        test_dossier_mixte_md,
        test_dossier_mixte_pdf,
        test_blocage_context,
        test_fichier_exe_ignore,
        test_lock_file_ignore,
        test_dry_run,
        test_list_formats,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        result = test_fn()
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"  {status} — {result.name}")
        if result.message:
            print(f"         {result.message}")
        if result.passed:
            passed += 1
        else:
            failed += 1
        print()

    print("=" * 60)
    print(f"Résultat: {passed} réussis, {failed} échoués sur {len(tests)} tests")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
