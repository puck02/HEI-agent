"""
Lightweight sparse lexical encoder for Qdrant hybrid search.

This module intentionally has no third-party dependency. It converts Chinese text
and ASCII words/numbers into a deterministic sparse vector suitable for Qdrant's
native sparse vector index.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

from qdrant_client import models

# Named-vector fields used by Qdrant hybrid collections.
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"

# Large prime-ish bucket count to keep sparse-vector indices bounded while
# reducing hash collisions enough for a small/medium knowledge base.
SPARSE_HASH_BUCKETS = 1_000_003

_ASCII_TOKEN_RE = re.compile(r"[a-zA-Z0-9_+\-.]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _hash_token(token: str) -> int:
    """Map a token to a stable positive sparse-vector index."""
    digest = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % SPARSE_HASH_BUCKETS


def tokenize_for_sparse(text: str) -> list[str]:
    """
    Tokenize Chinese/English health text for sparse lexical retrieval.

    Strategy:
    - ASCII words/numbers are lowercased as whole tokens.
    - Chinese characters are indexed as unigrams and adjacent bigrams.
    - Short mixed health queries still keep enough exact lexical signal.
    """
    if not text:
        return []

    tokens: list[str] = []
    normalized = text.lower()

    tokens.extend(match.group(0) for match in _ASCII_TOKEN_RE.finditer(normalized))

    cjk_chars = _CJK_RE.findall(normalized)
    tokens.extend(cjk_chars)
    tokens.extend("".join(pair) for pair in zip(cjk_chars, cjk_chars[1:]))

    return [token for token in tokens if token.strip()]


def encode_sparse_text(text: str) -> models.SparseVector:
    """Encode text as a deterministic L2-normalized Qdrant SparseVector."""
    counts = Counter(_hash_token(token) for token in tokenize_for_sparse(text))
    if not counts:
        return models.SparseVector(indices=[], values=[])

    # Log-scaled term frequency keeps repeated terms useful without letting long
    # chunks dominate only because of length.
    weighted = {idx: 1.0 + math.log(freq) for idx, freq in counts.items()}
    norm = math.sqrt(sum(value * value for value in weighted.values())) or 1.0

    indices = sorted(weighted)
    values = [weighted[idx] / norm for idx in indices]
    return models.SparseVector(indices=indices, values=values)
