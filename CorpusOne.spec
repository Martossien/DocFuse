# -*- mode: python ; coding: utf-8 -*-
"""Spec file PyInstaller pour DocFuse / CorpusOne.

CdC §5.1 — Build Windows portable --onedir (pas --onefile pour la vitesse).
CdC §13.2 — Empaquetage Python : PyInstaller --onedir préféré à onefile.

Usage sur Windows:
    pyinstaller --noconfirm CorpusOne.spec

Usage sous Linux avec Wine:
    # 1. Installer Wine
    # 2. Installer Python pour Windows dans Wine
    # 3. Installer les dépendances dans Wine
    # 4. Lancer PyInstaller via Wine
    wine python pyinstaller --noconfirm CorpusOne.spec
"""

import os
from pathlib import Path

block_cipher = None

# Chemin des assets (polices DejaVu)
assets_dir = Path(SPECPATH) / "src" / "docfuse" / "assets"
i18n_dir = Path(SPECPATH) / "src" / "docfuse" / "i18n"

a = Analysis(
    [str(Path(SPECPATH) / "src" / "docfuse" / "__main__.py")],
    pathex=[str(Path(SPECPATH) / "src")],
    binaries=[],
    datas=[
        (str(assets_dir / "DejaVuSans.ttf"), "docfuse/assets"),
        (str(assets_dir / "DejaVuSans-Bold.ttf"), "docfuse/assets"),
        (str(i18n_dir / "fr.json"), "docfuse/i18n"),
        (str(i18n_dir / "en.json"), "docfuse/i18n"),
    ],
    hiddenimports=[
        "tkinterdnd2",
        "charset_normalizer",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "mypy", "ruff", "pip_licenses"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CorpusOne",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # --windowed : pas de console noire
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CorpusOne",
)