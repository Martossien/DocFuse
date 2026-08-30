"""Constantes du projet : extensions supportées, seuils, couleurs, valeurs par défaut.

CdC §7, §9, §10, §12.
"""

from __future__ import annotations

import os
import re

from docfuse.branding import LEGACY_APP_NAME
from docfuse.branding import OUTPUT_DIR_NAME as _OUTPUT_DIR_NAME

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
    ".epub": "epub",
    ".msg": "msg",
    # Legacy Office binaire (Word/Excel/PowerPoint 97-2003, D-094)
    ".doc": "legacy_office",
    ".xls": "legacy_office",
    ".ppt": "legacy_office",
}

# Fichiers de développement traités comme texte brut (pas de parsing
# spécifique, juste détection d'encodage puis passage tel quel — cas d'usage
# LLM très courant : envoyer une codebase). Limite connue : dispatch par
# extension (`registry.py`), donc les fichiers sans extension (Dockerfile,
# Makefile) ou dotfiles purs (.gitignore, .env) restent hors périmètre.
CODE_EXTENSIONS: frozenset[str] = frozenset(
    {
        # Langages
        ".py",
        ".pyw",
        ".pyi",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".java",
        ".kt",
        ".kts",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".swift",
        ".c",
        ".h",
        ".cpp",
        ".cc",
        ".cxx",
        ".hpp",
        ".hh",
        ".cs",
        ".scala",
        ".lua",
        ".pl",
        ".pm",
        ".r",
        ".m",
        ".mm",
        ".dart",
        ".vb",
        ".vba",
        ".bas",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".psm1",
        ".bat",
        ".cmd",
        ".sql",
        ".groovy",
        ".clj",
        ".hs",
        ".fs",
        ".fsx",
        # Web / style
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".vue",
        ".svelte",
        # Config / infra / build
        ".toml",
        ".proto",
        ".graphql",
        ".gql",
        ".tf",
        ".tfvars",
        ".conf",
        ".properties",
        # Documentation texte
        ".rst",
        ".tex",
    }
)
SUPPORTED_EXTENSIONS.update(dict.fromkeys(CODE_EXTENSIONS, "code"))

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
    "corpus.md",  # Sortie DocFuse pour éviter de se réingérer
    "corpus.pdf",
    "corpus_[0-9][0-9][0-9].md",  # Parties d'un corpus découpé (D-101)
    "corpus_[0-9][0-9][0-9].pdf",
    f"{LEGACY_APP_NAME.lower()}_report.json",  # Rapports d'anciennes versions (0.1.x)
    f"{LEGACY_APP_NAME.lower()}_report.md",
    "*_rapport.md",  # I-05: Rapports générés par DocFuse (REPORT_SUFFIX)
    "*_rapport.json",
    "*.min.js",  # D-077 : bundle tiers minifié, jamais du code source à lire
    "*.min.css",
]

