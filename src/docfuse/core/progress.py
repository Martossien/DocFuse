"""Événements de progression thread-safe pour la GUI et la CLI.

L'orchestrator émet des ProgressEvent dans une queue thread-safe.
La GUI ou la CLI consomme cette queue pour mettre à jour l'affichage.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Protocol


@dataclass(frozen=True)
class ProgressEvent:
    """Événement de progression émis par l'orchestrator.

    Attributes:
        file_path: Chemin relatif du fichier en cours.
        current: Nombre de fichiers terminés, cet événement compris (D-099 :
            un compteur monotone — l'ancien index d'inventaire faisait
            reculer la barre quand les extractions parallèles finissaient
            dans le désordre). 0 pour un événement « pending ».
        total: Nombre total de fichiers à traiter.
        status: Statut du fichier ("ready", "images", "low_text", etc.).
        message: Message optionnel (erreur, warning).
    """

    file_path: str
    current: int
    total: int
    status: str
    message: str | None = None


class ProgressCallback(Protocol):
    """Protocole pour un callback de progression."""

    def __call__(self, event: ProgressEvent) -> None: ...


class ProgressEmitter:
    """Émetteur d'événements de progression avec queue thread-safe.

    L'orchestrator pousse des événements via ``emit()``.
    La GUI/CLI consomme via ``drain()`` (non bloquant) ou ``wait_event()`` (bloquant).
    """

    def __init__(self) -> None:
        self._queue: Queue[ProgressEvent] = Queue()
        self._cancelled = threading.Event()

    def emit(self, event: ProgressEvent) -> None:
        """Émet un événement de progression (thread-safe)."""
        if not self._cancelled.is_set():
            self._queue.put(event)

    def drain(self) -> list[ProgressEvent]:
        """Récupère tous les événements en attente (non bloquant).

        Returns:
            Liste des événements en attente (peut être vide).
        """
        events: list[ProgressEvent] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except Empty:
                break
        return events

    def cancel(self) -> None:
        """Signale l'annulation à tous les threads d'extraction."""
        self._cancelled.set()

    @property
    def is_cancelled(self) -> bool:
        """True si l'utilisateur a demandé l'annulation."""
        return self._cancelled.is_set()
