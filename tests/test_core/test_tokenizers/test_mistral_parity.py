"""Vérifie que notre adaptateur produit le même compte de tokens que le
vrai `Tekkenizer` de `mistral-common` sur du texte brut.

`mistral-common` n'est PAS une dépendance du projet (voir docstring de
`core/tokenizers/mistral.py` : `pydantic-extra-types[pycountry]` est LGPL-2.1,
incompatible avec la politique zéro-copyleft du projet une fois figée dans un
exécutable onefile). Ce test est donc ignoré si le paquet n'est pas installé
dans l'environnement — il sert de garde-fou pour les mainteneurs qui
rafraîchissent le fichier de vocabulaire vendoré, pas à la CI standard.
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

mistral_common = pytest.importorskip("mistral_common")

from docfuse.core.tokenizers.mistral import _load_encoding  # noqa: E402

SAMPLES = [
    "Hello, world!",
    "Bonjour le monde, ceci est un test avec des accents éàçù.",
    "",
    "A" * 5000,
    "日本語のテキストをトークン化するテスト。",
    "def foo(x: int) -> int:\n    return x * 2\n",
    "🚀 emoji test 🎉 with combining é́ characters",
]


@pytest.mark.parametrize("text", SAMPLES)
def test_token_count_matches_reference_tekkenizer(text: str, tmp_path: Path) -> None:
    from mistral_common.tokens.tokenizers.tekken import Tekkenizer

    from docfuse.core.tokenizers.mistral import _VOCAB_PATH

    raw = tmp_path / "tekken_240911.json"
    raw.write_bytes(gzip.decompress(_VOCAB_PATH.read_bytes()))
    reference = Tekkenizer.from_file(raw)
    ref_count = len(reference.encode(text, bos=False, eos=False))
    our_count = len(_load_encoding().encode(text))

    assert our_count == ref_count
