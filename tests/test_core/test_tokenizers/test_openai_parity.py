"""Vérifie que notre adaptateur produit le même compte de tokens que le
vrai `tiktoken.get_encoding("o200k_base")` officiel, sur du texte brut.

`tiktoken.get_encoding()` télécharge normalement son fichier depuis
openaipublic.blob.core.windows.net au premier appel. On amorce son cache
local avec notre fichier vendoré (même contenu, hash identique) pour que ce
test s'exécute entièrement hors ligne — voir `tiktoken.load.read_file_cached`
(le cache est indexé par sha1(url), peu importe l'origine du contenu tant
que le hash attendu correspond).
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from docfuse.core.tokenizers.openai import _VOCAB_PATH, _load_encoding

_O200K_URL = "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"

SAMPLES = [
    "Hello, world!",
    "Bonjour le monde, ceci est un test avec des accents éàçù.",
    "",
    "A" * 5000,
    "日本語のテキストをトークン化するテスト。",
    "def foo(x: int) -> int:\n    return x * 2\n",
    "🚀 emoji test 🎉 with combining é́ characters",
]


@pytest.fixture
def primed_tiktoken_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Amorce le cache tiktoken avec notre fichier vendoré (aucun réseau)."""
    cache_dir = tmp_path / "tiktoken_cache"
    cache_dir.mkdir()
    cache_key = hashlib.sha1(_O200K_URL.encode()).hexdigest()
    shutil.copy(_VOCAB_PATH, cache_dir / cache_key)
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(cache_dir))
    return cache_dir


@pytest.mark.usefixtures("primed_tiktoken_cache")
@pytest.mark.parametrize("text", SAMPLES)
def test_token_count_matches_reference_o200k_base(text: str) -> None:
    import tiktoken

    reference = tiktoken.get_encoding("o200k_base")
    ref_count = len(reference.encode(text, disallowed_special=()))
    our_count = len(_load_encoding().encode(text))

    assert our_count == ref_count
