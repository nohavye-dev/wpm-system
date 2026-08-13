---
description: Map the existing codebase's architecture and conventions into persistent memory
agent: build
subtask: true
---

> Guard: if `wpm.config.json` does not exist at the project root, memory is not activated. Politely explain that the user must run `wpm enable --write-config` at the project root, add the MCP server snippet it prints to the host configuration, restart the host, and stop without doing anything else.

You are mapping the structure of this codebase into the project's
persistent memory system (the `wpm-server` MCP server: `store_entry`,
`query_context`, `validate_entry`, `contradict_entry`, `link_entries`).

<scope>
$ARGUMENTS
</scope>

If `<scope>` is empty, map the whole project. If it names a path/module,
limit the mapping to that subtree.

This is NOT a file-by-file index — that would flood memory with noise and
give no retrieval value. You are extracting a small number of durable,
high-value structural facts an engineer would want recalled months later.

Follow these steps:

1. **Survey the structure** — list the directory tree of the scope
   (respecting .gitignore; skip build artifacts, node_modules, bin/obj,
   dist, .venv, etc). Identify the main layers/modules and what each is
   responsible for.

2. **Read enough real code** to ground your findings — key entry points,
   the most central classes/modules per layer, existing README/docs in
   the scope, project/config files (e.g. .csproj, package.json). Do not
   infer architecture purely from folder names without checking the code
   actually matches.

3. **Identify durable facts**, each becoming ONE candidate entry:
   - `archi_decision` — a structural choice actually observed in the code
     (e.g. "data sync pipeline separates DWG parsing (ODA SDK) from the
     API layer via an intermediate DTO"). Only record decisions you can
     point to concrete evidence for, not assumptions.
   - `convention` — a naming/style/error-handling pattern consistently
     followed across multiple files (not a one-off).
   - `bug_pattern` — only if you find a documented known issue (e.g. a
     comment, a TODO explaining a workaround, an existing issue tracker
     reference) — do not speculate about bugs you have not verified.

   Skip anything you are not reasonably confident about — a wrong
   architecture entry is worse than a missing one (it actively misleads
   future retrieval).

4. **For each candidate fact**, before storing:
   a. Call `query_context` with a short query on the topic,
      `min_confidence: 0.3`.
   b. If a very similar direct_match already exists: call `validate_entry`
      on it instead, `evidence_type: "execution_verified"` if you actually
      traced the code path, otherwise `evidence_type: "cross_reference"`,
      `evidence_ref` set to the file path(s) you checked.
   c. Otherwise `store_entry`:
      - `content`: in English, concise, naming the actual files/modules
        involved (e.g. "APCWebSystem: MassImport pipeline validates
        payloads against Astech API schema in `Services/MassImport/*`
        before persisting").
      - `type`: `archi_decision`, `convention`, or `bug_pattern` as above.
      - `source`: `"observed_code"` — this was read directly from the
        codebase, not inferred or guessed.

5. **Link entries** with `link_entries` where the relationship is explicit
   in the code (a convention that implements a stated architecture
   decision, a bug_pattern that stems from a specific archi_decision).

6. **Report back**: a short list of what was stored (grouped by type), what
   was revalidated instead of duplicated, and — importantly — anything you
   considered but skipped because you weren't confident enough to record
   it as a durable fact.

Do not ask for confirmation before each individual store_entry call — do
the full survey, then report the summary at the end.
