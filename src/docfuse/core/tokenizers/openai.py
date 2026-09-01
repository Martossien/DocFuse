"""Moteur de comptage précis basé sur l'encodage o200k_base d'OpenAI.

Couvre GPT-4o, GPT-4.1 et les modèles o-série. Le fichier de vocabulaire
(`assets/o200k_base.tiktoken.gz`, gzip du fichier officiel) est le fichier officiel distribué par OpenAI
avec `tiktoken` (MIT) — même contenu, hash SHA-256 vérifié à l'identique de
celui que `tiktoken_ext.openai_public.o200k_base()` attend
(`_EXPECTED_HASH` ci-dessous). Le pattern de découpage (`_PAT_STR`) est
recopié tel quel depuis ce même module.

On ne passe pas par `tiktoken.get_encoding("o200k_base")` : cette fonction
télécharge le fichier depuis openaipublic.blob.core.windows.net au premier
appel (zéro réseau interdit, CdC §10). On charge directement notre fichier
vendoré, sans dépendre du mécanisme de cache interne de tiktoken.

Comme pour le moteur Mistral, aucun token spécial n'est enregistré : un
texte qui contiendrait littéralement "<|endoftext|>" est compté comme texte
normal plutôt que de faire lever une exception (comportement par défaut de
tiktoken pour les tokens spéciaux non autorisés).
"""

from __future__ import annotations

import base64
import gzip
import logging
from functools import lru_cache
from pathlib import Path

import tiktoken

from docfuse.core.tokenizers.base import TokenizerEngine, TokenizerEngineInfo

logger = logging.getLogger(__name__)

_VOCAB_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "o200k_base.tiktoken.gz"
"""Fichier officiel `o200k_base.tiktoken`, **compressé** (3,5 Mo → 1,7 Mo)."""

# Pattern officiel de l'encodage o200k_base (tiktoken_ext.openai_public.o200k_base).
_PAT_STR = "|".join(
    [
        r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
        r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
        r"""\p{N}{1,3}""",
        r""" ?[^\s\p{L}\p{N}]+[\r\n/]*""",
        r"""\s*[\r\n]+""",
        r"""\s+(?!\S)""",
        r"""\s+""",
    ]
)


class OpenAIEngine(TokenizerEngine):
    """Compte les tokens avec l'encodage o200k_base d'OpenAI (BPE)."""

    info = TokenizerEngineInfo(id="openai", label_key="tokenizer.openai")

    def is_available(self) -> bool:
        try:
            _load_encoding()
        except Exception:
            logger.warning(
                "Moteur de comptage OpenAI indisponible, repli sur l'approximation",
                exc_info=True,
            )
            return False
        return True

    def count_tokens(self, text: str) -> int:
        return len(_load_encoding().encode(text))


@lru_cache(maxsize=1)
def _load_encoding() -> tiktoken.Encoding:
    """Charge l'Encoding tiktoken depuis le fichier de vocabulaire vendoré."""
    mergeable_ranks: dict[bytes, int] = {}
    with gzip.open(_VOCAB_PATH, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            token_b64, rank = line.split()
            mergeable_ranks[base64.b64decode(token_b64)] = int(rank)

    return tiktoken.Encoding(
        name="o200k_base",
        pat_str=_PAT_STR,
        mergeable_ranks=mergeable_ranks,
        special_tokens={},
    )
