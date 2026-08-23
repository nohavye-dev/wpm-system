# Installation and activation

WPM is installed once (globally), then activated project by project. The
OpenCode plugin is installed **by default** and registers the MCP server for
you: no manual OpenCode configuration is needed.

---

## 1. Global installation

```bash
curl -fsSL https://raw.githubusercontent.com/nohavye-dev/wpm-system/main/install.sh | bash
```

What the script does:

1. creates a dedicated Python environment (`~/.local/share/wpm-system/venv`) and
   installs the server in it;
2. pre-downloads the embedding model (~120 MB) for a first start
   offline;
3. installs the `wpm` command (`~/.local/bin/wpm`);
4. installs the OpenCode plugin in `~/.config/opencode/plugins/` (global).

> The paths honor `$XDG_DATA_HOME` / `$XDG_BIN_HOME` /
> `$XDG_CONFIG_HOME` if they are defined.

---

## 2. Activating a project

From the root of the project concerned:

```bash
wpm enable
```

`wpm enable` writes `wpm.config.json` at the root of the project
(confirmation; `--yes` to skip it):

- default `db_path` `.wpm/wpm.db` if absent (existing keys are preserved);
- creates the database folder and adds it to `.gitignore`;
- creates the database;
- refuses a `db_path` that leaves the project (external absolute path, or
  relative with `..`).

For a custom database folder:

```bash
wpm enable .memory   # → db_path ".memory/wpm.db"
```

> The `db_dir` only matters on a **first** activation: if a `db_path` already
> exists, it is preserved.

---

## 3. What happens next

At the next OpenCode start on this project, the plugin detects the
`wpm.config.json` and:

1. registers the `wpm` MCP server (tools `wpm_store_entry`,
   `wpm_query_context`, …);
2. grants the `wpm_*` permission so the agent can write the memory, even in
   plan mode.

**Restart OpenCode** after `wpm enable` (or `wpm disable`): the
configuration is only read once at startup.

---

## 4. Verifying it works

- In OpenCode, the agent must see the `wpm_*` tools.
- From the terminal, in the activated project:

```bash
wpm search "name of a topic"      # queries the memory
```

Without activation, the tools reply "wpm is not activated in this
project".

---

## 5. Disabling / uninstalling

```bash
wpm disable      # removes wpm.config.json (data is kept)
wpm uninstall    # complete global removal (venv, binary, plugin); --force to skip the confirmation
```

---

## 6. Backup and restore

```bash
wpm export > wpm-backup.json                        # exports the database to JSON (without embeddings)
wpm generate wpm-backup.json --output .wpm/wpm.db   # rebuilds a database (re-encodes embeddings)
```

Out of session: `wpm export` backs up the entries to JSON, `wpm generate`
rebuilds a database from an export (embeddings recomputed).

---

## For the curious — how the plugin registers the server

It is the plugin's `config` hook that, at load time, injects into the
OpenCode configuration an `mcp.wpm` entry pointing to
`python -m wpm_mcp_server` with `WPM_CONFIG_PATH` set to the project's
`wpm.config.json`, plus the `wpm_*` permission. So you have **nothing to
declare** in `opencode.json`. To wire the server manually (outside OpenCode,
or to understand), see
[`wpm-mcp-server/README.md`](https://github.com/nohavye-dev/wpm-system/blob/main/wpm-mcp-server/README.md).
