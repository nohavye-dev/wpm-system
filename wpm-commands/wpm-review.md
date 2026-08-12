---
description: Review the health of the project's persistent memory
agent: build
subtask: true
---

> Guard: if `wpm.config.json` does not exist at the project root, memory is not activated. Politely explain that the user must run `wpm enable` (then restart opencode) and stop without doing anything else.

You are reviewing the health of this project's persistent memory system.

1. Call `get_memory_stats` — a single, read-only call that returns the full
   dashboard.

2. Present the results in a compact, scannable format:

   ```
   WPM Memory Review
   ─────────────────

   Total: <N> entries
     archi_decision: <N>   convention: <N>   doc: <N>   learning: <N>   bug_pattern: <N>

   Confidence:
     High (>0.7)     <N>
     Medium (0.3-0.7) <N>
     Low (<0.3)       <N>
   ```

3. Highlight problems under dedicated headings:

   **⚠ Entries never validated** — list them. These have never been confirmed
   by test execution, cross-reference, or reuse. They should be verified or
   downgraded.

   **⚠ Active contradictions** — for each pair, describe what is known about
   the two conflicting entries (call `query_context` on their topics if
   needed). Ask whether any of these contradictions should be resolved.

   **🔻 Lowest confidence (bottom 5)** — list each with its confidence value
   and a short content preview. Entries below the project's confidence
   threshold (read from `wpm.config.json`, default 0.5) are especially
   concerning — they are effectively invisible to most queries.

   **Recent activity** — the last 10 events (validations, contradictions,
   creations). Flag sessions where no persistence happened.

4. End with a one-line verdict: "Memory is healthy" / "N issues need attention".

Do not modify anything — this is a read-only review.
