import sys
sys.path.insert(0, "src")

import importlib.util

from wpm_mcp_server.domain import EMBEDDING_DIM
from wpm_mcp_server.embeddings import (
    EmbeddingProvider,
    HashingEmbeddingProvider,
    PROVIDER_HASHING,
    PROVIDER_SENTENCE_TRANSFORMERS,
    SentenceTransformerProvider,
    build_provider,
    validate_embedding_dim,
)

# 1. Default -> dependency-free hashing provider, dim matches EMBEDDING_DIM
p = build_provider()
assert isinstance(p, HashingEmbeddingProvider)
assert p.dim == 384 == EMBEDDING_DIM
print("OK: default provider is hashing, dim =", p.dim)

# 2. Explicit "hashing" -> same provider
p2 = build_provider(provider="hashing")
assert isinstance(p2, HashingEmbeddingProvider)
print("OK: explicit 'hashing' provider")

# 3. Determinism + discrimination
v1a = p.embed("hello world")
v1b = p.embed("hello world")
v2 = p.embed("completely different words here")
assert v1a == v1b
assert v1a != v2
assert len(v1a) == 384
print("OK: deterministic, discriminating, 384-dim vectors")

# 4. Unknown provider -> raises
try:
    build_provider(provider="not_a_provider")
    raise AssertionError("should have raised")
except ValueError as exc:
    print("OK: unknown provider raised:", exc)

# 5. validate_embedding_dim with a tiny local stub
class StubProvider(EmbeddingProvider):
    def __init__(self, dim):
        self.dim = dim

    def embed(self, text):
        return [0.0] * self.dim

validate_embedding_dim(StubProvider(384), 384)
print("OK: matching dim passes validation")
try:
    validate_embedding_dim(StubProvider(768), 384)
    raise AssertionError("should have raised")
except ValueError as exc:
    print("OK: mismatched dim raised:", exc)

# 6. sentence_transformers only constructed when the extra is installed
if importlib.util.find_spec("sentence_transformers") is None:
    try:
        build_provider(provider="sentence_transformers")
        raise AssertionError("should have raised")
    except ImportError as exc:
        print("OK: missing extra raised:", exc)
else:
    print("SKIP: sentence_transformers installed, not constructing model in tests")

print("ALL EMBEDDINGS TESTS OK")
