# -*- mode: python ; coding: utf-8 -*-
"""Spec file PyInstaller pour la variante DocFuse-OCR (avec Tesseract bundlé).

Décision produit (2026-08-29, voir docs/journal-decisions.md) : `DocFuse.exe`
reste identique en taille — Tesseract (binaire + tessdata, ~40-80 Mo) n'y est
PAS embarqué. Cette variante distincte, `DocFuse-OCR.exe`, l'embarque pour
un usage "zéro installation" de l'OCR des PDF scannés (core/ocr/). Le code
d'exécution est strictement identique entre les deux exe — seul cet
empaquetage diffère (voir `core/ocr/tesseract.py::_bundled_binary_path`, qui
attend le binaire sous `tesseract/tesseract.exe` et les modèles de langue
sous `tesseract/tessdata/*.traineddata`, exactement l'arborescence produite
ici).

Ce fichier duplique volontairement la majeure partie de `DocFuse.spec`
plutôt que de factoriser un module commun : les deux fichiers ne sont
buildés que sur un runner Windows (jamais testés localement dans cet
environnement de développement Linux) — minimiser les changements sur
`DocFuse.spec`, déjà vérifié en production, réduit le risque plutôt que
d'introduire une dépendance partagée non testée entre les deux builds.

Usage sur Windows (CI, voir .github/workflows/ci.yml::build-windows-ocr) :
    # 1. choco install tesseract -y  (fournit tesseract.exe + DLL + eng.traineddata)
    # 2. Télécharger fra.traineddata (tessdata_fast) dans le même tessdata/
    # 3. set TESSERACT_HOME=C:\\Program Files\\Tesseract-OCR  (optionnel, valeur par défaut)
    # 4. pyinstaller --noconfirm DocFuse-OCR.spec
"""

import os
import sys

# D-102 : même variable d'environnement que DocFuse.spec / docfuse.branding.
_APP_NAME = (os.environ.get("DOCFUSE_APP_NAME") or "DocFuse").strip() or "DocFuse"
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Chemin des assets (polices DejaVu)
assets_dir = Path(SPECPATH) / "src" / "docfuse" / "assets"
i18n_dir = Path(SPECPATH) / "src" / "docfuse" / "i18n"

# D-054 / D-055 : DLL runtime non couvertes par l'analyse statique (voir
# DocFuse.spec — même raison, même solution).
_python_dlls_dir = Path(getattr(sys, "base_prefix", sys.prefix)) / "DLLs"
_extra_binaries: list[tuple[str, str]] = []
if _python_dlls_dir.is_dir():
    for _dll_path in sorted(_python_dlls_dir.glob("*.dll")):
        _extra_binaries.append((str(_dll_path), "."))

# Tesseract : binaire + DLL (libtesseract, Leptonica, libpng, libjpeg, zlib…)
# + tessdata (fra + eng, tessdata_fast — voir le workflow CI qui les prépare
# dans TESSERACT_HOME avant l'appel à pyinstaller). Le nom exact des DLL
# varie selon la version de build de Tesseract : on embarque tout le
# contenu du dossier d'installation plutôt que de lister des noms figés.
_tesseract_home = Path(os.environ.get("TESSERACT_HOME", r"C:\Program Files\Tesseract-OCR"))
_tesseract_binaries: list[tuple[str, str]] = []
_tesseract_datas: list[tuple[str, str]] = []
if _tesseract_home.is_dir():
    for _exe_or_dll in sorted(_tesseract_home.glob("*.exe")) + sorted(
        _tesseract_home.glob("*.dll")
    ):
        _tesseract_binaries.append((str(_exe_or_dll), "tesseract"))
    _tessdata_dir = _tesseract_home / "tessdata"
    for _traineddata in sorted(_tessdata_dir.glob("*.traineddata")):
        _tesseract_datas.append((str(_traineddata), "tesseract/tessdata"))
else:
    raise FileNotFoundError(
        f"Tesseract introuvable dans TESSERACT_HOME={_tesseract_home} — "
        "installez-le avant de lancer ce build (voir docstring ci-dessus)."
    )
if not _tesseract_datas:
    raise FileNotFoundError(
        f"Aucun *.traineddata trouvé sous {_tesseract_home / 'tessdata'} — "
        "le build DocFuse-OCR sans modèle de langue n'aurait aucun intérêt."
    )

a = Analysis(
    [str(Path(SPECPATH) / "src" / "docfuse" / "__main__.py")],
    pathex=[str(Path(SPECPATH) / "src")],
    binaries=_extra_binaries + _tesseract_binaries,
    datas=[
        (str(assets_dir / "DejaVuSans.ttf"), "docfuse/assets"),
        (str(assets_dir / "DejaVuSans-Bold.ttf"), "docfuse/assets"),
        (str(assets_dir / "tekken_240911.json"), "docfuse/assets"),
        (str(assets_dir / "o200k_base.tiktoken"), "docfuse/assets"),
        (str(i18n_dir / "fr.json"), "docfuse/i18n"),
        (str(i18n_dir / "en.json"), "docfuse/i18n"),
    ]
    + _tesseract_datas
    # D-096 : bibliothèque Tcl `tkdnd` (voir DocFuse.spec).
    + collect_data_files("tkinterdnd2"),
    hiddenimports=collect_submodules("docfuse.extractors")
    + collect_submodules("tiktoken_ext")
    + [
        "tkinter",
        "tkinterdnd2",
        "charset_normalizer",
        "tiktoken",
        "pypdfium2",
        "PIL",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "mypy", "ruff", "pip_licenses"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onefile : tout (runtime + binaires + datas + scripts) dans un seul .exe.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f"{_APP_NAME}-OCR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,  # --windowed : pas de console noire
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
