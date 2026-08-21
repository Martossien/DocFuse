"""Configuration : chargement JSON à 3 niveaux.

CdC §5.2 — Ordre de lecture (le premier trouvé gagne, puis fusion avec les défauts) :
1. Fichier CorpusOne.json à côté de l'exe (priorité portable / clé USB).
2. %APPDATA%/CorpusOne/config.json (si le dossier de l'exe n'est pas inscriptible).
3. Valeurs par défaut compilées dans constants.py.

Écriture : même endroit d'où la conf a été lue ; si lecture seule → fallback APPDATA.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from docfuse.constants import (
    DEFAULT_CONTEXT_LIMIT,
    DEFAULT_FORMAT,
    DEFAULT_LANG,
    DEFAULT_MARGIN,
    DEFAULT_OPEN_OUTPUT_FOLDER,
    DEFAULT_RECURSIVE,
    DEFAULT_SORT,
    DEFAULT_TOKENIZER_ENGINE,
    SCAN_MIN_CHARS_FILE,
    SCAN_MIN_CHARS_PER_PAGE,
    SCAN_SPARSE_PAGE_CHARS,
    SCAN_SPARSE_PAGE_RATIO,
)

logger = logging.getLogger(__name__)


@dataclass
class ScanConfig:
    """Configuration des seuils de détection scans/pauvreté."""

    min_chars_file: int = SCAN_MIN_CHARS_FILE
    min_chars_per_page: int = SCAN_MIN_CHARS_PER_PAGE
    sparse_page_chars: int = SCAN_SPARSE_PAGE_CHARS
    sparse_page_ratio: float = SCAN_SPARSE_PAGE_RATIO


@dataclass
class Config:
    """Configuration de DocFuse.

    CdC §12 — Schéma JSON.
    """

    lang: str = DEFAULT_LANG
    format: str = DEFAULT_FORMAT
    context_limit: int = DEFAULT_CONTEXT_LIMIT
    margin: float = DEFAULT_MARGIN
    recursive: bool = DEFAULT_RECURSIVE
    sort: str = DEFAULT_SORT
    open_output_folder: bool = DEFAULT_OPEN_OUTPUT_FOLDER
    scan: ScanConfig = field(default_factory=ScanConfig)
    exclude_globs: list[str] = field(default_factory=list)
    max_depth: int = 12  # I-04: CdC §16 — profondeur max configurable, défaut 12
    tokenizer_engine: str = DEFAULT_TOKENIZER_ENGINE

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def validate(self) -> list[str]:
        """I-17: Valide les bornes min/max des champs.

        CdC §12 — Validation : types et min/max ; message clair.

        Returns:
            Liste de messages d'erreur (vide si tout est OK).
        """
        errors: list[str] = []
        if self.context_limit < 1:
            errors.append(f"context_limit doit être >= 1 (valeur: {self.context_limit})")
        if self.context_limit > 1_000_000:
            errors.append(f"context_limit inhabituel (valeur: {self.context_limit})")
        if not (-1.0 <= self.margin <= 10.0):
            errors.append(f"margin doit être entre -1.0 et 10.0 (valeur: {self.margin})")
        if self.sort not in ("name", "mtime", "type"):
            errors.append(f"sort doit être 'name', 'mtime' ou 'type' (valeur: {self.sort})")
        if not (1 <= self.max_depth <= 100):
            errors.append(f"max_depth doit être entre 1 et 100 (valeur: {self.max_depth})")
        if not (0 <= self.scan.min_chars_file <= 10000):
            errors.append(f"scan.min_chars_file hors plage (valeur: {self.scan.min_chars_file})")
        if not (0 <= self.scan.min_chars_per_page <= 10000):
            errors.append(
                f"scan.min_chars_per_page hors plage (valeur: {self.scan.min_chars_per_page})"
            )
        if not (0.0 <= self.scan.sparse_page_ratio <= 1.0):
            errors.append(
                f"scan.sparse_page_ratio doit être entre 0.0 et 1.0 (valeur: {self.scan.sparse_page_ratio})"
            )
        return errors


def _exe_dir() -> Path:
    """Retourne le dossier de l'exécutable (ou du script)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


