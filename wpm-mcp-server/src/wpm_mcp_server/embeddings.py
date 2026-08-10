"""Embedding provider abstraction.

The spec deliberately leaves the embedding model open ("local or a light
model, depending on the offline constraint" — spec section 10). This module
defines a minimal interface plus a dependency-free default implementation
so the server is usable and testable without a network call or a model
download.

The default `HashingEmbeddingProvider` is NOT semantically meaningful — it
is a deterministic bag-of-tokens hashing scheme, good enough to exercise
storage, retrieval plumbing, and sqlite-vec wiring end-to-end, but it will
not produce good semantic similarity. Swap in `SentenceTransformerProvider`
(or any other implementation of `EmbeddingProvider`) for real use; see
README.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from wpm_mcp_server.domain import EMBEDDING_DIM

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


class EmbeddingProvider(ABC):
    dim: int

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Return a fixed-length float vector for the given text."""


class HashingEmbeddingProvider(EmbeddingProvider):
    """Deterministic, offline, dependency-free fallback.

    Each token is hashed into a bucket of the output vector (with a sign
    derived from a second hash), then the vector is L2-normalized. This is
    a standard "feature hashing" trick — cheap and stable, but it has no
    real semantic structure. Replace it for anything beyond local testing.
    """

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = _TOKEN_RE.findall(text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector


class SentenceTransformerProvider(EmbeddingProvider):
    """Real semantic embeddings via sentence-transformers.

    Not wired in by default because it requires downloading model weights
    (network access + disk space) and an extra dependency. To use it:

        pip install sentence-transformers
        provider = SentenceTransformerProvider("all-MiniLM-L6-v2")

    all-MiniLM-L6-v2 produces 384-dim vectors, matching EMBEDDING_DIM.
    Change EMBEDDING_DIM in domain.py if you use a different model.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore

        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> list[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()


PROVIDER_HASHING = "hashing"
PROVIDER_SENTENCE_TRANSFORMERS = "sentence_transformers"


def validate_embedding_dim(provider: EmbeddingProvider, expected: int) -> None:
    """Fail fast when the provider's vector dimension mismatches the schema."""
    if provider.dim != expected:
        raise ValueError(
            f"embedding provider '{provider.__class__.__name__}' produces "
            f"{provider.dim}-dim vectors but EMBEDDING_DIM is {expected}. "
            f"Change EMBEDDING_DIM in domain.py to match the model's output "
            f"dimension, then re-embed the database (existing vectors cannot "
            f"change dimension in place)."
        )


def build_provider(
    provider: str | None = None, model: str = "all-MiniLM-L6-v2"
) -> EmbeddingProvider:
    """Build the configured embedding provider.

    provider is None/""/"hashing" for the dependency-free default, or
    "sentence_transformers" for real semantic embeddings (requires the
    `[semantic-embeddings]` extra). Unknown values raise so a typo in
    wpm.config.json fails at startup instead of silently falling back.
    """
    name = (provider or PROVIDER_HASHING).strip().lower()
    if name == PROVIDER_HASHING:
        instance: EmbeddingProvider = HashingEmbeddingProvider()
    elif name == PROVIDER_SENTENCE_TRANSFORMERS:
        try:
            instance = SentenceTransformerProvider(model)
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is not installed. Run "
                "`pip install -e \".[semantic-embeddings]\"` to enable "
                "SentenceTransformerProvider."
            ) from exc
    else:
        raise ValueError(
            f"unknown embedding provider '{provider}'. Expected one of "
            f"null, '{PROVIDER_HASHING}', or '{PROVIDER_SENTENCE_TRANSFORMERS}'."
        )
    validate_embedding_dim(instance, EMBEDDING_DIM)
    return instance


def get_default_provider() -> EmbeddingProvider:
    return build_provider()
