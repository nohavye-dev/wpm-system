import sys
sys.path.insert(0, "src")

import os

import pytest

from wpm_mcp_server.core import EMBEDDING_DIM
from wpm_mcp_server.infra.embeddings import (
    EmbeddingProvider,
    ONNXRuntimeProvider,
    get_provider,
)

# Skip ONNX tests when the hardware dependencies aren't available
# (CI / quick local smoke runs). Full tests need `pip install onnxruntime tokenizers`.
if os.environ.get("WPM_SKIP_ONNX_TEST"):
    print("SKIP: WPM_SKIP_ONNX_TEST set")
    pytest.skip("WPM_SKIP_ONNX_TEST set", allow_module_level=True)

try:
    import onnxruntime  # noqa: F401
    import tokenizers  # noqa: F401
except ImportError:
    print("SKIP: onnxruntime/tokenizers not installed")
    pytest.skip("onnxruntime/tokenizers not installed", allow_module_level=True)

# 1. Default provider, dim matches EMBEDDING_DIM
p = get_provider()
assert isinstance(p, ONNXRuntimeProvider)
assert p.dim == 384 == EMBEDDING_DIM
print("OK: default provider is ONNX, dim =", p.dim)

# 2. Determinism
v1a = p.embed("hello world")
v1b = p.embed("hello world")
v2 = p.embed("completely different words here")
assert v1a == v1b
assert len(v1a) == 384
print("OK: deterministic, 384-dim vectors")

# 3. Vectors are L2-normalized (norm ≈ 1.0)
norm = sum(x * x for x in v1a) ** 0.5
assert abs(norm - 1.0) < 1e-4, f"norm={norm}"
print("OK: L2-normalized vectors, norm =", norm)

print("ALL EMBEDDINGS TESTS OK")
