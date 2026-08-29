"""Moteur OCR basé sur le binaire CLI Tesseract (Apache-2.0).

Invocation via `subprocess` plutôt qu'une liaison native (`tesserocr`) :
chaque appel est déjà un process OS isolé, avec son propre `timeout=` — pas
besoin d'un `ProcessPoolExecutor` ni d'un `TessBaseAPI` partagé (non
thread-safe). `tesseract stdin stdout` lit l'image sur l'entrée standard et
écrit le texte reconnu sur la sortie standard : aucun fichier temporaire à
créer ni à nettoyer.

Résolution du binaire, dans l'ordre :
1. Bundlé à côté de l'exécutable figé (`CorpusOne-OCR.exe`, voir
   `CorpusOne-OCR.spec`) — détecté via `sys._MEIPASS`.
2. Une installation Tesseract déjà présente sur la machine (PATH), ex.
   l'installeur Windows officiel (UB-Mannheim). Aucun réseau dans les deux cas.

Si aucun des deux n'est trouvé, `is_available()` renvoie `False` — l'appelant
(`extractors/pdf.py`) se comporte alors exactement comme avant l'ajout de
cette fonctionnalité (voir `core/ocr/registry.py::resolve_ocr_engine`).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from docfuse.core.ocr.base import OcrEngine, OcrEngineInfo

logger = logging.getLogger(__name__)


class TesseractEngine(OcrEngine):
    """OCR via le binaire CLI `tesseract`."""

    info = OcrEngineInfo(id="tesseract", label_key="ocr.tesseract")

    def is_available(self) -> bool:
        return _resolve_binary() is not None

    def ocr_image(self, image_bytes: bytes, lang: str) -> str:
        binary = _resolve_binary()
        if binary is None:
            return ""
        try:
            result = subprocess.run(
                [binary, "stdin", "stdout", "-l", lang],
                input=image_bytes,
                capture_output=True,
                timeout=_OCR_SUBPROCESS_TIMEOUT_S,
                check=False,
                env=_subprocess_env(binary),
            )
        except (subprocess.TimeoutExpired, OSError):
            logger.warning("Échec OCR (timeout ou erreur process)", exc_info=True)
            return ""
        if result.returncode != 0:
            logger.warning("tesseract a renvoyé le code %d", result.returncode)
            return ""
        return result.stdout.decode("utf-8", errors="replace")


_OCR_SUBPROCESS_TIMEOUT_S = 60


def _bundled_binary_path() -> Path | None:
    """Chemin du binaire Tesseract embarqué dans un exécutable figé (CorpusOne-OCR).

    `sys._MEIPASS` n'existe que dans un exécutable PyInstaller onefile en
    cours d'exécution (extraction temporaire du bundle). L'arborescence
    attendue (voir `CorpusOne-OCR.spec`) : `tesseract/tesseract.exe` +
    `tesseract/tessdata/*.traineddata` juste à côté.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is None:
        return None
    candidate = Path(meipass) / "tesseract" / "tesseract.exe"
    return candidate if candidate.is_file() else None


@lru_cache(maxsize=1)
def _resolve_binary() -> str | None:
    """Résout le chemin du binaire Tesseract utilisable, ou `None`.

    Mis en cache : la résolution (accès disque + PATH) ne doit être refaite
    qu'une fois par exécution.
    """
    bundled = _bundled_binary_path()
    if bundled is not None:
        return str(bundled)
    return shutil.which("tesseract")


def _subprocess_env(binary: str) -> dict[str, str] | None:
    """Environnement à passer au process `tesseract`.

    Pour le binaire bundlé (`CorpusOne-OCR.exe`), `TESSDATA_PREFIX` est fixé
    explicitement vers le `tessdata/` embarqué à côté — on ne compte pas sur
    la détection relative par défaut de Tesseract, qui dépend du répertoire
    de travail du process appelant, imprévisible depuis un onefile
    PyInstaller (extraction dans %TEMP%). Pour une installation système
    (PATH), l'environnement hérité suffit — c'est celui que son propre
    installeur a déjà configuré.
    """
    bundled = _bundled_binary_path()
    if bundled is None or str(bundled) != binary:
        return None
    tessdata_dir = bundled.parent / "tessdata"
    env = dict(os.environ)
    env["TESSDATA_PREFIX"] = str(tessdata_dir)
    return env
