"""Pool d'extraction par processus (`core/workers.py`, D-111)."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import pytest

from docfuse.core import workers
from docfuse.core.orchestrator import run_analysis
from docfuse.core.workers import ExtractionPool, pool_kind, reset_extraction_pool

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _pool_propre() -> None:
    reset_extraction_pool()
    yield
    reset_extraction_pool()


def test_mode_par_defaut_processus_et_repli_par_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(workers.POOL_ENV, raising=False)
    assert pool_kind() == "process"
    monkeypatch.setenv(workers.POOL_ENV, "thread")
    assert pool_kind() == "thread"


def test_exe_gele_sur_posix_reste_en_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(workers.POOL_ENV, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(os, "name", "posix")
    assert pool_kind() == "thread"
    monkeypatch.setattr(os, "name", "nt")
    assert pool_kind() == "process"


def _extraction(paths: list[Path]) -> list[tuple[str, str, int]]:
    result = run_analysis(input_path=paths, recursive=False, tokenizer_engine="approx")
    return sorted((f.relative_path, str(f.status), len(f.text)) for f in result.files)


def test_processus_et_threads_rendent_la_meme_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le pool de processus n'est qu'une autre façon d'exécuter le même code :
    même statut, même texte, fichier par fichier."""
    paths = sorted(
        p
        for p in FIXTURES.iterdir()
        if p.is_file() and p.suffix in {".txt", ".docx", ".pdf", ".xlsx"}
    )[:8]
    assert paths
    monkeypatch.setenv(workers.POOL_ENV, "thread")
    en_threads = _extraction(paths)
    assert workers.extraction_pool().kind == "thread"
    reset_extraction_pool()
    monkeypatch.delenv(workers.POOL_ENV, raising=False)
    en_processus = _extraction(paths)
    assert workers.extraction_pool().kind == "process"
    assert en_processus == en_threads


def test_le_pool_est_reutilise_entre_deux_appels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(workers.POOL_ENV, raising=False)
    paths = sorted(p for p in FIXTURES.iterdir() if p.is_file() and p.suffix in {".txt", ".docx"})[
        :2
    ]
    assert paths
    _extraction(paths)
    pool = workers.extraction_pool()
    executor = pool._executor
    _extraction(paths)
    assert workers.extraction_pool() is pool
    assert pool._executor is executor


def _avertit(_idx: int) -> int:
    logging.getLogger("docfuse.extractors.test").warning("bonjour depuis le travailleur")
    return _idx


def test_les_journaux_des_travailleurs_remontent_au_parent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv(workers.POOL_ENV, raising=False)
    pool = ExtractionPool(max_workers=1)
    try:
        with caplog.at_level(logging.WARNING, logger="docfuse.extractors.test"):
            assert pool.submit(_avertit, 7).result(timeout=60) == 7
            deadline = time.monotonic() + 5
            while (
                "bonjour depuis le travailleur" not in caplog.text and time.monotonic() < deadline
            ):
                time.sleep(0.05)
        assert pool.kind == "process"
        assert "bonjour depuis le travailleur" in caplog.text
    finally:
        pool.shutdown()


def test_pool_casse_repli_sur_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(workers.POOL_ENV, raising=False)
    pool = ExtractionPool(max_workers=1)
    try:
        assert pool.submit(_avertit, 1).result(timeout=60) == 1
        assert pool.kind == "process"
        pool.broken("test")
        assert pool.submit(_avertit, 2).result(timeout=60) == 2
        assert pool.kind == "thread"
    finally:
        pool.shutdown()
