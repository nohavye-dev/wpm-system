# Workflows — `wpm-learn`, `wpm-map`, `wpm-bootstrap`, `wpm-audit`, `wpm-patterns`, `wpm-persist`

Six ready-to-use workflows to feed, inspect or persist the project memory.
In OpenCode, these are slash commands (e.g. `/wpm-learn`); they only run on
explicit invocation.

## Two ways of memorizing, not to be confused

- **Incremental memorization (automatic)** — while working, the agent records
  every durable fact as soon as it encounters it. This is the default
  behavior, described in [`04-agent-behavior.md`](https://nohavye-dev.github.io/wpm-site/en/docs/agent-behavior). The
  workflows do not replace it.
- **Controlled ingestion (manual)** — `wpm-learn`, `wpm-map` and `wpm-bootstrap` are for
  bringing in **in bulk** documents, a code mapping, or an initial seeding.
  Not for one-off facts of a task.

## Common guardrail

- If `wpm.config.json` does not exist, the memory is not activated: run
  `wpm enable` at the project root then restart OpenCode.
- If no path is provided to `wpm-learn` or `wpm-map`, the command only
  displays its usage and guesses nothing.

---

## `wpm-learn <paths>`

Ingests one or more markdown documents, section by section.

- Each section (`##`/`###`) becomes a candidate entry.
- **Deduplication**: before writing, the workflow checks whether the fact
  already exists; if so, it re-validates instead of creating a duplicate.
- Content **kept in its native language**, rephrased concisely (technical
  terms and code as-is).
- Type inferred (`doc`, `archi_decision`, `convention`, `bug_pattern`),
  source `official_doc`.
- Renders a **summary**: per file, sections stored / deduplicated / ignored.

## `wpm-map [scopes]`

Maps the architecture and conventions of the codebase.

- **Not a file-by-file index**: only a few structuring facts, always anchored
  in code that was actually read.
- Types: `archi_decision`, `convention`, `bug_pattern`; source
  `observed_code`.
- Same deduplication as `wpm-learn`, with a final summary (stored / re-validated /
  discarded for lack of confidence).

## `wpm-bootstrap`

Seeds the memory from the existing artifacts (README, docs, lint configs,
CI/CD, folder structure) — in a single pass. To run once per project, after
`wpm enable`, then incremental memorization takes over.

## `wpm-audit`

**Read-only** dashboard of the memory health: total per type, confidence
distribution, entries never validated, active contradictions, the 5 weakest
entries, recent activity. Ends with a verdict ("Memory is healthy" / "N
issues need attention") and may suggest actions (`pin_entry`,
`deprecate_entry`, `restore_entry`) without executing them.

## `wpm-patterns [type]`

Analyzes the memory to detect recurring patterns and proposes improvements: a
missing convention, an implicit decision, a contradiction to resolve. The
proposed actions are **executed automatically**:
- 4+ `bug_pattern` of the same cause → create a `convention`;
- a `convention` validated 3+ times → `pin_entry`;
- a long-standing contradiction → `deprecate_entry` on the weaker entry;
- 3+ `insight` confirming the same architecture decision → create an
  `archi_decision` + `pin_entry`.
If nothing emerges, the negative result is reported.

## `wpm-persist`

End-of-task persistence pass. Triggered automatically when the session goes
idle, but can also be invoked explicitly (e.g. `/wpm-persist`) to write any
durable fact left unpersisted — decisions, confirmed results, understood bug
patterns. If nothing remains to persist, it does nothing and does not respond;
otherwise it summarizes what was stored and states that persistence is complete.

---

> After an ingestion, read the summary: "discarded" facts indicate a
> deliberate filtering (too vague, too uncertain), not a failure. You can then
> reinforce the entries over the sessions (`validate_entry`,
> `contradict_entry`).
