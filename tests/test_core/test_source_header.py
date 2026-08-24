"""Tests de estimate_source_context() avec un moteur de comptage précis.

Point de vigilance perf (voir docstring de source_header.py) : avec un
moteur précis, le texte complet du fichier ne doit être encodé qu'une seule
fois pendant la convergence de l'en-tête, pas jusqu'à 20 fois.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.core.tokenizers.base import TokenizerEngine, TokenizerEngineInfo
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus
from docfuse.output.source_header import build_source_header, estimate_source_context


class _CountingEngine(TokenizerEngine):
    """Moteur factice (1 token/mot) qui journalise chaque appel."""

    info = TokenizerEngineInfo(id="fake", label_key="tokenizer.fake")

    def __init__(self) -> None:
        self.calls: list[str] = []

    def is_available(self) -> bool:
        return True

    def count_tokens(self, text: str) -> int:
        self.calls.append(text)
        return len(text.split())


def _make_file(text: str) -> ExtractedFile:
    return ExtractedFile(
        path=Path("/tmp/doc.txt"),
        relative_path="doc.txt",
        extension="txt",
        file_type="text",
        size_bytes=len(text.encode("utf-8")),
        text=text,
        status=FileStatus.READY,
    )


class TestEstimateSourceContextWithPreciseEngine:
    def test_large_file_text_is_encoded_only_once(self) -> None:
        engine = _CountingEngine()
        text = "mot " * 5000
        f = _make_file(text)

        estimate_source_context(f, margin=0.15, engine=engine)

        full_text_calls = [c for c in engine.calls if c == text]
        assert len(full_text_calls) == 1

        header_only_calls = [c for c in engine.calls if c != text]
        assert header_only_calls  # convergence de l'en-tête a bien eu lieu
        assert all(len(c) < 500 for c in header_only_calls)

    def test_converges_to_a_fixed_point(self) -> None:
        engine = _CountingEngine()
        f = _make_file("un texte de taille normale pour ce test")

        estimate = estimate_source_context(f, margin=0.15, engine=engine)

        # Invariant de convergence : header_tokens (recalculé à partir des
        # valeurs retournées) + text_tokens == tokens_estimated retourné.
        from docfuse.output.source_header import _render_source_header

        header = _render_source_header(f, estimate.tokens_estimated, estimate.tokens_with_margin)
        text_tokens = engine.count_tokens(f.text)
        header_tokens = engine.count_tokens(f"{header}\n\n")
        assert header_tokens + text_tokens == estimate.tokens_estimated

    def test_bytes_utf8_reflects_header_and_text(self) -> None:
        engine = _CountingEngine()
        f = _make_file("texte court")

        estimate = estimate_source_context(f, margin=0.15, engine=engine)

        assert estimate.bytes_utf8 > len(f.text.encode("utf-8"))  # en-tête inclus


class TestEstimateSourceContextApproxUnchanged:
    def test_approx_path_still_reencodes_full_concatenation(self) -> None:
        # Comportement historique : gratuit avec octets/4, donc pas
        # d'optimisation nécessaire — on vérifie juste que ça fonctionne
        # toujours sans moteur explicite.
        f = _make_file("un petit texte de test")
        estimate = estimate_source_context(f, margin=0.15, engine=None)
        assert estimate.tokens_estimated > 0
        assert estimate.bytes_utf8 > len(f.text.encode("utf-8"))


class TestSourceHeaderExtraMetadata:
    def test_header_renders_secret_alert(self) -> None:
        f = _make_file("texte")
        f.extra_metadata["secrets_detected"] = "clé AWS (ligne 2)"
        header = build_source_header(f, margin=0.15)
        assert "clé AWS (ligne 2)" in header

    def test_header_renders_duplicate_note(self) -> None:
        f = _make_file("texte")
        f.extra_metadata["duplicate_of"] = "original.docx"
        header = build_source_header(f, margin=0.15)
        assert "original.docx" in header

    def test_header_without_extra_metadata_unchanged(self) -> None:
        f = _make_file("texte")
        header = build_source_header(f, margin=0.15)
        assert "doublon" not in header.lower()
        assert "secret" not in header.lower()
