# -*- mode: python ; coding: utf-8 -*-
"""Spec file PyInstaller pour DocFuse (anciennement CorpusOne).

CdC §5.1 — Build Windows portable mono-exécutable (--onefile).
    Le runtime Python (python313.dll, VCRUNTIME140, etc.) et toutes les
    dépendances sont embarqués dans le .exe pour qu'un simple déplacement
    du fichier DocFuse.exe suffise à le lancer, sans DLL externe.
CdC §13.2 — Empaquetage Python : PyInstaller onefile préféré pour la
    portabilité. Le démarrage (extraction du bundle dans %TEMP%) reste
    acceptable pour un outil de génération de corpus.

Usage sur Windows:
    pyinstaller --noconfirm DocFuse.spec

Usage sous Linux avec Wine:
    # 1. Installer Wine
    # 2. Installer Python pour Windows dans Wine
    # 3. Installer les dépendances dans Wine
    # 4. Lancer PyInstaller via Wine
    wine python pyinstaller --noconfirm DocFuse.spec
"""

import os
import sys

# D-102 : le nom de l'exécutable suit la variable d'environnement lue par
# `docfuse.branding` (défaut DocFuse) — un seul nom pour l'exe, le dossier de
# sortie et la config.
_APP_NAME = (os.environ.get("DOCFUSE_APP_NAME") or "DocFuse").strip() or "DocFuse"
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Chemin des assets (polices DejaVu)
assets_dir = Path(SPECPATH) / "src" / "docfuse" / "assets"
i18n_dir = Path(SPECPATH) / "src" / "docfuse" / "i18n"

# D-054 / D-055 : DLL runtime non couvertes par l'analyse statique.
# PyInstaller en mode onefile embarque les .pyd mais pas toujours les DLL
# natives dont elles dépendent (Tcl/Tk : tcl86t/tk86t/zlib1 ; ctypes : libffi-8 ;
# ssl : libssl-3 / libcrypto-3 ; sqlite3 : sqlite3.dll). Comme aucun module
# Python ne fait `import tcl86t.dll`, ces DLL ne sont pas auto-collectées et
# leur absence fait échouer le chargement de _tkinter / _ctypes / _ssl / _sqlite3
# dès la première fenêtre GUI.
#
# Solution : on force l'inclusion de toute DLL du dossier <python>/DLLs/ qui
# n'est pas déjà embarquée par PyInstaller. C'est portable : si la DLL est
# absente du Python de build (ex. Tcl non installé), elle est simplement
# ignorée.
_python_dlls_dir = Path(getattr(sys, "base_prefix", sys.prefix)) / "DLLs"
_extra_binaries: list[tuple[str, str]] = []
if _python_dlls_dir.is_dir():
    for _dll_path in sorted(_python_dlls_dir.glob("*.dll")):
        _extra_binaries.append((str(_dll_path), "."))

a = Analysis(
    [str(Path(SPECPATH) / "src" / "docfuse" / "__main__.py")],
    pathex=[str(Path(SPECPATH) / "src")],
    binaries=_extra_binaries,
    datas=[
        (str(assets_dir / "DejaVuSans.ttf"), "docfuse/assets"),
        (str(assets_dir / "DejaVuSans-Bold.ttf"), "docfuse/assets"),
        (str(assets_dir / "tekken_240911.json.gz"), "docfuse/assets"),
        (str(assets_dir / "o200k_base.tiktoken.gz"), "docfuse/assets"),
        (str(i18n_dir / "fr.json"), "docfuse/i18n"),
        (str(i18n_dir / "en.json"), "docfuse/i18n"),
    ]
    # D-096 : la bibliothèque Tcl `tkdnd` (dossier tkinterdnd2/tkdnd/<os>-<arch>)
    # n'est pas un module Python : PyInstaller n'a aucun hook pour elle et ne
    # l'embarquait pas — le glisser-déposer ne pouvait pas fonctionner dans
    # l'exe même une fois `TkinterDnD.require()` appelé.
    + collect_data_files("tkinterdnd2"),
    hiddenimports=collect_submodules("docfuse.extractors")
    + collect_submodules("docfuse.gui")
    + collect_submodules("tiktoken_ext")
    + [
        "tkinter",
        "tkinterdnd2",
        "charset_normalizer",
        "tiktoken",
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
# exclude_binaries=False est la valeur onefile ; il n'y a plus de COLLECT().
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=_APP_NAME,
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
