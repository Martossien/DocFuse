"""Sélection explicite des fichiers et dossiers d'entrée.

Cette abstraction est partagée par la GUI, la CLI et l'orchestrateur afin que
les fichiers choisis par l'utilisateur restent la source de vérité du pipeline.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path


def path_key(path: Path) -> str:
    """Retourne une clé stable pour comparer des chemins locaux.

    ``normcase`` rend la comparaison insensible à la casse sous Windows sans
    imposer ce comportement sur les plateformes sensibles à la casse.
    """

    return os.path.normcase(str(path.absolute()))


@dataclass(frozen=True)
class InputSelection:
    """Fichiers/dossiers choisis et fichiers volontairement retirés."""

    paths: tuple[Path, ...]
    excluded_files: frozenset[Path] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        normalized_paths = self._deduplicate(self.paths)
        if not normalized_paths:
            raise ValueError("Une sélection doit contenir au moins un chemin")

        normalized_excluded = frozenset(Path(path).absolute() for path in self.excluded_files)
        object.__setattr__(self, "paths", normalized_paths)
        object.__setattr__(self, "excluded_files", normalized_excluded)

    @classmethod
    def from_paths(cls, paths: Iterable[Path]) -> InputSelection:
        """Construit une sélection normalisée depuis un itérable de chemins."""

        return cls(tuple(paths))

    @classmethod
    def from_value(cls, value: Path | Sequence[Path] | InputSelection) -> InputSelection:
        """Normalise l'entrée publique historique de ``run_analysis``."""

        if isinstance(value, InputSelection):
            return value
        if isinstance(value, Path):
            return cls((value,))
        return cls(tuple(value))

    @staticmethod
    def _deduplicate(paths: Iterable[Path]) -> tuple[Path, ...]:
        unique: list[Path] = []
        seen: set[str] = set()
        for raw_path in paths:
            path = Path(raw_path).absolute()
            key = path_key(path)
            if key not in seen:
                seen.add(key)
                unique.append(path)
        return tuple(unique)

    @property
    def primary_path(self) -> Path:
        """Premier chemin choisi, utilisé comme référence de sortie."""

        return self.paths[0]

    @property
    def output_directory(self) -> Path:
        """Dossier source dans lequel créer ``CorpusOne_output``."""

        primary = self.primary_path
        return primary if primary.is_dir() else primary.parent

    def exclude(self, path: Path) -> InputSelection:
        """Retourne une nouvelle sélection où ``path`` est explicitement retiré."""

        return InputSelection(self.paths, self.excluded_files | {path.absolute()})

    def is_excluded(self, path: Path) -> bool:
        """Indique si un fichier a été retiré de la sélection."""

        excluded_keys = {path_key(item) for item in self.excluded_files}
        return path_key(path) in excluded_keys
