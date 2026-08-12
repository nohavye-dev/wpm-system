"""Embedding via ONNX runtime + HuggingFace tokenizers.

No torch — onnxruntime (~5 MB) + tokenizers (~15 MB) + model ONNX
(~80 MB cached once) replace the ~1 GB sentence-transformers/torch stack.

The default model is all-MiniLM-L6-v2 (384-dim vectors), matching the
EMBEDDING_DIM constant in domain.py. Set WPM_EMBEDDING_MODEL to override.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from wpm_mcp_server.domain import EMBEDDING_DIM

import logging as _logging
import os as _os
import warnings as _warnings
_logging.root.handlers.clear()
_logging.root.setLevel(_logging.ERROR)
_warnings.filterwarnings("ignore")
if "HF_HUB_DISABLE_IMPLICIT_TRUST" not in _os.environ:
    _os.environ["HF_HUB_DISABLE_IMPLICIT_TRUST"] = "1"

_DEFAULT_MODEL = "all-MiniLM-L6-v2"


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
        onnx_path = hf_hub_download(repo, "onnx/model.onnx")

        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        self._session = ort.InferenceSession(
            onnx_path, providers=["CPUExecutionProvider"]
        )
        self.dim = EMBEDDING_DIM

        output_info = self._session.get_outputs()[0]
        output_shape = output_info.shape
        if output_shape and len(output_shape) == 3 and output_shape[2] != EMBEDDING_DIM:
            raise ValueError(
                f"ONNX model produces {output_shape[2]}-dim token vectors "
                f"but EMBEDDING_DIM is {EMBEDDING_DIM}. Change EMBEDDING_DIM "
                f"in domain.py to match the model's output dimension."
            )

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
        token_embeddings = outputs[0]  # [batch, seq_len, dim]

        # Mean pooling with attention mask
        mask = attention_mask[:, :, None].astype(np.float64)  # [batch, seq_len, 1]
        summed = (token_embeddings.astype(np.float64) * mask).sum(axis=1)
        counts = mask.sum(axis=1)
        counts = np.clip(counts, a_min=1e-9, a_max=None)
        vec = summed / counts  # [batch, dim]

        vec = vec[0]  # [dim]
        vec = vec / (np.linalg.norm(vec) or 1.0)
        return vec.tolist()


def get_provider(model: str | None = None) -> EmbeddingProvider:
    """Build the embedding provider (ONNX runtime, no config needed)."""
    return ONNXRuntimeProvider(model or _DEFAULT_MODEL)
