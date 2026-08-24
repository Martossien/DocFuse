"""Constantes du projet : extensions supportées, seuils, couleurs, valeurs par défaut.

CdC §7, §9, §10, §12.
"""

from __future__ import annotations

import re

# ──────────────────────────────────────────────────────────────────────────────
# Extensions de fichiers supportées (liste blanche)
# CdC §7.2 (obligatoires), §7.3 (faciles), §7.4 (refusés)
# ──────────────────────────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS: dict[str, str] = {
    # Obligatoires (CdC §7.2)
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".rtf": "rtf",
    ".txt": "text",
    ".text": "text",
    ".log": "text",
    ".html": "html",
    ".htm": "html",
    # Faciles (CdC §7.3)
    ".md": "markdown",
    ".markdown": "markdown",
    ".csv": "csv_tsv",
    ".tsv": "csv_tsv",
    ".xlsx": "xlsx",
    ".ods": "odf",
    ".odt": "odf",
    ".odp": "odf",
    ".xml": "xml_json",
    ".json": "xml_json",
    ".yaml": "xml_json",
    ".yml": "xml_json",
    ".ini": "xml_json",
    ".cfg": "xml_json",
    ".eml": "eml",
    ".mhtml": "mhtml",
    ".mht": "mhtml",
}

# I-22: Extensions d'images pures (CdC §7.4 — ignorées avec message spécifique)
IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".tif",
        ".tiff",
        ".webp",
        ".svg",
        ".ico",
        ".heic",
    }
)

ALL_EXTENSIONS: frozenset[str] = frozenset(SUPPORTED_EXTENSIONS.keys())

# ──────────────────────────────────────────────────────────────────────────────
# Fichiers spéciaux à ignorer (CdC §7.5)
# ──────────────────────────────────────────────────────────────────────────────

IGNORE_PATTERNS: list[str] = [
    "~$*",  # Fichiers de verrouillage Office
    "Thumbs.db",
    "desktop.ini",
    ".DS_Store",
    "corpus.md",  # Sortie CorpusOne pour éviter de se réingérer
    "corpus.pdf",
    "corpusone_report.json",
    "corpusone_report.md",
    "*_rapport.md",  # I-05: Rapports générés par DocFuse
    "*_rapport.json",
]

IGNORE_DIRS: frozenset[str] = frozenset(
    {
        "$RECYCLE.BIN",
        "System Volume Information",
        ".git",
        "__pycache__",
        "_internal",  # Dossier runtime PyInstaller
    }
)

# ──────────────────────────────────────────────────────────────────────────────
# Valeurs par défaut (CdC §10, §12)
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_CONTEXT_LIMIT: int = 128_000
DEFAULT_MARGIN: float = 0.15
DEFAULT_FORMAT: str = "md"
DEFAULT_LANG: str = "fr"
DEFAULT_RECURSIVE: bool = True
DEFAULT_SORT: str = "name"
DEFAULT_OPEN_OUTPUT_FOLDER: bool = True

# ──────────────────────────────────────────────────────────────────────────────
# Seuils de détection scans / pauvreté de texte (CdC §9.2, §12)
# ──────────────────────────────────────────────────────────────────────────────

SCAN_MIN_CHARS_FILE: int = 80
"""Un fichier avec < 80 caractères de texte extractible → alerte importante."""

SCAN_MIN_CHARS_PER_PAGE: int = 50
"""PDF : moyenne < 50 caractères par page → alerte importante."""

SCAN_SPARSE_PAGE_CHARS: int = 20
"""PDF : une page avec < 20 caractères est « sparse »."""

SCAN_SPARSE_PAGE_RATIO: float = 0.30
"""PDF : ≥ 30 % de pages sparse + images → alerte importante."""

# ──────────────────────────────────────────────────────────────────────────────
# Compteur de contexte (CdC §10.1)
# ──────────────────────────────────────────────────────────────────────────────

BYTES_PER_TOKEN: int = 4
"""Approximation : 1 token ≈ 4 octets UTF-8."""

DEFAULT_TOKENIZER_ENGINE: str = "approx"
"""Moteur de comptage par défaut. "approx" = octets/4 (CdC §10), toujours
disponible. Autres moteurs enregistrés dans core/tokenizers/registry.py."""

# ──────────────────────────────────────────────────────────────────────────────
# PDF : déduplication des en-têtes/pieds de page répétés (v0.1.3)
# ──────────────────────────────────────────────────────────────────────────────

PDF_BOILERPLATE_MIN_PAGES: int = 4
"""Nombre minimum de pages du PDF pour tenter une déduplication."""

PDF_BOILERPLATE_MIN_OCCURRENCES: int = 3
"""Une ligne d'en-tête/pied de page doit apparaître au moins ce nombre de fois."""

PDF_BOILERPLATE_MIN_RATIO: float = 0.5
"""... et sur au moins cette proportion des pages pour être jugée répétitive."""

PDF_BOILERPLATE_MAX_LINE_LEN: int = 200
"""Longueur maximale d'une ligne candidate (en-têtes/pieds de page sont courts)."""

# ──────────────────────────────────────────────────────────────────────────────
# Markdown : images intégrées en base64 (v0.1.3)
# ──────────────────────────────────────────────────────────────────────────────

MARKDOWN_BASE64_MIN_LEN: int = 100
"""Longueur minimale d'un payload base64 pour être considéré comme une image
intégrée à retirer (évite de matcher de courtes chaînes accidentelles)."""

# ──────────────────────────────────────────────────────────────────────────────
# Détection de doublons de contenu entre fichiers (v0.1.3)
# ──────────────────────────────────────────────────────────────────────────────

DUPLICATE_MIN_CHARS: int = 50
"""Un fichier avec moins de caractères que ce seuil n'est jamais comparé pour
déduplication (évite les faux positifs entre fichiers presque vides)."""

# ──────────────────────────────────────────────────────────────────────────────
# Performance
# ──────────────────────────────────────────────────────────────────────────────

MAX_WORKERS: int = 4
"""Nombre maximum de threads d'extraction parallèle (IO-bound)."""

MAX_TRAVERSAL_DEPTH: int = 12
"""Profondeur maximale de parcours des dossiers (CdC §16)."""

LARGE_FILE_THRESHOLD: int = 50 * 1024 * 1024
"""Seuil de fichier volumineux : 50 Mo → message « patience » (CdC §17)."""

# ──────────────────────────────────────────────────────────────────────────────
# GUI : couleurs des statuts (CdC §6.1)
# ──────────────────────────────────────────────────────────────────────────────

STATUS_COLORS: dict[str, str] = {
    "ready": "#22c55e",  # vert
    "images": "#eab308",  # jaune
    "low_text": "#f97316",  # orange foncé
    "too_large": "#ef4444",  # rouge
    "ignored": "#9ca3af",  # gris
    "error": "#dc2626",  # rouge
}

# ──────────────────────────────────────────────────────────────────────────────
# Regex pour le tri naturel (file2 avant file10)
# ──────────────────────────────────────────────────────────────────────────────

_NATURAL_SORT_RE = re.compile(r"(\d+)")


def natural_sort_key(path: str) -> list[object]:
    """Clé de tri naturel : 'file2' < 'file10' car 2 < 10.

    Args:
        path: Chemin relatif ou nom de fichier.

    Returns:
        Liste alternant str et int pour comparaison naturelle.
    """
    return [int(s) if s.isdigit() else s.lower() for s in _NATURAL_SORT_RE.split(path)]
