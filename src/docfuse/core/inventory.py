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
from dataclasses import dataclass
from pathlib import Path

from docfuse.constants import (
    ALL_EXTENSIONS,
    IGNORE_DIRS,
    IGNORE_PATTERNS,
    IMAGE_EXTENSIONS,
    MAX_TRAVERSAL_DEPTH,
    natural_sort_key,
)
from docfuse.models.input_selection import InputSelection, path_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InventoryEntry:
    """Fichier retenu et chemin de provenance affiché dans le corpus."""

    path: Path
    relative_path: str


def _should_ignore(filename: str) -> bool:
    """Vérifie si un fichier correspond à un pattern d'ignorance.

    Args:
        filename: Nom du fichier (pas le chemin complet).

    Returns:
        True si le fichier doit être ignoré.
    """
    return any(fnmatch.fnmatch(filename, pattern) for pattern in IGNORE_PATTERNS)


_VCS_DIRS: frozenset[str] = frozenset({".git", ".svn", ".hg", ".bzr"})


def _should_ignore_dir(dirname: str) -> bool:
    """Vérifie si un dossier doit être ignoré.

    M-07: On filtre les dossiers système et de versioning, mais pas tous
    les dossiers commençant par un point (certains peuvent contenir des docs).
    Les dossiers cachés VCS (".git", ".svn", ".hg", ".bzr") et système sont exclus.
    """
    return dirname in IGNORE_DIRS or dirname in _VCS_DIRS


def _safe_mtime(path: Path) -> float:
    """Clé de tri `mtime` qui ne lève jamais (D-096).

    Un lien symbolique cassé ou un fichier supprimé entre le parcours et le
    tri faisait remonter `FileNotFoundError` hors de `run_analysis` — toute
    l'analyse échouait, alors qu'en tri `name` le même fichier est
    simplement signalé en ERROR par son extracteur.
    """
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


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
    found, _ignored = _walk_source(root, recursive, extensions, exclude_globs, max_depth)

    # Tri selon le mode choisi (CdC §8.1 — sort: name | mtime | type)
    if sort == "mtime":
        found.sort(key=_safe_mtime, reverse=True)
    elif sort == "type":
        found.sort(key=lambda p: (p.suffix.lower(), natural_sort_key(str(p.relative_to(root)))))
    else:  # name (défaut)
        found.sort(key=lambda p: natural_sort_key(str(p.relative_to(root))))
    return found


def _walk_source(
    root: Path,
    recursive: bool,
    extensions: frozenset[str] | None,
    exclude_globs: list[str] | None,
    max_depth: int,
) -> tuple[list[Path], list[tuple[Path, str]]]:
    """Un seul parcours d'un dossier source → (fichiers retenus, ignorés).

    D-098 : `scan_directory` et `list_ignored` parcouraient chacun tout
    l'arbre (2× les appels système) et `collect_inputs` re-triait ensuite
    des entrées déjà triées. Les deux fonctions publiques restent
    disponibles (et triées) pour les appelants/tests existants ; le
    pipeline passe par ce parcours unique, non trié (le tri final se fait
    une fois dans `collect_inputs`).
    """
    from docfuse.i18n import t

    if extensions is None:
        extensions = ALL_EXTENSIONS
    exclude_globs = exclude_globs or []

    if not root.is_dir():
        raise NotADirectoryError(f"Le chemin n'est pas un dossier: {root}")

    found: list[Path] = []
    ignored: list[tuple[Path, str]] = []

    if recursive:
        for dirpath, dirnames, filenames in _walk_with_depth(root, max_depth):
            # D-096 : un dossier élagué (`node_modules/`, `build/`, `dist/`,
            # `.git/`, `__MACOSX/`…) n'apparaissait ni dans le corpus ni dans
            # le rapport — invisible, contraire au CdC §7.1 (« tout fichier
            # rencontré et non retenu est listé »). `build/` ou `dist/` sont
            # aussi des noms de dossiers documentaires ordinaires : on
            # signale le dossier élagué, une ligne par dossier.
            kept_dirs = []
            for d in dirnames:
                if _should_ignore_dir(d):
                    ignored.append((Path(dirpath) / d, t("inventory.ignored_dir")))
                else:
                    kept_dirs.append(d)
            dirnames[:] = kept_dirs
            for filename in filenames:
                filepath = Path(dirpath) / filename
                reason = _ignored_reason(filename, extensions, exclude_globs)
                if reason is None:
                    found.append(filepath)
                else:
                    ignored.append((filepath, reason))
    else:
        for entry in root.iterdir():
            if not entry.is_file():
                continue
            reason = _ignored_reason(entry.name, extensions, exclude_globs)
            if reason is None:
                found.append(entry)
            else:
                ignored.append((entry, reason))

    return found, ignored


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


