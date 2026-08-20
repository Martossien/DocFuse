"""Inventaire : parcourt un dossier et liste les fichiers supportés.

CdC §7.1 — Liste blanche d'extensions. Rien d'inconnu n'est concaténé.
CdC §7.5 — Fichiers spéciaux à ignorer proprement.
CdC §8.1 — Tri par chemin relatif, ordre naturel, insensible à la casse.
"""

from __future__ import annotations

import fnmatch
import logging
import os
from collections.abc import Iterator
from pathlib import Path

from docfuse.constants import (
    ALL_EXTENSIONS,
    IGNORE_DIRS,
    IGNORE_PATTERNS,
    IMAGE_EXTENSIONS,
    MAX_TRAVERSAL_DEPTH,
    natural_sort_key,
)

logger = logging.getLogger(__name__)


def _should_ignore(filename: str) -> bool:
    """Vérifie si un fichier correspond à un pattern d'ignorance.

    Args:
        filename: Nom du fichier (pas le chemin complet).

    Returns:
        True si le fichier doit être ignoré.
    """
    return any(fnmatch.fnmatch(filename, pattern) for pattern in IGNORE_PATTERNS)


def _should_ignore_dir(dirname: str) -> bool:
    """Vérifie si un dossier doit être ignoré.

    M-07: On filtre les dossiers système et de versioning, mais pas tous
    les dossiers commençant par un point (certains peuvent contenir des docs).
    Les dossiers cachés VCS (".git", ".svn", ".hg", ".bzr") et système sont exclus.
    """
    vcs_dirs = {".git", ".svn", ".hg", ".bzr", ".gitignore"}
    return dirname in IGNORE_DIRS or dirname in vcs_dirs


def scan_directory(
    root: Path,
    recursive: bool = True,
    extensions: frozenset[str] | None = None,
    exclude_globs: list[str] | None = None,
    max_depth: int = MAX_TRAVERSAL_DEPTH,
    sort: str = "name",
) -> list[Path]:
    """Parcourt un dossier et retourne la liste des fichiers supportés.

    Args:
        root: Dossier racine à parcourir.
        recursive: Si True, descend dans les sous-dossiers.
        extensions: Liste blanche d'extensions (avec le point).
            Si None, utilise ALL_EXTENSIONS.
        exclude_globs: Patterns fnmatch à exclure (ex: ["*.tmp"]).
        max_depth: Profondeur maximale (CdC §16, défaut 12).
        sort: Mode de tri — "name" (défaut, tri naturel), "mtime", "type" (CdC §8.1).

    Returns:
        Liste triée selon le mode choisi.
    """
    if extensions is None:
        extensions = ALL_EXTENSIONS

    exclude_globs = exclude_globs or []
    found: list[Path] = []

    if not root.is_dir():
        raise NotADirectoryError(f"Le chemin n'est pas un dossier: {root}")

    if recursive:
        for dirpath, dirnames, filenames in _walk_with_depth(root, max_depth):
            # Filtrer les dossiers à ignorer (mutation in-place de dirnames)
            dirnames[:] = [d for d in dirnames if not _should_ignore_dir(d)]
            for filename in filenames:
                if _matches_file(filename, extensions, exclude_globs):
                    found.append(Path(dirpath) / filename)
    else:
        for entry in root.iterdir():
            if entry.is_file() and _matches_file(entry.name, extensions, exclude_globs):
                found.append(entry)

    # Tri selon le mode choisi (CdC §8.1 — sort: name | mtime | type)
    if sort == "mtime":
        found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    elif sort == "type":
        found.sort(key=lambda p: (p.suffix.lower(), natural_sort_key(str(p.relative_to(root)))))
    else:  # name (défaut)
        found.sort(key=lambda p: natural_sort_key(str(p.relative_to(root))))
    return found


