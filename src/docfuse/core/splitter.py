"""Découpage d'un résultat d'analyse en plusieurs corpus par budget de tokens (D-101).

Jusqu'en 0.1.x, un total (ou un fichier) au-delà du plafond **bloquait** la
génération (CdC §10.3). Le mode « découpage » (`split_context`) remplace ce
blocage par une répartition des fichiers en parties successives, chacune
sous le plafond :

- remplissage **séquentiel** dans l'ordre du tri (first-fit) — jamais de
  bin-packing qui réordonnerait les fichiers ;
- un fichier n'est **jamais coupé** ;
- un fichier qui dépasse à lui seul le plafond est **isolé** dans sa propre
  partie et signalé (`CorpusPart.oversized`) — jamais abandonné en silence
  (règle 12.4 d'AGENTS.md).

Module pur : aucune écriture, aucun état global. Les writers et le rapport
consomment la liste de `CorpusPart` (voir `orchestrator.generate_corpus_parts`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docfuse.core.orchestrator import OrchestratorResult


@dataclass(frozen=True)
class CorpusPart:
    """Une partie du corpus : indices (dans `result.files`) et totaux.

    Attributes:
        index: Numéro de partie, à partir de 1 (numérotation des fichiers
            `corpus_001.md`, `corpus_002.md`…).
        file_indices: Indices des fichiers de cette partie dans
            `result.files` / `result.estimates`, dans l'ordre du corpus.
        tokens_estimated: Somme des tokens estimés des fichiers de la partie.
        tokens_with_margin: Somme des tokens avec marge (le budget comparé au
            plafond).
        oversized: True si la partie ne contient qu'un fichier qui dépasse à
            lui seul le plafond.
    """

    index: int
    file_indices: tuple[int, ...]
    tokens_estimated: int
    tokens_with_margin: int
    oversized: bool = False


def split_by_budget(
    result: OrchestratorResult, context_limit: int | None = None
) -> list[CorpusPart]:
    """Répartit les fichiers extraits de `result` en parties sous le plafond.

    Args:
        result: Résultat d'analyse (les estimations sont alignées sur les
            fichiers). Seuls les fichiers dont le statut de base est
            « extrait » (READY, IMAGES, LOW_TEXT) participent — les mêmes que
            ceux que les writers écrivent.
        context_limit: Plafond en tokens (avec marge). Par défaut celui du
            résultat.

    Returns:
        Liste de parties, vide si aucun fichier extrait. La concaténation des
        `file_indices` de toutes les parties est exactement la liste des
        fichiers extraits, dans l'ordre.
    """
    limit = result.context_limit if context_limit is None else context_limit
    parts: list[CorpusPart] = []
    current: list[int] = []
    current_estimated = 0
    current_margin = 0

    def close_part(*, oversized: bool = False) -> None:
        nonlocal current, current_estimated, current_margin
        if not current:
            return
        parts.append(
            CorpusPart(
                index=len(parts) + 1,
                file_indices=tuple(current),
                tokens_estimated=current_estimated,
                tokens_with_margin=current_margin,
                oversized=oversized,
            )
        )
        current, current_estimated, current_margin = [], 0, 0

    for index in result.extracted_indices():
        estimate = result.estimates[index]
        cost = estimate.tokens_with_margin
        if cost > limit:
            # Fichier hors plafond : on ferme la partie en cours, on l'isole
            # dans la sienne (signalée), et on repart à vide.
            close_part()
            current = [index]
            current_estimated = estimate.tokens_estimated
            current_margin = cost
            close_part(oversized=True)
            continue
        if current and current_margin + cost > limit:
            close_part()
        current.append(index)
        current_estimated += estimate.tokens_estimated
        current_margin += cost

    close_part()
    return parts


def part_of_file(parts: list[CorpusPart], file_index: int) -> int | None:
    """Numéro de la partie contenant `file_index`, ou None (fichier non extrait)."""
    for part in parts:
        if file_index in part.file_indices:
            return part.index
    return None
