"""Silence noisy third-party loggers (Lot 2B: deduplicate 4 clones)."""

from __future__ import annotations

import logging
import warnings


def silence_third_party() -> None:
    """Per-logger silencing (Lot 2C: keep TUI clean without touching root)."""
    for name in ("onnxruntime", "huggingface_hub", "tokenizers", "filelock"):
        lg = logging.getLogger(name)
        lg.addHandler(logging.NullHandler())
        lg.propagate = False
        lg.setLevel(logging.CRITICAL)
    warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
    warnings.filterwarnings("ignore", category=UserWarning, module="tokenizers")