def _walk_with_depth(root: Path, max_depth: int) -> Iterator[tuple[str, list[str], list[str]]]:
    """os.walk avec limite de profondeur.

    Générateur yielding (dirpath, dirnames, filenames) comme os.walk,
    mais ne descend pas au-delà de max_depth.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        # Calcul de la profondeur
        rel = Path(dirpath).relative_to(root)
        depth = len(rel.parts)
        if depth >= max_depth:
            dirnames[:] = []  # Ne pas descendre plus loin
        yield dirpath, dirnames, filenames


def _matches_file(
    filename: str,
    extensions: frozenset[str],
    exclude_globs: list[str],
) -> bool:
    """Vérifie si un fichier doit être inclus dans l'inventaire.

    Args:
        filename: Nom du fichier.
        extensions: Liste blanche d'extensions.
        exclude_globs: Patterns d'exclusion.

    Returns:
        True si le fichier est supporté et non exclu.
    """
    # Ignorer les fichiers spéciaux
    if _should_ignore(filename):
        return False

    # Ignorer les patterns d'exclusion
    for pattern in exclude_globs:
        if fnmatch.fnmatch(filename, pattern):
            return False

    # Vérifier l'extension (liste blanche)
    ext = Path(filename).suffix.lower()
    return ext in extensions


def scan_files(
    paths: list[Path],
    extensions: frozenset[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> list[Path]:
    """Liste des fichiers individuels (pas un dossier).

    Pour le scénario glisser-déposer de fichiers (CdC §2.3).

    Args:
        paths: Liste de fichiers individuels.
        extensions: Liste blanche d'extensions.
        exclude_globs: Patterns d'exclusion.

    Returns:
        Liste triée par ordre naturel du nom de fichier.
    """
    if extensions is None:
        extensions = ALL_EXTENSIONS

    exclude_globs = exclude_globs or []
    found: list[Path] = []

    for p in paths:
        if p.is_file() and _matches_file(p.name, extensions, exclude_globs):
            found.append(p)

    found.sort(key=lambda p: natural_sort_key(p.name))
    return found


def list_ignored(
    root: Path,
    recursive: bool = True,
    extensions: frozenset[str] | None = None,
    exclude_globs: list[str] | None = None,
    max_depth: int = MAX_TRAVERSAL_DEPTH,
) -> list[tuple[Path, str]]:
    """Liste les fichiers ignorés avec la raison (pour le rapport).

    CdC §7.1 : « Tout fichier rencontré et non retenu est listé dans le rapport. »

    Args:
        root: Dossier racine.
        recursive: Si True, descend dans les sous-dossiers.
        extensions: Liste blanche.
        exclude_globs: Patterns d'exclusion.
        max_depth: Profondeur maximale.

    Returns:
        Liste de (chemin, raison) pour chaque fichier ignoré.
    """
    from docfuse.i18n import t

    if extensions is None:
        extensions = ALL_EXTENSIONS

    exclude_globs = exclude_globs or []
    ignored: list[tuple[Path, str]] = []

    def _classify(filename: str, ext: str) -> str | None:
        """Classifie un fichier ignoré et retourne la raison (i18n) ou None."""
        if _should_ignore(filename):
            return t("inventory.special_ignored")
        if any(fnmatch.fnmatch(filename, pat) for pat in exclude_globs):
            return t("inventory.excluded_by_pattern")
        if ext not in extensions:
            if ext in IMAGE_EXTENSIONS:
                return t("inventory.image_ocr_disabled")
            return t("inventory.unsupported_ext", ext=ext or "(none)")
        return None

    if recursive:
        for dirpath, dirnames, filenames in _walk_with_depth(root, max_depth):
            dirnames[:] = [d for d in dirnames if not _should_ignore_dir(d)]
            for filename in filenames:
                filepath = Path(dirpath) / filename
                ext = Path(filename).suffix.lower()
                reason = _classify(filename, ext)
                if reason:
                    ignored.append((filepath, reason))
    else:
        for entry in root.iterdir():
            if not entry.is_file():
                continue
            ext = entry.suffix.lower()
            reason = _classify(entry.name, ext)
            if reason:
                ignored.append((entry, reason))

    return ignored
