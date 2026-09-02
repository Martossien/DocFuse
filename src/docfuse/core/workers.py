"""Pool d'extraction : des processus plutôt que des threads (D-111).

L'extraction est du Python pur pour l'essentiel (pdfminer, parseurs XML,
rendu de pages) : sous le GIL, huit threads ne font que 1,6× mieux qu'un
seul (mesure du 02/09 sur 181 fichiers dont 41 PDF : 163 s en un thread,
101 s en huit threads, **48 s en huit processus**, sortie strictement
identique). Le pool de processus est donc la voie normale ; les threads
restent le repli.

Règles :
- contexte `spawn` sur tous les systèmes — pypdfium2 déconseille `fork`
  (état du moteur dupliqué, instabilités), et c'est le seul mode qui se
  comporte pareil sous Windows et Linux ;
- un seul pool par processus, réutilisé d'un appel à l'autre : sous Windows
  chaque travailleur est un interpréteur à relancer (~1 à 2 s), on ne paie
  ce prix qu'une fois par campagne, pas par lot ;
- les journaux des travailleurs remontent au parent (`QueueHandler` →
  `QueueListener`) : un avertissement d'extracteur finit dans le journal de
  l'application hôte, pas sur un stderr que personne ne lit ;
- le nombre de processus Tesseract reste borné pour **tout** le pool par un
  sémaphore inter-processus (`OCR_MAX_CONCURRENCY`), comme il l'était pour
  les threads — sans lui, huit travailleurs × huit pages donneraient 64
  Tesseract simultanés ;
- repli sur les threads si le pool ne peut pas démarrer ou se casse
  (`BrokenProcessPool` : un travailleur tué par l'OOM killer, par exemple),
  et d'office quand l'exécutable est gelé sur POSIX, où `spawn` n'est pas
  supporté par PyInstaller ; `DOCFUSE_EXTRACTION_POOL=thread` force les
  threads (tests qui remplacent des extracteurs en mémoire, diagnostic).

Les exécutables PyInstaller (onefile) relancent l'exe lui-même pour chaque
travailleur ; le crochet d'exécution de PyInstaller et `freeze_support()`
aux points d'entrée (`cli.main`, `gui.launch`) interceptent ce relancement.
"""

from __future__ import annotations

import atexit
import logging
import multiprocessing
import os
import sys
import threading
from collections.abc import Callable
from concurrent.futures import Executor, Future, ProcessPoolExecutor, ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from logging.handlers import QueueHandler, QueueListener
from multiprocessing.synchronize import Semaphore as ProcessSemaphore
from typing import Any

from docfuse.constants import MAX_WORKERS, OCR_MAX_CONCURRENCY

logger = logging.getLogger(__name__)

POOL_ENV = "DOCFUSE_EXTRACTION_POOL"
"""`process` (défaut) ou `thread`."""


def pool_kind() -> str:
    """Mode demandé : `process` sauf variable d'environnement `thread`, ou
    exécutable gelé sur POSIX (PyInstaller n'y supporte pas `spawn`)."""
    asked = os.environ.get(POOL_ENV, "process").strip().lower()
    if asked == "thread":
        return "thread"
    if getattr(sys, "frozen", False) and os.name != "nt":
        return "thread"
    return "process"


class ExtractionPool:
    """Le pool du processus, créé à la première demande et réutilisé.

    `submit` a la signature d'un `Executor`. `cancel_pending` abandonne ce
    qui n'a pas démarré (annulation par l'utilisateur) ; le pool est alors
    fermé et recréé à la demande suivante. `broken()` est à appeler quand un
    résultat lève `BrokenProcessPool` : le pool passe aux threads pour le
    reste du processus, en le disant une fois.
    """

    def __init__(self, max_workers: int = MAX_WORKERS) -> None:
        self.max_workers = max(1, max_workers)
        self._executor: Executor | None = None
        self._kind = ""
        self._listener: QueueListener | None = None
        self._lock = threading.Lock()
        self._fallback_said = False

    @property
    def kind(self) -> str:
        """`process`, `thread`, ou vide tant que rien n'a démarré."""
        return self._kind

    def submit(self, fn: Callable[..., Any], /, *args: Any) -> Future[Any]:
        return self._ensure().submit(fn, *args)

    def cancel_pending(self) -> None:
        """Abandonne les tâches non démarrées et ferme le pool (annulation)."""
        with self._lock:
            executor, self._executor = self._executor, None
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)
            self._stop_listener()
            self._kind = ""

    def broken(self, why: str) -> None:
        """Le pool de processus s'est cassé : threads pour la suite."""
        with self._lock:
            executor, self._executor = self._executor, None
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)
            self._stop_listener()
            self._kind = ""
            if not self._fallback_said:
                self._fallback_said = True
                logger.warning(
                    "Pool de processus d'extraction hors service (%s) : "
                    "extraction par threads pour la suite",
                    why,
                )

    def shutdown(self) -> None:
        with self._lock:
            executor, self._executor = self._executor, None
            if executor is not None:
                executor.shutdown(wait=True)
            self._stop_listener()
            self._kind = ""

    # ------------------------------------------------------------------ interne
    def _ensure(self) -> Executor:
        with self._lock:
            if self._executor is None:
                self._executor = self._start()
            return self._executor

    def _start(self) -> Executor:
        wanted = "thread" if self._fallback_said else pool_kind()
        if wanted == "process":
            try:
                executor = self._start_processes()
            except (OSError, ValueError, RuntimeError) as exc:
                self._fallback_said = True
                logger.warning(
                    "Pool de processus d'extraction impossible à démarrer (%s) : "
                    "extraction par threads",
                    exc,
                )
            else:
                self._kind = "process"
                return executor
        self._kind = "thread"
        return ThreadPoolExecutor(max_workers=self.max_workers)

    def _start_processes(self) -> Executor:
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        gate = context.Semaphore(OCR_MAX_CONCURRENCY)
        self._listener = QueueListener(
            queue, _ForwardToParentLoggers(), respect_handler_level=False
        )
        self._listener.start()
        return ProcessPoolExecutor(
            max_workers=self.max_workers,
            mp_context=context,
            initializer=_worker_init,
            initargs=(queue, gate, logging.getLogger().getEffectiveLevel()),
        )

    def _stop_listener(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


class _ForwardToParentLoggers(logging.Handler):
    """Rejoue dans le parent, sous leur nom d'origine, les enregistrements
    venus des travailleurs : ils passent par la configuration du parent."""

    def emit(self, record: logging.LogRecord) -> None:
        logging.getLogger(record.name).handle(record)


def _worker_init(queue: Any, gate: ProcessSemaphore, level: int) -> None:
    """Dans chaque travailleur : journaux vers le parent, verrou OCR partagé."""
    root = logging.getLogger()
    root.handlers[:] = [QueueHandler(queue)]
    root.setLevel(level)
    from docfuse.core.ocr.registry import set_ocr_gate

    set_ocr_gate(gate)


_POOL: ExtractionPool | None = None
_POOL_LOCK = threading.Lock()


def extraction_pool() -> ExtractionPool:
    """Le pool partagé du processus (créé au premier appel)."""
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = ExtractionPool()
            atexit.register(_POOL.shutdown)
        return _POOL


def reset_extraction_pool() -> None:
    """Ferme et oublie le pool partagé (tests, changement de mode)."""
    global _POOL
    with _POOL_LOCK:
        if _POOL is not None:
            _POOL.shutdown()
            _POOL = None


__all__ = [
    "POOL_ENV",
    "BrokenProcessPool",
    "ExtractionPool",
    "extraction_pool",
    "pool_kind",
    "reset_extraction_pool",
]
