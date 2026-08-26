# The confidence model — why memory forgets

WPM is not a database: it is a **weighted memory**. Every entry carries a
confidence score that decays over time and shifts with evidence. This document
explains how that score is computed, where the values come from, and how to
tune them.

---

## The formula

```
confidence(t) = min(1.0, provenance + validation) × exp(−λ × t)
```

- **provenance** — the starting confidence, set by the *source* of the
  information (see [Provenance](#provenance---the-starting-confidence));
- **validation** — the score accumulated through evidence (`validate_entry`,
  `contradict_entry`), capped with the provenance at 1.0;
- **λ** — the erosion rate tied to the entry *type* (see
  [Half-lives](#half-lives-per-entry-type));
- **t** — time since the **last validation** (each piece of evidence resets
  the decay clock).

A **pinned** entry (`pin_entry`) does not decay: its confidence stays fixed
at `min(1.0, provenance + validation)`.

The intuitive quantity behind λ is the **half-life**: the time it takes for
the confidence to drop to half its initial value.

```
half-life = ln(2) / λ ≈ 0.693 / λ
```

Confidence never goes below zero, and it stays a *weight*: a low-confidence
entry is not deleted — it simply ranks lower in query results and is excluded
from threshold blocks like `<project-rules>`.

---

## Half-lives per entry type

| Type | Half-life | Reliability of the value |
|---|---|---|
| `archi_decision` | ~1 year | domain reasoning |
| `convention` | ~6 months | domain reasoning |
| `doc` | ~4.5 months | indicative bound (not measured) |
| `insight` | ~1 month | domain reasoning |
| `bug_pattern` | ~18 days | **measured on published data** |
| `execution_result` | ~3 days | domain reasoning |

Reading: a convention stored today will still weigh ~50% in six months; a
build result, in three days. The order is not arbitrary — it mirrors how fast
each category of knowledge becomes stale in a real project.

---

## Where these values come from

Half-lives are not guessed: they are **calibrated against external anchors**,
with an explicit reliability level for each.

### Published measurement — `bug_pattern`

A bug's lifetime is approximated by its **resolution time**. An empirical
study across scientific software repositories measures a median resolution
of **18.09 days** ("What Drives Issue Resolution Speed?", arXiv 2512.18852).
Targeting confidence 0.5 at that median yields λ ≈ 0.0016/hour — the applied
value. It is a conservative bound: report → fix time underestimates the true
introduction → fix lifetime.

### Indicative bound — `doc`

Research on documentation shows that code references go stale en masse and
often stay unfixed for years (Tan & Wagner, *Empirical Software Engineering*
2023 — DOCER, analysis of 3,000+ GitHub projects). A non-peer-reviewed
industry statistic ("60% outdated within 6 months") provides a provisional
upper bound: half-life ≈ 4.5 months. To be replaced by a rigorous
measurement when available.

### Domain reasoning — the remaining types

No published anchor exists for `archi_decision`, `convention`, `insight`,
`execution_result`. Their λ values are set by domain reasoning: magnitudes
consistent with the two anchors above, and lifetimes consistent with their
nature (an architecture decision lives for years; a test result, for days).

Full sources and method: see the working note
[`../../internals/heuristic-calibration.md`](../../internals/heuristic-calibration.md).

---

## Provenance — the starting confidence

At write time, the source sets the initial score:

| Source | Initial confidence |
|---|---|
| `official_doc` | 0.9 |
| `observed_code` | 0.75 |
| `tool_execution` | 0.7 |
| `agent_inference` | 0.35 |

Information read from official documentation is born more reliable than an
agent's inference — and decays less in relative terms.

---

## Evidence — raising or lowering the score

After writing, two families of events move confidence:

- **Confirmation** (`validate_entry`) with externally checkable proof: test
  output, file path, documentation, a corroborating entry. The strongest kind
  is `execution_verified` (the fact was replayed).
- **Contradiction** (`contradict_entry`) with the same evidentiary bar —
  never a mere difference of opinion.

Each evidence type carries its own weight (tunable), and identical events are
deduplicated over a time window to prevent artificial inflation.

---

## Tuning these parameters

Everything above is configured in `wpm.config.json`, advanced section
[`domain`](https://nohavye-dev.github.io/wpm-site/en/docs/configuration): `decay` (per type), `provenance`,
`evidence`, plus the `retrieval` thresholds.

> Not to be confused with the **user profile**: inferred observations about
> the person follow their own freshness rule (dropped from the profile block
> after 30 days without reinforcement), independent of this memory-confidence
> model.
