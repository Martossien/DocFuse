"""Moteur de comptage précis basé sur le tokenizer Tekken de Mistral AI.

Le fichier de vocabulaire (`assets/tekken_240911.json.gz`, gzip du JSON d'origine) est extrait du paquet
`mistral-common` (Apache-2.0, voir NOTICE) — on n'installe pas ce paquet lui-même :
il tire `pydantic-extra-types[pycountry]`, et `pycountry` est sous licence
LGPL-2.1, incompatible avec la politique zéro-copyleft du projet (CdC NFR-06)
une fois figée dans un exécutable PyInstaller onefile (pas de liaison dynamique
possible dans ce cas, cf. la même remarque du CdC à propos de PySide6).

Le tokenizer Tekken s'appuie en interne sur le moteur BPE de `tiktoken` (MIT) :
on reconstruit ici le même `tiktoken.Encoding` à partir du même vocabulaire, ce
qui donne un compte de tokens strictement identique à celui de
`mistral_common.tokens.tokenizers.tekken.Tekkenizer.encode()` pour du texte brut
(voir tests/test_core/test_tokenizers/test_mistral_parity.py). Zéro réseau :
tout est chargé depuis le fichier local embarqué.
"""

from __future__ import annotations

import base64
import gzip
import json
import logging
from functools import lru_cache
from pathlib import Path

import tiktoken

from docfuse.core.tokenizers.base import TokenizerEngine, TokenizerEngineInfo

logger = logging.getLogger(__name__)

_VOCAB_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "tekken_240911.json.gz"
"""Vocabulaire Tekken tel que distribué par mistral-common, **compressé** (19 Mo → 2,6 Mo
dans le paquet et l'exécutable ; décompression ~0,1 s au premier comptage)."""


class MistralEngine(TokenizerEngine):
    """Compte les tokens avec le vocabulaire Tekken de Mistral AI (BPE)."""

    info = TokenizerEngineInfo(id="mistral", label_key="tokenizer.mistral")

    def is_available(self) -> bool:
        try:
            _load_encoding()
        except Exception:
            logger.warning(
                "Moteur de comptage Mistral indisponible, repli sur l'approximation",
                exc_info=True,
            )
            return False
        return True

    def count_tokens(self, text: str) -> int:
        return len(_load_encoding().encode(text))


@lru_cache(maxsize=1)
def _load_encoding() -> tiktoken.Encoding:
    """Reconstruit l'Encoding tiktoken du tokenizer Tekken de Mistral.

    Réplique la logique de `Tekkenizer._reload_mergeable_ranks` (Apache-2.0,
    mistral-common) sans installer ce paquet — voir le docstring du module.
    """
    with gzip.open(_VOCAB_PATH, "rt", encoding="utf-8") as fh:
        data = json.load(fh)

    config = data["config"]
    vocab_size = int(config["default_vocab_size"])
    num_special_tokens = int(config["default_num_special_tokens"])
    inner_vocab_size = vocab_size - num_special_tokens

    mergeable_ranks: dict[bytes, int] = {
        base64.b64decode(entry["token_bytes"]): int(entry["rank"])
        for entry in data["vocab"][:inner_vocab_size]
    }

    return tiktoken.Encoding(
        name="tekken_240911",
        pat_str=str(config["pattern"]),
        mergeable_ranks=mergeable_ranks,
        special_tokens={},
    )
