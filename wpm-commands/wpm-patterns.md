---
description: Analyze memory for recurring patterns and suggest new conventions or architecture decisions
agent: build
subtask: true
---

> Guard: if `wpm.config.json` does not exist at the project root, memory is not activated. Politely explain that the user must run `wpm enable` (then restart opencode) and stop without doing anything else.

You are analyzing the project's persistent memory to detect recurring
patterns and identify opportunities for improvement. This is metacognitive
analysis — the memory system examining itself.

<type_filter>
$ARGUMENTS
</type_filter>

If `<type_filter>` is empty, analyze ALL entry types. If it names a type
(doc, archi_decision, learning, convention, bug_pattern), focus the
analysis on that type only.

---

## 1. Gather entries

Call `list_entries(type=<type_filter>, limit=100)` to retrieve all entries
of the target type(s).

If `total > 100`, note this in your report: "<N> entries of this type, only
the top 100 by confidence were analyzed. Consider increasing the scope by
running this again with a more specific type filter."

---

## 2. Read and categorize

Read each entry. Group them by semantic themes — not by vector similarity,
but by human judgment of what they're about. Examples:

- For `bug_pattern`: null safety, concurrency, serialization, API
  contracts, configuration errors, race conditions, memory leaks...
- For `convention`: naming, formatting, error handling, logging,
  dependency injection, test structure...
- For `archi_decision`: tech stack choices, layering, communication
  patterns, data flow, deployment...

Each entry belongs to exactly one theme. If an entry spans multiple
themes, pick the dominant one. If no clear theme emerges for a group of
fewer than 3, label it as "isolated".

---

## 3. Identify actionable patterns

For each theme with **3 or more entries**, ask:

- **Is there a root cause?** → Could a new `archi_decision` or
  `convention` prevent these entries from recurring?
- **Is there a missing rule?** → Several `bug_pattern` entries with the
  same cause suggest a `convention` that would catch them at dev time.
- **Is an existing entry being repeatedly confirmed?** → If multiple
  entries revalidate the same existing fact, suggest pinning it with
  `pin_entry`.
- **Are there lingering contradictions?** → If the same two entries
  appear in conflicts across queries, flag them for resolution.

---

## 4. Propose and execute

For each actionable pattern found, present your reasoning and propose
a concrete action. Then execute it automatically — do NOT ask for
confirmation for each action.

| Pattern | Action | Tool to call |
|---------|--------|-------------|
| 4+ bug_patterns about null safety → missing convention | Create a `convention` entry | `store_entry(type="convention", ...)` |
| Existing convention validated 3+ times → should be pinned | Pin the convention | `pin_entry(entry_id)` |
| Two entries with a long-standing contradiction → resolve it | Deprecate the weaker one | `deprecate_entry(entry_id)` |
| 3+ learnings confirm the same architecture decision → solidify it | Upgrade to `archi_decision` + pin | `store_entry(type="archi_decision")` + `pin_entry` |

For each `store_entry`: follow the standard rules (dedup via
`query_context` first, English content, `source="observed_code"` if
grounded in real entries, `source="agent_inference"` if inferred).

---

## 5. Report

Print a structured report:

```
Pattern Analysis — <type_filter or "all types">
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Analyzed: N entries across M themes

Themes found:
  <theme_1> (N entries)
  <theme_2> (N entries)
  isolated (N entries, <3 per theme)

Actions taken:
  ✓ Created archi_decision "<title>" (entry_id: abc123)
  ✓ Created convention "<title>" (entry_id: def456)
  ✓ Pinned entry ghi789 ("<content summary>")
  ✓ Deprecated entry jkl012 ("<content summary>")

No action needed for: <theme_X> — patterns are benign or already addressed.
```

If no actionable patterns were found (all themes have <3 entries, or
all patterns are already addressed), report this clearly and end.
Do NOT invent patterns where none exist — a negative result is valid.
