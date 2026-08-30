#!/bin/bash
# Script de build Windows pour DocFuse (anciennement CorpusOne)
# Build portable PyInstaller --onefile : un seul .exe autoportant (D-054/D-055).
#
# Le nom de l'exécutable suit la variable DOCFUSE_APP_NAME (défaut : DocFuse),
# comme le dossier de sortie et la config (D-102) :
#   DOCFUSE_APP_NAME=MonOutil pyinstaller --noconfirm DocFuse.spec  →  dist/MonOutil.exe
#
# Usage sur Windows :
#   pip install -e ".[dev,gui]" pyinstaller
#   pyinstaller --noconfirm DocFuse.spec          # → dist/DocFuse.exe
#   pyinstaller --noconfirm DocFuse-OCR.spec      # → dist/DocFuse-OCR.exe (Tesseract requis, voir le spec)
#
# Usage sous Linux avec Wine (cross-compile) :
#   1. Installer Wine : sudo apt install wine64
#   2. Télécharger Python pour Windows :
#      wget https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe
#   3. Installer dans Wine :
#      wine python-3.12.7-amd64.exe /quiet InstallAllUsers=1
#   4. Installer les dépendances :
#      wine python -m pip install -e ".[dev,gui]" pyinstaller
#   5. Build :
#      wine python -m PyInstaller --noconfirm DocFuse.spec

set -e

APP_NAME="${DOCFUSE_APP_NAME:-DocFuse}"
SPEC="${1:-DocFuse.spec}"
echo "=== Build $APP_NAME ($SPEC) ==="

# Sur Windows natif
if [[ "$OS" == "Windows_NT" ]] || [[ "$(uname -s)" == *"MINGW"* ]]; then
    echo "Build Windows natif..."
    pyinstaller --noconfirm "$SPEC"
    echo "Build terminé : dist/$APP_NAME.exe (ou dist/$APP_NAME-OCR.exe pour le spec OCR)"
    exit 0
fi

# Sous Linux avec Wine
if command -v wine64 &>/dev/null; then
    echo "Build via Wine..."
    wine64 python -m PyInstaller --noconfirm "$SPEC"
    echo "Build terminé : dist/$APP_NAME.exe (ou dist/$APP_NAME-OCR.exe pour le spec OCR)"
    exit 0
fi

echo "Ce script ne peut pas produire un .exe Windows sur cette machine."
echo "Solutions :"
echo "  1. Sur une machine Windows : pyinstaller --noconfirm $SPEC"
echo "  2. Via la CI GitHub Actions (job build-windows / build-windows-ocr)"
echo "  3. Installer Wine + Python Windows :"
echo "     wine64 python -m PyInstaller --noconfirm $SPEC"
exit 1
