#!/bin/bash
# Script de build Windows pour DocFuse / CorpusOne
# CdC §5.1 — Build portable --onedir
#
# Usage sur Windows:
#   pip install -e ".[dev]"
#   pyinstaller --noconfirm CorpusOne.spec
#
# Usage sous Linux avec Wine (cross-compile):
#   1. Installer Wine : sudo apt install wine64
#   2. Télécharger Python pour Windows :
#      wget https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe
#   3. Installer dans Wine :
#      wine python-3.12.7-amd64.exe /quiet InstallAllUsers=1
#   4. Installer les dépendances :
#      wine python -m pip install -r requirements-build.txt
#   5. Build :
#      wine python -m PyInstaller --noconfirm CorpusOne.spec
#
# Le résultat est dans dist/CorpusOne/CorpusOne.exe

set -e

echo "=== Build DocFuse / CorpusOne ==="

# Sur Windows natif
if [[ "$OS" == "Windows_NT" ]] || [[ "$(uname -s)" == *"MINGW"* ]]; then
    echo "Build Windows natif..."
    pyinstaller --noconfirm CorpusOne.spec
    echo "Build terminé : dist/CorpusOne/CorpusOne.exe"
    exit 0
fi

# Sous Linux avec Wine
if command -v wine64 &>/dev/null; then
    echo "Build via Wine..."
    wine64 python -m PyInstaller --noconfirm CorpusOne.spec
    echo "Build terminé : dist/CorpusOne/CorpusOne.exe"
    exit 0
fi

echo "Erreur: PyInstaller ne peut pas cross-compiler vers Windows depuis Linux sans Wine."
echo ""
echo "Solutions :"
echo "  1. Sur une machine Windows : pyinstaller --noconfirm CorpusOne.spec"
echo "  2. Sous Linux avec Wine :"
echo "     sudo apt install wine64"
echo "     wine64 python -m pip install pyinstaller"
echo "     wine64 python -m PyInstaller --noconfirm CorpusOne.spec"
echo "  3. Via GitHub Actions (windows-latest) :"
echo "     Le workflow CI peut être étendu pour build le binaire."
echo ""
echo "Le fichier CorpusOne.spec est prêt pour le build."
exit 1