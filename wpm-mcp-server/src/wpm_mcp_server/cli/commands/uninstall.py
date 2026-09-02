from __future__ import annotations

import glob
import os
import shutil
from pathlib import Path

from wpm_mcp_server.cli.confirm import confirm
from wpm_mcp_server.cli.paths import BIN_DIR, DATA_DIR

_WPM_EMBEDDING_MODELS = [
    "all-MiniLM-L6-v2",
    "paraphrase-multilingual-MiniLM-L12-v2",
]


def _user_site_packages_dirs() -> list[Path]:
    base = Path.home() / ".local" / "lib"
    return [Path(p) for p in glob.glob(str(base / "python*" / "site-packages"))]


def _hf_hub_cache_dir() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    hf_home = os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
    return Path(hf_home) / "hub"


def _opencode_plugin_dir() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(config_home) / "opencode" / "plugins"


def cmd_uninstall(force: bool = False) -> None:
    if not force:
        print(
            "This will remove the server venv, data, the 'wpm' binary, the OpenCode plugin, the pip-installed server and the embedding model cache."
        )
        if not confirm("Continue? [y/N] "):
            print("wpm: aborted")
            return

    data_path = Path(DATA_DIR)
    if data_path.exists():
        shutil.rmtree(data_path)
        print(f"wpm: removed {data_path}")

    wpm_bin = Path(BIN_DIR) / "wpm"
    if wpm_bin.exists():
        wpm_bin.unlink()
        print(f"wpm: removed {wpm_bin}")

    plugin_dir = _opencode_plugin_dir()
    plugin_target = plugin_dir / "wpm-plugin.ts"
    if plugin_target.exists():
        plugin_target.unlink()
        print(f"wpm: removed {plugin_target}")
    plugin_lib = plugin_dir / "wpm-lib"
    if plugin_lib.exists():
        shutil.rmtree(plugin_lib)
        print(f"wpm: removed {plugin_lib}")

    for bin_dir in {Path.home() / ".local" / "bin", Path(BIN_DIR)}:
        wpm_mcp_bin = bin_dir / "wpm-mcp-server"
        if wpm_mcp_bin.exists():
            wpm_mcp_bin.unlink()
            print(f"wpm: removed {wpm_mcp_bin}")
    for site in _user_site_packages_dirs():
        for pattern in (
            "wpm_mcp_server",
            "wpm_mcp_server-*.dist-info",
            "__editable__.wpm_mcp_server-*.pth",
        ):
            for match in glob.glob(str(site / pattern)):
                p = Path(match)
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                print(f"wpm: removed {p}")

    hub = _hf_hub_cache_dir()
    for model in _WPM_EMBEDDING_MODELS:
        model_dir = hub / f"models--sentence-transformers--{model}"
        if model_dir.exists():
            shutil.rmtree(model_dir)
            print(f"wpm: removed embedding cache {model}")

    print("wpm: fully uninstalled")
    print("note: per-project wpm.config.json and .wpm/ databases are left in place")
    print("note: remove any 'wpm' MCP server entry from your host configurations")
