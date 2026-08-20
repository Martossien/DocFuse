"""Registre des extracteurs avec dispatch par extension.

Inspiré de MarkItDown (ConverterRegistration + priorité), adapté pour DocFuse.

Principe :
- Chaque extracteur décore sa classe avec ``@register(".ext", priority=0.0)``.
- Le registre est un dict ``{extension: list[(priority, ExtractorClass)]}``.
- Au dispatch, on prend l'extracteur de priorité la plus basse (essayé en premier).
- L'import du module ``extractors`` déclenche l'enregistrement de tous les extracteurs.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docfuse.extractors.base import Extractor

# Registre : extension → liste de (priorité, classe)
# Tri stable : priorité la plus basse = essayé en premier (comme MarkItDown).
_REGISTRY: dict[str, list[tuple[float, type[Extractor]]]] = defaultdict(list)

# Indique si tous les extracteurs ont été importés (auto-discovery)
_LOADED = False


def register(
    *extensions: str, priority: float = 0.0
) -> Callable[[type[Extractor]], type[Extractor]]:
    """Décorateur pour enregistrer un extracteur pour une ou plusieurs extensions.

    Usage::

        @register(".pdf", priority=0.0)
        class PdfExtractor(Extractor):
            ...

    Args:
        *extensions: Extensions avec le point (ex: ".pdf", ".docx").
        priority: Priorité (plus bas = essayé en premier). Défaut 0.0.
            Les plugins peuvent utiliser une priorité négative pour passer
            avant les extracteurs built-in.

    Returns:
        La classe inchangée (décorateur pass-through).
    """

    def decorator(cls: type[Extractor]) -> type[Extractor]:
        for ext in extensions:
            _REGISTRY[ext.lower()].append((priority, cls))
        return cls

    return decorator


def _ensure_loaded() -> None:
    """Importe tous les modules d'extracteurs pour déclencher l'enregistrement.

    Idempotent : ne se exécute qu'une fois. L'import des modules déclenche
    les décorateurs @register au niveau module.
    """
    global _LOADED
    if _LOADED:
        return

    extractor_modules = [
        "docfuse.extractors.text",
        "docfuse.extractors.markdown",
        "docfuse.extractors.csv_tsv",
        "docfuse.extractors.xml_json",
        "docfuse.extractors.html",
        "docfuse.extractors.rtf",
        "docfuse.extractors.docx",
        "docfuse.extractors.pptx",
        "docfuse.extractors.xlsx",
        "docfuse.extractors.pdf",
        "docfuse.extractors.odf",
        "docfuse.extractors.eml",
        "docfuse.extractors.mhtml",
    ]

    for mod_name in extractor_modules:
        import_module(mod_name)

    _LOADED = True


def get_extractor_for(path: Path) -> type[Extractor] | None:
    """Retourne la classe d'extracteur appropriée pour un fichier.

    Args:
        path: Chemin du fichier.

    Returns:
        La classe d'extracteur (priorité la plus basse) ou None si l'extension
        n'est pas supportée.
    """
    _ensure_loaded()
    ext = path.suffix.lower()
    candidates = _REGISTRY.get(ext, [])
    if not candidates:
        return None
    # Tri stable par priorité : la plus basse gagne.
    candidates_sorted = sorted(candidates, key=lambda x: x[0])
    return candidates_sorted[0][1]


def list_supported_extensions() -> set[str]:
    """Retourne l'ensemble des extensions enregistrées dans le registre."""
    _ensure_loaded()
    return set(_REGISTRY.keys())


def clear_registry() -> None:
    """Vide le registre (pour les tests)."""
    global _LOADED
    _REGISTRY.clear()
    _LOADED = False