def _ignored_reason(
    filename: str,
    extensions: frozenset[str],
    exclude_globs: list[str],
) -> str | None:
    """Retourne la raison localisée pour laquelle un fichier est ignoré."""

    from docfuse.i18n import t

    if _should_ignore(filename):
        return t("inventory.special_ignored")
    if any(fnmatch.fnmatch(filename, pattern) for pattern in exclude_globs):
        return t("inventory.excluded_by_pattern")

    ext = Path(filename).suffix.lower()
    if ext not in extensions:
        if ext in IMAGE_EXTENSIONS:
            return t("inventory.image_ocr_disabled")
        return t("inventory.unsupported_ext", ext=ext or "(none)")
    return None


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


def list_ignored_files(
    paths: list[Path],
    extensions: frozenset[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> list[tuple[Path, str]]:
    """Liste les fichiers explicitement choisis mais non retenus."""

    if extensions is None:
        extensions = ALL_EXTENSIONS
    exclude_globs = exclude_globs or []

    ignored: list[tuple[Path, str]] = []
    for path in paths:
        if not path.is_file():
            continue
        reason = _ignored_reason(path.name, extensions, exclude_globs)
        if reason is not None:
            ignored.append((path, reason))
    return ignored


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
    _found, ignored = _walk_source(root, recursive, extensions, exclude_globs, max_depth)
    return ignored


def _unique_relative_path(path: Path, preferred: str, used: set[str]) -> str:
    """Produit un libellé relatif lisible et unique pour l'en-tête SOURCE."""

    candidate = preferred
    if candidate.casefold() not in used:
        used.add(candidate.casefold())
        return candidate

    parts = path.parts
    for width in range(2, len(parts) + 1):
        candidate = str(Path(*parts[-width:]))
        if candidate.casefold() not in used:
            used.add(candidate.casefold())
            return candidate

    suffix = 2
    while f"{candidate} ({suffix})".casefold() in used:
        suffix += 1
    candidate = f"{candidate} ({suffix})"
    used.add(candidate.casefold())
    return candidate


def collect_inputs(
    selection: InputSelection,
    recursive: bool,
    exclude_globs: list[str],
    extensions: frozenset[str] | None,
    sort: str,
    max_depth: int,
) -> tuple[list[InventoryEntry], list[tuple[Path, str]]]:
    """Inventorie plusieurs sources sans élargir une sélection de fichiers."""

    from docfuse.i18n import t

    candidates: list[tuple[Path, str]] = []
    ignored: list[tuple[Path, str]] = []
    seen_files: set[str] = set()
    multiple_sources = len(selection.paths) > 1

    for source in selection.paths:
        if source.is_dir():
            # D-098 : un seul parcours par source, tri unique plus bas.
            paths, source_ignored = _walk_source(
                source, recursive, extensions, exclude_globs, max_depth
            )
            ignored.extend(source_ignored)
            for path in paths:
                relative = path.relative_to(source)
                preferred = str(Path(source.name) / relative) if multiple_sources else str(relative)
                key = path_key(path)
                if key not in seen_files:
                    seen_files.add(key)
                    candidates.append((path, preferred))
        elif source.is_file():
            paths = scan_files([source], exclude_globs=exclude_globs, extensions=extensions)
            ignored.extend(
                list_ignored_files([source], exclude_globs=exclude_globs, extensions=extensions)
            )
            for path in paths:
                key = path_key(path)
                if key not in seen_files:
                    seen_files.add(key)
                    candidates.append((path, path.name))

    excluded_keys = {path_key(path) for path in selection.excluded_files}
    included: list[tuple[Path, str]] = []
    for path, preferred in candidates:
        if path_key(path) in excluded_keys:
            ignored.append((path, t("inventory.removed_by_user")))
        else:
            included.append((path, preferred))

    used_relative_paths: set[str] = set()
    entries = [
        InventoryEntry(path, _unique_relative_path(path, preferred, used_relative_paths))
        for path, preferred in included
    ]

    if sort == "mtime":
        entries.sort(key=lambda entry: _safe_mtime(entry.path), reverse=True)
    elif sort == "type":
        entries.sort(
            key=lambda entry: (entry.path.suffix.lower(), natural_sort_key(entry.relative_path))
        )
    else:
        entries.sort(key=lambda entry: natural_sort_key(entry.relative_path))

    unique_ignored: list[tuple[Path, str]] = []
    seen_ignored: set[str] = set()
    for path, reason in ignored:
        key = path_key(path)
        if key not in seen_ignored:
            seen_ignored.add(key)
            unique_ignored.append((path, reason))
    return entries, unique_ignored
