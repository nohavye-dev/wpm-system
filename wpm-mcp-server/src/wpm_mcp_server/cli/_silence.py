"""Silence noisy third-party loggers (Lot 2B: deduplicate 4 clones)."""

from __future__ import annotations

import logging
import warnings


def silence_third_party() -> None:
    logging.root.handlers.clear()
    logging.root.addHandler(logging.NullHandler())
    logging.root.setLevel(logging.CRITICAL)
    warnings.filterwarnings("ignore")
