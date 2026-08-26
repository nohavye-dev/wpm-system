# Configuration — `wpm.config.json`

Reference for the configuration file. **In practice, you often have
nothing to write by hand**: `wpm enable` creates the file with a default
`db_path`, and most settings are optional.

---

## What you need to know first

`wpm.config.json` lives at the **root of the project**. It is the **activation
marker**: without it (nor `WPM_DB_PATH`), the server starts in **inert**
mode — it lists its tools but each call returns "wpm is not activated in this
project".

The server is registered **automatically by the OpenCode plugin** (no manual
configuration in `opencode.json`). The file is therefore mostly used to say
*where* the database lives and, if needed, to adjust a few settings.

Minimal example (often sufficient):

```json
{
  "db_path": ".wpm/wpm.db"
}
```

An absent key keeps its default value; an **unknown** key (typo) raises an
explicit error at startup rather than being ignored. Keys starting with `$`
(editor meta-data) are tolerated and ignored by the server.

---

## Editor validation (`$schema`)

A JSON Schema describes the entire configuration (types, defaults,
descriptions): `wpm-mcp-server/wpm.config.schema.json`, generated from the
server code by `scripts/generate_config_schema.py`.

Three ways to reference it through the `"$schema"` key:

| Level | Reference | Audience |
|---|---|---|
| Local machine | absolute path to `~/.local/share/wpm-system/wpm.config.schema.json` | **automatic**: `wpm enable` injects the key when it finds the local copy |
| In this repo | `"./wpm-mcp-server/wpm.config.schema.json"` | wpm-system development |
| Remote | `https://raw.githubusercontent.com/nohavye-dev/wpm-system/main/wpm-mcp-server/wpm.config.schema.json` | reference, machines without an install |

After changing server settings, regenerate schema and example:

```bash
python3 scripts/generate_config_schema.py          # writes both files
python3 scripts/generate_config_schema.py --check  # checks for drift
```

---

## Basic settings

### `db_path` — SQLite database (required)

```json
"db_path": ".wpm/wpm.db"
```

| | |
|---|---|
| Required | yes (otherwise inert server) |

Path of the SQLite file. A **relative path is resolved relative to the
directory that contains `wpm.config.json`**. The database must stay **inside
the project** (a path leaving it, including via a symlink, is refused).
Precedence: `WPM_DB_PATH` (env) > `db_path` (file).

### `confidence_threshold` — project-rules threshold (optional, default 0.5)

Confidence threshold below which an entry is not injected into the
`<project-rules>` block recomposed from the memory. Only adjustable in
the file (no env variable).

```json
"confidence_threshold": 0.6
```

### `response_language` — response language (optional, default auto)

Sets the language of the agent's **responses, summaries and reports** — **not**
the stored content, which stays in its native language (the embedding model
is multilingual).

- Absent, `null` or `"auto"`: the agent responds in the user's language.
- Fixed value (e.g. `"french"`): the agent always responds in that language.

```json
"response_language": "french"
```

Override: `WPM_RESPONSE_LANGUAGE`. The value is read at server startup
(restart required to change).

### `verification_command_patterns` — strong-evidence commands (optional, default [])

List of regexes **added** to the hard-coded list of commands whose success
counts as strong evidence (`execution_verified`) for `record_execution`.

```json
"verification_command_patterns": ["\\bmy-custom-runner\\b"]
```

Only add commands whose `exit 0` **proves** something (tests, build, lint).
**Never** add `ls`, `cat`, `echo`, `grep`, `git status`/`diff`: `exit 0` proves
nothing there.

---

## Memory pop-in (RAG)

The plugin spawns and owns the MCP server (warm embedding + rule cache).
Every turn it pushes into context: golden rules, the `<current-user>` block,
project rules, and a RAG pop-in of strongly relevant memories (recall of the
last user message). Execution recording goes through a direct warm-server call.

### `rag_similarity_threshold` — pop-in threshold (optional, default 0.35)

Minimum cosine similarity between the user's raw message and a memory
entry for it to be automatically injected into context, combined with
`confidence_threshold` as a quality guard. Lowered from 0.45 to 0.35 after
end-to-end recall calibration (see
`docs/internals/recall-rag-calibration.md`).

### `rag_max_items` — pop-in volume (optional, default 5)

Maximum number of entries injected per turn, after filtering and
deduplication against the `<project-rules>` block.

```json
"rag_similarity_threshold": 0.35,
"rag_max_items": 5
```

These two keys are only read by the plugin; the values
declared server-side exist for schema validation.

---

## Advanced: the `domain` section

**To leave aside unless you explicitly need tuning.** This section only
concerns the scoring and retrieval formulas. It is made of 6 sub-sections,
all under `"domain"`:

| Section | Rule |
|---|---|
| `provenance` | starting confidence according to `source` |
| `decay` | confidence erosion rate (λ) per `type` |
| `evidence` | how much `validation_score` moves per evidence |
| `validation` | score bounds + deduplication window |
| `retrieval` | similarity/confidence/centrality weighting |
| `expansion` | graph expansion + auto-linking thresholds |

You only replace what you need:

```json
{
  "db_path": ".wpm/wpm.db",
  "domain": {
    "retrieval": { "weight_similarity": 0.6 }
  }
}
```

The full detail of each sub-section, with its default values, is in
[`wpm-mcp-server/wpm.config.example.json`](https://github.com/nohavye-dev/wpm-system/blob/main/wpm-mcp-server/wpm.config.example.json).

---

## Environment variables

| Variable | Overrides |
|---|---|
| `WPM_CONFIG_PATH` | which JSON file is read |
| `WPM_DB_PATH` | `db_path` |
| `WPM_RESPONSE_LANGUAGE` | `response_language` |
| `WPM_EMBEDDING_MODEL` | embedding model (default `paraphrase-multilingual-MiniLM-L12-v2`) |

The `domain` keys have no env variable: only adjustable via the file.

---

## Embeddings

Embeddings use ONNX Runtime + HuggingFace tokenizers, model
`paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions, 50 languages),
pre-downloaded at install and cached. Changing the model
(`WPM_EMBEDDING_MODEL`) after inserting entries requires re-embedding the
database: run `wpm reembed` at the project root (the server refuses to query a
database whose vectors come from another model until then).
