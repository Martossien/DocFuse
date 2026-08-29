"""Non-régression de l'audit D-098 (lot 3 : performance, sortie identique).

Les gains ont été mesurés sur des dossiers réels (voir journal-decisions.md)
et l'identité byte-à-byte du corpus vérifiée ; ces tests verrouillent les
invariants dont cette identité dépend.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from docfuse.core.embedded_images import ImageBatch
from docfuse.core.inventory import _walk_source, list_ignored, scan_directory
from docfuse.core.ocr.base import OcrEngine, OcrEngineInfo
from docfuse.core.orchestrator import run_analysis


class _SlowTagEngine(OcrEngine):
    """Moteur factice : renvoie le texte encodé dans l'image, après un délai
    inversement proportionnel à l'index — les résultats arrivent dans le
    DÉSORDRE si l'implémentation ne préserve pas l'ordre de soumission."""

    info = OcrEngineInfo(id="fake", label_key="ocr.tesseract")

    def __init__(self) -> None:
        self.calls = 0
        self.max_parallel = 0
        self._running = 0
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        return True

    def ocr_image(self, image_bytes: bytes, lang: str) -> str:
        del lang  # même signature que les vrais moteurs, langue sans effet ici
        with self._lock:
            self.calls += 1
            self._running += 1
            self.max_parallel = max(self.max_parallel, self._running)
        text = image_bytes.decode()
        time.sleep(0.05 if text.endswith("0") else 0.005)
        with self._lock:
            self._running -= 1
        return "" if text == "EMPTY" else f"ocr:{text}"


class TestImageBatch:
    def test_markers_follow_document_order_despite_parallel_ocr(self) -> None:
        engine = _SlowTagEngine()
        batch = ImageBatch(engine, want_export=False)
        parts = ["intro"]
        for i in range(6):
            parts.append(batch.add(f"doc__img{i}.png", f"img{i}".encode()))
            parts.append(f"para{i}")

        resolved = batch.resolve(parts)

        assert [p for p in resolved if p.startswith("[[IMAGE")] == [
            f"[[IMAGE — texte OCR (tesseract, fra+eng)]]\nocr:img{i}" for i in range(6)
        ]
        assert resolved[0] == "intro"
        assert resolved[2] == "para0"
        assert engine.calls == 6
        assert engine.max_parallel > 1

    def test_empty_result_drops_token_and_export_follows_marker(self) -> None:
        engine = _SlowTagEngine()
        batch = ImageBatch(engine, want_export=True)
        t1 = batch.add("a.png", b"EMPTY")
        t2 = batch.add("b.png", b"hello")

        resolved = batch.resolve(["x", t1, "y", t2])

        # Export actif : même une image sans texte OCR garde son tag.
        assert resolved == [
            "x",
            "[[IMAGE: a.png]]",
            "y",
            "[[IMAGE: b.png — texte OCR (tesseract, fra+eng)]]\nocr:hello",
        ]
        assert [img.filename for img in batch.images] == ["a.png", "b.png"]

        no_export = ImageBatch(engine, want_export=False)
        t3 = no_export.add("c.png", b"EMPTY")
        assert no_export.resolve(["x", t3, "y"]) == ["x", "y"]
        assert no_export.images == []

    def test_no_engine_no_export_is_a_noop(self) -> None:
        batch = ImageBatch(None, want_export=False)
        assert not batch.active
        token = batch.add("a.png", b"data")
        assert batch.resolve(["x", token]) == ["x"]

    def test_take_moves_an_image_out_of_the_batch(self) -> None:
        engine = _SlowTagEngine()
        batch = ImageBatch(engine, want_export=True)
        token = batch.add("cell.png", b"cell")
        candidate = batch.take(token)
        assert candidate is not None
        assert candidate.tag == "cell.png"
        assert batch.take(token) is None  # déjà retiré
        assert batch.resolve([token, "rest"]) == ["rest"]
        assert batch.images == []


class TestEstimateCache:
    def test_recompute_engine_reuses_cached_estimates(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text(
            "Texte de test suffisamment long pour compter.", encoding="utf-8"
        )
        (tmp_path / "b.txt").write_text("Un second fichier avec du texte.", encoding="utf-8")
        result = run_analysis(tmp_path, context_limit=128000)
        approx = list(result.estimates)

        result.recompute_engine("openai")
        openai = list(result.estimates)
        result.recompute_engine("approx")
        assert result.estimates == approx
        assert set(result._estimates_by_engine) == {"approx", "openai"}

        assert result.remove_file(tmp_path / "a.txt", reason="test")
        # Toutes les listes en cache restent alignées sur `files`.
        assert all(len(v) == len(result.files) for v in result._estimates_by_engine.values())
        result.recompute_engine("openai")
        assert result.estimates == openai[1:]


class TestSingleWalk:
    def test_walk_source_matches_public_functions(self, tmp_path: Path) -> None:
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "x.js").write_text("x", encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.md").write_text("c", encoding="utf-8")

        found, ignored = _walk_source(tmp_path, True, None, None, 12)

        assert sorted(found) == sorted(scan_directory(tmp_path))
        assert sorted(ignored) == sorted(list_ignored(tmp_path))
        assert {p.name for p, _ in ignored} == {"photo.jpg", "node_modules"}
