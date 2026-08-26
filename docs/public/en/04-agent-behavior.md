# Agent behavior — how to use the memory

This document describes **what the agent must do** to get the best out of the
memory once the project is activated. This is not server technology (see
[`wpm-mcp-server/README.md`](https://github.com/nohavye-dev/wpm-system/blob/main/wpm-mcp-server/README.md)),
it is the behavioral handbook.

- **The essentials** (below) are injected at the start of every session and
  reminded by the plugin at every turn.
- **The detailed reference** (further down) spells out each rule; the agent
  does not have to memorize it — the essentials are re-read at the right
  moment.

---

## The essentials

Three **golden rules**, in priority order:

1. **MEMORY FIRST** — before reading a file or searching the code, query the
   memory first (`query_context`): the answer may already be there.
2. **WRITE AS YOU GO** — as soon as a durable fact emerges (decision,
   convention, test result, understood bug), record it immediately
   (`store_entry`). Never defer it to the end.
3. **PROOF BEFORE VALIDATION** — validate or contradict only with external,
   verifiable evidence, never with reasoning alone.

**Startup sequence**: the plugin pushes golden rules, `<current-user>`
(conversation preferences) and project rules plus a RAG recall on every turn →
`query_context` on the current topic → `store_entry` as soon as a durable fact
appears → `validate_entry` with evidence once confirmed.

**Cross-cutting policies**:

- **Reliability over completeness**: a false entry is worse than a missing
  one; better an underpopulated memory than a polluted one.
- **Write at any time**: the writing tools are used in plan mode, build mode
  or any mode — the plugin grants the `wpm_*` tools in every mode, including
  plan mode. If the host still blocks a write, retry.
- **Silent user memory**: when you state a preference ("be more concise"),
  the agent records it as a **declared** preference without announcing it;
  when it notices a recurring pattern about you itself, it records it as
  **inferred** — always silently, after checking what already exists
  (reinforce or contradictory supersede). Your statements outrank its
  inferences; everything is visible and fixable via `wpm user-observations`.

> The detail of each rule (choice of type, source, evidence hierarchy…) lives
> in the **description of each tool**, re-read at every call — so applied
> without reading this document.

---

## Detailed reference

### 1. Content language

All stored `content` stays **in its native language** (the embedding model is
multilingual). Don't translate before storing. However, the agent's responses
and reports stay in the user's language — unless `response_language` is set in
the config (see [`02-configuration.md`](https://nohavye-dev.github.io/wpm-site/en/docs/configuration)).

### 2. When to write

Write **as you go**: as soon as a durable fact exists, record it without
waiting for the end of the task (an unwritten fact may disappear at
compaction). But **don't write just anything**: ask yourself "will this fact
still be true and useful in several weeks?". A transient detail, an
unverified hypothesis, an obvious fact already readable in the code: don't
create an entry.

`store_entry` returns a `potential_contradictions` field: very similar entries
already present. High similarity does not mean contradiction — it may be a
duplicate (→ `validate_entry` on the existing one) or a real contradiction
(→ `contradict_entry`). **Compare the contents** before acting.

### 3. Deduplication before writing

Before any `store_entry`, do a quick `query_context`. If a very close fact
already exists: **do not create a duplicate**, call `validate_entry` on the
existing one. A duplicate splits confidence across two entries.

### 4. Choosing the right `type`

| Type | When to use it |
|---|---|
| `doc` | Explanatory/reference content from documentation |
| `archi_decision` | Structuring choice, observed in the code or decided |
| `convention` | Naming/style/process rule followed consistently |
| `insight` | Discovered understanding, durable for weeks/months — neither a decision, nor a rule, nor copied from a doc |
| `bug_pattern` | Known problem and its cause, with proof — never a guess |
| `execution_result` | Result of a test/build/lint (via `record_execution`) — ephemeral |

Don't force a fact into an unsuitable type out of habit.

### 5. Choosing the right `source`

The `source` sets the starting confidence. Never over-declare:

| Source | When |
|---|---|
| `official_doc` | Real documentation, read and cited |
| `observed_code` | Seen directly in the code |
| `tool_execution` | Result of a command/test actually run |
| `agent_inference` | Deduction without direct proof — low starting confidence |

A hypothesis uses `agent_inference`, even if it seems solid.

### 6. Validation — evidence hierarchy

`validate_entry` / `contradict_entry` require an `evidence_type` and an
`evidence_ref` pointing to something **verifiable**.

| Evidence | Strength | Effect |
|---|---|---|
| `execution_verified` | strong | test/build/command executed, result observed |
| `cross_reference` | medium | independent confirmation by another source |
| `reuse_without_failure` | weak | reused without failure — weak signal |
| `agent_reasoning` | none | **logged, never moves the score** |

Never use `agent_reasoning` to raise confidence. Don't re-validate in a loop
to inflate a score (deduplicated per session anyway).

### 7. Contradiction — never delete

If a fact contradicts an existing entry: `contradict_entry` with external
evidence, **never** delete or overwrite. The contradicted entry's score drops
faster than a confirmation would raise it (intended).

### 8. Reading — treat results differently

- `direct_matches` — direct match, the most reliable.
- `related_context` — associative recall (1 graph hop), less reliable, to
  mention cautiously.
- `conflicts` — entries in active contradiction. **Always check before relying
  on a `direct_match`.** Never present a disputed fact as established.

### 9. Explicit links

`link_entries` only for the relations that similarity cannot guess:
`depends_on`, `refines` (`contradicts` is handled by `contradict_entry`). Don't
over-link.

### 10. Session discipline

- Stable `session_id` for a whole task (otherwise the anti-loop deduplication
  loses its effect).
- At the end of a task, do a last pass: is there any fact left
  unpersisted? Write it before considering the task complete.

### 11. Dedicated workflows

The `wpm-learn`/`wpm-map`/`wpm-bootstrap`/`wpm-audit`/`wpm-patterns` workflows are the
**controlled** ingestion; they do not replace incremental memorization. See
[`03-workflows.md`](https://nohavye-dev.github.io/wpm-site/en/docs/workflows).

### 12. Lifecycle: pin, deprecate, restore

- **`pin_entry`** — freeze the confidence (no more decay). For foundational
  decisions, imposed conventions, entries validated 3+ times (>0.7). Never an
  `insight`/`bug_pattern`/`execution_result` nor a disputed entry.
- **`deprecate_entry`** — exclude an obsolete entry (settled contradiction,
  gone code, fixed bug). Reversible.
- **`restore_entry`** — put an entry back to active status (premature
  deprecation, pin no longer justified).

### 13. What to never do

- Translate content into English before storing.
- Create an entry without checking that it doesn't already exist.
- Validate with `agent_reasoning` to inflate a score.
- Delete or overwrite a contradicted entry.
- Present a `direct_match` as reliable without checking `conflicts`.
- Defer writing an important fact "for later".
- Over-link entries with no real relation.
- Pin an `insight`/`bug_pattern`/`execution_result` or an unvalidated entry.
- Deprecate without being certain of the obsolescence.
- Ignore the problems reported by `wpm-audit`.
- Defer persistence because you're in plan mode — the `wpm_*` tools are
  allowed in plan mode.
