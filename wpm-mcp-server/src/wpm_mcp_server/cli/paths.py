"""Shared paths for wpm CLI."""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share" / "wpm-system"))
BIN_DIR = os.environ.get("XDG_BIN_HOME", str(Path.home() / ".local" / "bin"))
