"""Embedding via ONNX runtime + HuggingFace tokenizers.

No torch — onnxruntime (~5 MB) + tokenizers (~15 MB) + an ONNX model
(quantized ~120 MB, or float32 ~470 MB, cached once) replace the ~1 GB
sentence-transformers/torch stack.

The default model is paraphrase-multilingual-MiniLM-L12-v2 (384-dim
vectors, 50+ languages), matching the EMBEDDING_DIM constant in
core/constants.py. A quantized ONNX export is preferred when available for the
current CPU architecture, with a fallback to the float32 export. Set
WPM_EMBEDDING_MODEL to override.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from wpm_mcp_server.core.constants import EMBEDDING_DIM

import contextlib
import logging
import os as _os
import warnings as _warnings

if "HF_HUB_DISABLE_IMPLICIT_TRUST" not in _os.environ:
    _os.environ["HF_HUB_DISABLE_IMPLICIT_TRUST"] = "1"

_logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
_ONNX_FALLBACK = "onnx/model.onnx"


def resolve_model_name() -> str:
    """Resolve the active embedding model: WPM_EMBEDDING_MODEL or default."""
    return _os.environ.get("WPM_EMBEDDING_MODEL") or _DEFAULT_MODEL


def _quantized_onnx_candidates() -> list[str]:
    """Architecture-specific quantized ONNX exports, in preference order.

    The sentence-transformers Hub repos ship one quantized export per CPU
    ISA rather than a generic int8 file, so the choice depends on the
    host. Unknown architectures return [] and fall back to float32.
    """
    import platform as _platform

    machine = _platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return ["onnx/model_qint8_arm64.onnx"]
    if machine in ("x86_64", "amd64"):
        return ["onnx/model_quint8_avx2.onnx", "onnx/model_qint8_avx512.onnx"]
    return []


class EmbeddingProvider(ABC):
    dim: int

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Return a fixed-length float vector for the given text."""


class ONNXRuntimeProvider(EmbeddingProvider):
    """Semantic embeddings via ONNX runtime.

    Downloads the ONNX model and tokenizer from the HuggingFace Hub on
    first use (cached locally). No torch required.
    """

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        repo = f"sentence-transformers/{model}"

        tokenizer_path = hf_hub_download(repo, "tokenizer.json")
        self._tokenizer = Tokenizer.from_file(tokenizer_path)

        self._session = self._load_session(ort, repo)
        self.dim = EMBEDDING_DIM

        output_info = self._session.get_outputs()[0]
        output_shape = output_info.shape
        if output_shape and isinstance(output_shape[-1], int) and output_shape[-1] != EMBEDDING_DIM:
            raise ValueError(
                f"ONNX model produces {output_shape[-1]}-dim vectors "
                f"but EMBEDDING_DIM is {EMBEDDING_DIM}. Change EMBEDDING_DIM "
                f"in core/constants.py to match the model's output dimension."
            )

    @staticmethod
    def _load_session(ort, repo: str):
        """Load the best available ONNX export: quantized first, float32 last.

        A missing quantized file (older repo layout), an architecture
        without the targeted ISA, or a session load failure each fall
        through to the next candidate.
        """
        from huggingface_hub import hf_hub_download

        candidates = [*_quantized_onnx_candidates(), _ONNX_FALLBACK]
        last_error: Exception | None = None
        for rel_path in candidates:
            try:
                onnx_path = hf_hub_download(repo, rel_path)
                return ort.InferenceSession(
                    onnx_path, providers=["CPUExecutionProvider"]
                )
            except (OSError, RuntimeError, ValueError) as exc:  # pragma: no cover - environment-dependent
                last_error = exc
                continue
        raise RuntimeError(
            f"could not load any ONNX export for {repo} "
            f"(tried {candidates})"
        ) from last_error

    def embed(self, text: str) -> list[float]:
        import numpy as np

        encoded = self._tokenizer.encode(text)
        input_names = [i.name for i in self._session.get_inputs()]

        feed = {}
        input_ids = np.array([encoded.ids], dtype=np.int64)
        attention_mask = np.array([encoded.attention_mask], dtype=np.int64)

        if "input_ids" in input_names:
            feed["input_ids"] = input_ids
        if "attention_mask" in input_names:
            feed["attention_mask"] = attention_mask
        if "token_type_ids" in input_names:
            feed["token_type_ids"] = np.zeros(
                (1, len(encoded.ids)), dtype=np.int64
            )

        outputs = self._session.run(None, feed)
        embeddings = outputs[0]

        # Sentence-transformers ONNX exports may include pooling (2D
        # [batch, dim]) or expose raw token embeddings (3D [batch, seq, dim]).
        if embeddings.ndim == 3:
            mask = attention_mask[:, :, None].astype(np.float64)  # [batch, seq_len, 1]
            summed = (embeddings.astype(np.float64) * mask).sum(axis=1)
            counts = mask.sum(axis=1)
            counts = np.clip(counts, a_min=1e-9, a_max=None)
            vec = (summed / counts)[0]  # [dim]
        elif embeddings.ndim == 2:
            vec = embeddings[0].astype(np.float64)  # [dim]
        else:
            raise ValueError(
                f"unexpected ONNX output rank {embeddings.ndim} "
                "(expected 2 or 3)"
            )

        vec = vec / (np.linalg.norm(vec) or 1.0)
        return vec.tolist()


def _debug_log_file() -> Path | None:
    """File for ONNX C++ logs when WPM_DEBUG=1, else None (Lot 2C: TUI clean + file)."""
    if _os.environ.get("WPM_DEBUG") != "1":
        return None
    from pathlib import Path

    base = _os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    log_dir = Path(base) / "wpm-system" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _logger.debug("could not create debug log dir %s: %s", log_dir, exc)
        return None
    return log_dir / "wpm-embeddings.log"


@contextlib.contextmanager
def silenced_stderr():
    """Silence fd 2 (C++ ONNX logs) leak-free; file only when WPM_DEBUG=1 (B)."""
    import os

    debug_file = _debug_log_file()
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    target = str(debug_file) if debug_file else os.devnull
    # For devnull we don't need CREAT, but it's harmless
    null_fd = os.open(target, flags, 0o644)
    saved = os.dup(2)
    try:
        os.dup2(null_fd, 2)
        yield
    finally:
        try:
            os.dup2(saved, 2)
        finally:
            os.close(saved)
            os.close(null_fd)


def get_provider(model: str | None = None) -> EmbeddingProvider:
    """Build the embedding provider (ONNX runtime, no config needed)."""
    with silenced_stderr():
        return ONNXRuntimeProvider(model or resolve_model_name())