def _appdata_dir() -> Path:
    """Retourne le dossier %APPDATA%/CorpusOne (ou équivalent Linux)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    else:
        base = str(Path.home() / ".config")
    return Path(base) / "CorpusOne"


def _config_paths() -> list[Path]:
    """Retourne les chemins de config possibles dans l'ordre de priorité."""
    paths: list[Path] = []

    # 1. À côté de l'exe
    exe_dir = _exe_dir()
    exe_config = exe_dir / "CorpusOne.json"
    paths.append(exe_config)

    # 2. APPDATA
    appdata_config = _appdata_dir() / "config.json"
    paths.append(appdata_config)

    return paths


def load_config(explicit_path: Path | None = None) -> Config:
    """Charge la configuration depuis les fichiers JSON.

    Args:
        explicit_path: Chemin explicite (surcharge CLI --config).

    Returns:
        Config fusionnée avec les défauts.
    """
    config = Config()

    paths_to_try: list[Path] = []
    if explicit_path:
        paths_to_try.append(explicit_path)
    paths_to_try.extend(_config_paths())

    for config_path in paths_to_try:
        if config_path.exists() and config_path.is_file():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                config = _merge_config(config, data)
                logger.info("Config chargée depuis %s", config_path)
                break
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.warning(
                    "Config invalide dans %s : %s — bascule sur défauts", config_path, exc
                )

    return config


def _merge_config(base: Config, data: dict[str, Any]) -> Config:
    """Fusionne un dictionnaire JSON dans une Config existante.

    Champs inconnus = ignorés (forward compatible). CdC §12.
    """
    if "lang" in data:
        base.lang = str(data["lang"])
    if "format" in data:
        base.format = str(data["format"])
    if "context_limit" in data:
        base.context_limit = int(data["context_limit"])
    if "margin" in data:
        base.margin = float(data["margin"])
    if "recursive" in data:
        base.recursive = bool(data["recursive"])
    if "sort" in data:
        base.sort = str(data["sort"])
    if "open_output_folder" in data:
        base.open_output_folder = bool(data["open_output_folder"])
    if "exclude_globs" in data:
        base.exclude_globs = [str(g) for g in data["exclude_globs"]]
    if "max_depth" in data:  # I-04
        base.max_depth = int(data["max_depth"])
    if "tokenizer_engine" in data:
        base.tokenizer_engine = str(data["tokenizer_engine"])
    if "scan" in data and isinstance(data["scan"], dict):
        scan_data: dict[str, Any] = data["scan"]
        if "min_chars_file" in scan_data:
            base.scan.min_chars_file = int(scan_data["min_chars_file"])
        if "min_chars_per_page" in scan_data:
            base.scan.min_chars_per_page = int(scan_data["min_chars_per_page"])
        if "sparse_page_chars" in scan_data:
            base.scan.sparse_page_chars = int(scan_data["sparse_page_chars"])
        if "sparse_page_ratio" in scan_data:
            base.scan.sparse_page_ratio = float(scan_data["sparse_page_ratio"])

    return base


def save_config(config: Config, explicit_path: Path | None = None) -> Path:
    """Sauvegarde la configuration en JSON.

    CdC §5.2 — Écriture : même endroit d'où la conf a été lue ;
    si lecture seule → fallback APPDATA.

    Args:
        config: Configuration à sauvegarder.
        explicit_path: Chemin explicite (si fourni par CLI).

    Returns:
        Chemin où la config a été écrite.
    """
    if explicit_path:
        target = explicit_path
    else:
        # Essayer à côté de l'exe d'abord
        target = _exe_dir() / "CorpusOne.json"
        if not _is_writable_dir(target.parent):
            target = _appdata_dir() / "config.json"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(config.to_json(), encoding="utf-8")
    logger.info("Config sauvegardée dans %s", target)
    return target


def _is_writable_dir(path: Path) -> bool:
    """Vérifie si un dossier est inscriptible."""
    try:
        test_file = path / ".docfuse_write_test"
        test_file.touch()
        test_file.unlink()
        return True
    except (OSError, PermissionError):
        return False
