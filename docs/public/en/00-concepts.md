# Concepts — understanding WPM without jargon

This document explains **what WPM does and why**, with as little technical
detail as possible. For the precise mechanics (data schema, formulas,
protocol), see [`wpm-mcp-server/README.md`](https://github.com/nohavye-dev/wpm-system/blob/main/wpm-mcp-server/README.md) and
[`02-configuration.md`](https://nohavye-dev.github.io/wpm-site/en/docs/configuration).

---

## The problem

An AI agent works in a **limited, ephemeral context**. When it discovers an
architecture decision, a code convention or a recurring bug, that information
lives in its current conversation… then disappears at the next session. Result:
every new session starts from scratch, re-reads the code, re-guesses what had
already been understood.

**WPM solves this**: it gives the agent a **persistent memory, specific to the
project**, that survives sessions.

---

## The idea in one sentence

> A shared notebook across all the agent's sessions, where each note has a
> **degree of reliability** that changes over time.

What sets WPM apart from a simple note store is that every piece of
information is **weighted**: you know how much you can trust it, and that
trust is maintained or eroded according to what happens next.

---

## The concepts, one by one

### 1. The project memory

Everything the agent considers durable about a project is recorded:
architecture decisions, conventions, bug patterns, test results. This memory
is stored **locally, in the project** (a SQLite file in a `.wpm/` folder), not
in the cloud.

*Analogy: a project-internal wiki, fed automatically while working, instead of
a hand-written documentation that quickly becomes obsolete.*

### 2. Weighted confidence

Each memory entry carries a **confidence score between 0 and 1**. An entry at
0.9 is a near-certainty; at 0.3, a fragile intuition. This score is not
decorative: it is what decides whether information is shown to the agent, and
with what weight.

*Analogy: a "to be verified" note vs a "confirmed by three sources" note. You
don't treat them the same way.*

### 3. Provenance: where does the information come from?

The **starting** confidence depends on the origin of the fact:

| Source | Starting confidence | Example |
|---|---|---|
| Official documentation read | high | "the framework docs say that…" |
| Code observed directly | medium-high | "this file does X" |
| Result of a command actually run | medium | "the test passes" |
| Agent's deduction, without proof | low | "I suppose that…" |

A hypothesis stays a hypothesis, even if it seems solid: it starts with low
confidence, and that's normal.

*Analogy: a primary source is worth more than a rumor.*

### 4. Decay

Information that has **not been confirmed for a long time** erodes: its score
slowly drops over time. The rate depends on the type of information — an
architecture decision stays reliable for ~1 year, a test result only a few
days.

*Analogy: a password noted three months ago is no longer reliable; a design
principle, on the other hand, is.*

### 5. Evidence: how confidence goes up

An entry only gains confidence through **external, verifiable evidence**: a
passing test, a second source confirming it, a reuse without failure. Simply
"thinking it's true" **never** raises the score.

*Analogy: you don't validate a hypothesis by repeating it, but by testing it.*

### 6. Contradiction, never deletion

When information turns out to be false or outdated, WPM **never deletes** the
old entry: it records a **contradiction** (with its evidence). The old entry
stays visible, its score drops faster than a confirmation would raise it — and
the history stays traceable.

*Analogy: you cross out a line in the notebook rather than tearing the page
out, to keep a record of what was revised and why.*

### 7. Hybrid retrieval (vector + graph)

When the agent looks up "everything we know about X", WPM combines two
mechanisms:
- **semantic similarity** (finding the notes that talk about the same thing,
  even with different words);
- the **link graph** (following the relations between notes to surface related
  but not identical information).

The result distinguishes **direct matches** (reliable) from **associative
context** (related, so to be mentioned cautiously).

*Analogy: a search that finds not only the exact article, but also the linked
pages that shed light on the context.*

### 8. Project rules

WPM automatically recomposes a summary of the project's **most reliable
conventions and decisions** (the "project-rules" block) and the plugin pushes
it on every turn. That is what lets it follow the project's practices without
them being re-explained every time.

*Analogy: the "house rules" page of the wiki, updated on its own from the most
reliable notes.*

### 9. Writing as you go

The agent records durable facts **as soon as they emerge**, while working,
rather than writing everything at the end (where part would already be lost).
That is what keeps the memory alive and up to date.

*Analogy: taking notes during a meeting rather than trying to reconstruct
everything a week later.*

### 10. The user profile

Alongside **project** memory, WPM keeps a memory of the **person**: a global
profile (first name, language, introduction) that follows the user across
projects and survives uninstalls. Two sources coexist there:

- **declared preferences** — what you state ("talk to me more simply"),
  recorded silently, always applied and never expiring; a contradictory new
  preference replaces the old one;
- **inferred observations** — what the agent notices itself (habits, tools,
  style, context…), stored in a closed taxonomy, injected only once a pattern
  repeats (×2) and while it stays fresh (30 days). On conflict, declared wins.

*Analogy: a long-time colleague who remembers what you asked of them
(declared) and what they observed working with you (inferred).*

---

## How it all fits together

```
              agent work:
              ┌─────────────────────────────────────────┐
              │  as you go: "hey, a durable            │
              │  fact" → store_entry (with source)     │
              └─────────────────┬───────────────────────┘
                                ▼
                      ┌────────────────────┐   each entry has a confidence that lives:
                      │  memory base       │
                      │  (local SQLite)    │     • rises (evidence)
                      └────────────────────┘     • falls (time, contradictions)
                                │
                                ▼
              ┌───────────────────────────────────────┐
              │  when the agent needs information:    │
              │  query_context → reliable notes       │
              │  surface, uncertain ones stay         │
              │  in the background or get flagged     │
              └───────────────────────────────────────┘
```

The agent does not need to "manage" the memory: it writes as it goes and
queries when it needs context. The system takes care of reliability.

---

## What it solves (goals)

- **Continuity**: sessions no longer start from zero.
- **Reliability**: what is certain is distinguished from what is assumed, and
  false information is not left to pollute decisions.
- **Traceability**: revisions and contradictions remain visible, no silent
  overwriting.
- **Zero friction**: the agent memorizes while working; no configuration to
  maintain by hand.

---

## Limitations (the project is in trial phase)

WPM is an **ongoing experiment**. The confidence model (decay rates, weights,
thresholds) is calibrated on **reasoned but still little-measured** values; it
will need to be validated on real, long-term projects. See
[`docs/internals/`](https://github.com/nohavye-dev/wpm-system/tree/main/docs/internals) for the design notes and the validation plan.

---

## To go further

- [`01-setup.md`](https://nohavye-dev.github.io/wpm-site/en/docs/setup) — install and activate WPM on a project.
- [`03-workflows.md`](https://nohavye-dev.github.io/wpm-site/en/docs/workflows) — the `wpm-learn`, `wpm-map`, `wpm-bootstrap`, `wpm-audit`, `wpm-patterns`, `wpm-persist` commands.
- [`04-agent-behavior.md`](https://nohavye-dev.github.io/wpm-site/en/docs/agent-behavior) — the details of what the agent must do.
- [`05-confidence-model.md`](https://nohavye-dev.github.io/wpm-site/en/docs/confidence-model) — why memory forgets: half-lives, provenance, evidence.
- [`wpm-mcp-server/README.md`](https://github.com/nohavye-dev/wpm-system/blob/main/wpm-mcp-server/README.md) — the technical side of the server.