IGNORE_DIRS: frozenset[str] = frozenset(
    {
        "$RECYCLE.BIN",
        "System Volume Information",
        ".git",
        "__pycache__",
        "_internal",  # Dossier runtime PyInstaller
        # D-077 : dépendances/artefacts tiers du monde JS/web — jamais du
        # code écrit par l'utilisateur, souvent volumineux (jQuery, etc.).
        "node_modules",
        "vendor",
        "dist",
        "build",
        # D-092 : dossier créé par macOS lors de la compression d'une archive
        # ZIP — contient des fichiers AppleDouble (`._nom`, métadonnées de
        # resource fork), jamais du contenu réel malgré une extension qui
        # peut sembler légitime (ex: `__MACOSX/._rapport.json` n'est pas du
        # JSON, c'est du binaire propriétaire Apple).
        "__MACOSX",
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

DEFAULT_EXTRACT_EMBEDDED_IMAGES: bool = False
"""Export des images intégrées DOCX/PPTX en fichiers séparés (D-091) —
désactivé par défaut : c'est la seule fonctionnalité de DocFuse qui écrit des
fichiers en plus du corpus/rapport."""

# ──────────────────────────────────────────────────────────────────────────────
# Sorties : noms partagés CLI/GUI (D-099, voir output/paths.py)
# ──────────────────────────────────────────────────────────────────────────────

OUTPUT_DIR_NAME: str = _OUTPUT_DIR_NAME
"""Dossier de sortie par défaut, créé dans la source sélectionnée (I-13).
Dérivé du nom d'application (D-102, voir `branding.py`)."""

DEFAULT_SPLIT_CONTEXT: bool = False
"""Mode découpage (D-101) : désactivé par défaut, le plafond bloque (CdC §10.3)."""

REPORT_SUFFIX: str = "_rapport"
"""Suffixe des rapports écrits à côté du corpus (`corpus_rapport.md/.json`).
Doit rester cohérent avec les motifs `*_rapport.*` de IGNORE_PATTERNS."""

CORPUS_EXTENSIONS: dict[str, str] = {"md": ".md", "pdf": ".pdf"}
"""Format de sortie → extension du corpus."""

VERBATIM_EXTENSIONS: frozenset[str] = frozenset(
    {
        "md",
        "markdown",
        "txt",
        "text",
        "log",
        "csv",
        "tsv",
        "xml",
        "json",
        "yaml",
        "yml",
        "ini",
        "cfg",
        "eml",
        "mhtml",
        "mht",
    }
)
"""Extensions dont le texte est inclus tel quel dans le corpus Markdown (CdC
§7.3), jamais encapsulé dans des backticks même s'il contient des ```. Les
autres formats (documents bureautiques, PDF, HTML, code) sont encapsulés
dans des backticks adaptatifs quand leur texte contient des ```."""

CSV_FIELD_SIZE_LIMIT: int = 2**31 - 1
"""Taille maximale d'un champ CSV (D-096 : 131 072 par défaut faisait planter
tout fichier à long champ). `sys.maxsize` lève `OverflowError` sous Windows
(C long 32 bits) — valeur portable, 2 Go par champ suffisent largement."""

PDF_PAGE_HEADER_MAX_CHARS: int = 70
"""Longueur maximale du chemin relatif inscrit dans l'en-tête de chaque page
du corpus PDF (D-100) ; au-delà, raccourci par la gauche."""

UNUSUAL_CONTEXT_LIMIT: int = 1_000_000
"""Au-delà de ce plafond, un avertissement « valeur inhabituelle » est émis
(CdC §10.3, M-11)."""

HEADER_ESTIMATE_MAX_ITERATIONS: int = 20
"""Nombre maximal d'itérations pour faire converger l'en-tête SOURCE (qui
contient sa propre estimation de tokens) — voir output/source_header.py."""

SECRETS_NOTE_MAX_LINES_PER_KIND: int = 10
"""Nombre maximal de numéros de ligne cités par type de secret dans la note
de transparence (D-099 : un journal de 40 000 lignes de jetons produisait
une note de 1,5 Mo, soit 29 % des tokens du fichier)."""

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
# OCR des PDF scannés (moteur optionnel, voir core/ocr/)
# ──────────────────────────────────────────────────────────────────────────────

PDF_OCR_MIN_CHARS_PER_PAGE: int = 80
"""Une page avec moins de texte natif utile que ce seuil est candidate à
l'OCR (classée "ocr" ou "mixed" selon la présence d'images)."""

PDF_OCR_GARBAGE_MARKERS: tuple[str, ...] = ("(cid:", "�")
"""Marqueurs de texte natif « poubelle » (polices cassées, glyphes non
mappés) : une page qui en contient est traitée comme si elle n'avait pas de
texte utile, même si `PDF_OCR_MIN_CHARS_PER_PAGE` caractères ont été extraits."""

OCR_DPI: int = 200
"""Résolution de rastérisation d'une page avant OCR (interactif ; 300 pour
un CER trop élevé serait une optimisation v1.1)."""

OCR_LANG: str = "fra+eng"
"""Langues Tesseract (i18n FR/EN du projet)."""

OCR_PAGE_TIMEOUT_S: int = 60
"""Timeout d'un appel Tesseract (une page rastérisée ou une image intégrée).
Un appel qui dépasse ce délai est marqué "failed", le fichier continue.
D-098 : constante enfin câblée (elle documentait 30 s mais le code en dur
appliquait 60 s — la valeur réelle est conservée)."""

OCR_MAX_CONCURRENCY: int = max(2, min(8, os.cpu_count() or 4))
"""Nombre maximal de processus Tesseract simultanés pour tout le processus
(D-098). Tesseract est mono-thread par processus (non lié à OpenMP dans les
binaires embarqués/testés) : le débit croît linéairement avec ce nombre,
jusqu'au nombre de cœurs. Sémaphore global partagé entre l'OCR des pages
PDF et celui des images intégrées — auparavant jusqu'à MAX_WORKERS ×
MAX_WORKERS processus non bornés."""

OCR_MAX_PAGES_PER_FILE: int = 200
"""Plafond de pages OCRisables par fichier — protection contre un PDF hostile
(bombe de rendu) ou simplement un scan de très grande taille."""

OCR_MAX_PIXELS_PER_PAGE: int = 4000 * 4000
"""Plafond largeur×hauteur d'une page rastérisée — protection mémoire."""

# ──────────────────────────────────────────────────────────────────────────────
# Détection d'encodage : plausibilité du décodage cp1252 (D-093)
# ──────────────────────────────────────────────────────────────────────────────

ENCODING_MAX_CONTROL_RATIO: float = 0.01
"""Ratio maximal de caractères de contrôle (hors tab/LF/CR) toléré dans un
texte décodé en cp1252 pour être accepté tel quel — au-delà, on retombe sur
charset-normalizer plutôt que de garder un cp1252 mal choisi."""

ENCODING_PLAUSIBILITY_SAMPLE_CHARS: int = 100_000
"""Nombre de caractères analysés pour le test de plausibilité — coût borné
même sur un gros fichier."""

ENCODING_MAX_UTF8_REPLACEMENT_RATIO: float = 0.001
"""D-097 : un fichier dont le décodage UTF-8 tolérant ne produit pas plus
de cette proportion de U+FFFD (0,1 %) est considéré UTF-8 (séquence
tronquée en fin de fichier, octet égaré) plutôt que basculé en cp1252."""

# ──────────────────────────────────────────────────────────────────────────────
# Garde-fou "bombe zip" pour les formats conteneurs ZIP (D-093)
# ──────────────────────────────────────────────────────────────────────────────

ZIP_BOMB_MAX_RATIO: float = 200.0
"""Ratio (taille décompressée / taille compressée) au-delà duquel un
conteneur ZIP (DOCX/PPTX/XLSX/ODF/EPUB) est jugé suspect. Heuristique, pas
une science exacte — combiné à `ZIP_BOMB_MIN_UNCOMPRESSED_BYTES` pour éviter
les faux positifs sur un petit fichier légitimement très répétitif."""

ZIP_BOMB_MIN_UNCOMPRESSED_BYTES: int = 300 * 1024 * 1024
"""Volume décompressé minimal (300 Mo) pour que le ratio ci-dessus déclenche
un rejet — un petit fichier avec un ratio élevé n'est jamais dangereux."""

# ──────────────────────────────────────────────────────────────────────────────
# Performance
# ──────────────────────────────────────────────────────────────────────────────

MAX_WORKERS: int = max(2, min(8, os.cpu_count() or 4))
"""Nombre maximum de threads d'extraction parallèle (D-098). L'extraction est
CPU-bound (pdfminer, parseurs XML) + sous-processus Tesseract — pas
« IO-bound » comme l'ancienne docstring l'affirmait. Dérivé du nombre de
cœurs, borné à [2, 8] : mesuré 29 s → 26 s sur 120 fichiers réels en
passant de 4 à 8, aucun gain au-delà (le chemin critique est un seul
fichier, voir OCR_MAX_CONCURRENCY)."""

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

PENDING_COLOR: str = "#9ca3af"
"""Gris des lignes « en attente » et des statuts inconnus dans la table GUI."""

GAUGE_COLORS: dict[str, str] = {"ok": "#22c55e", "warning": "#f97316", "blocked": "#ef4444"}
"""Jauge de contexte (I-11) : vert sous GAUGE_WARNING_RATIO, orange jusqu'au
plafond, rouge au-delà."""

GAUGE_WARNING_RATIO: float = 0.8
"""Fraction du plafond à partir de laquelle la jauge passe à l'orange."""

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
