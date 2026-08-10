---
description: Ingest a markdown doc into persistent memory, chunked by section
agent: build
subtask: true
---

> Guard: if `wpm.config.json` does not exist at the project root, memory is not activated. Politely explain that the user must run `wpm enable` (then restart opencode) and stop without doing anything else.

You are ingesting a markdown document into the project's persistent memory
system (the `wpm-server` MCP server: `store_entry`, `query_context`,
`validate_entry`, `contradict_entry`, `link_entries`).

<document_path>
$ARGUMENTS
</document_path>

Follow these steps exactly:

1. **Read the file** at the given path. If no path was given, ask for one
   and stop — do not guess a file.

2. **Split it into sections** along its `##`/`###` headings (or logical
   paragraphs if it has no headings). Each section becomes ONE candidate
   memory entry. Do NOT store the whole file as a single entry — this
   destroys retrieval granularity (a single averaged vector, no way to
   link one specific section to a specific architecture decision).

3. **For each section**, before storing:
   a. Call `query_context` with a short query summarizing the section's
      topic, `min_confidence: 0.3`.
   b. If a direct_match with similarity above ~0.85 already exists and is
      clearly the same fact: do NOT create a duplicate. Instead call
      `validate_entry` on it with `evidence_type: "cross_reference"` and
      `evidence_ref` pointing to this file path — this is a re-confirmation,
      not a new fact.
   c. Otherwise, call `store_entry`:
      - `content`: the section's content, TRANSLATED TO ENGLISH if the
        source is in French (embedding consistency — see project
        conventions), rewritten concisely (no filler, no repeated
        headings), NOT a verbatim copy-paste of formatting artifacts.
      - `type`: infer the best fit —
        `doc` (default for explanatory/reference content),
        `archi_decision` (the section describes a structural choice),
        `convention` (a coding/naming/process rule),
        `bug_pattern` (a known issue and its cause).
      - `source`: `"official_doc"` (this is manual, deliberate ingestion of
        a real document, not an inference).

4. **Link related sections** to each other with `link_entries` when one
   section clearly depends on or refines another (e.g. a convention
   section that only makes sense given an architecture section earlier in
   the same doc) — don't over-link, only when the relationship is explicit
   in the text.

5. **Report back** a short summary: how many sections stored as new
   entries, how many were deduplicated/revalidated instead, and any
   section you skipped and why (e.g. too vague to be a useful standalone
   fact).

Do not ask for confirmation before each individual store_entry call — work
through the whole document, then report the summary at the end.
