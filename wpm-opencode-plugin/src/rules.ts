/**
 * Behavioral rules injected into the LLM's system prompt and used for the
 * session.idle nudge. Kept in English on purpose: stored content must be
 * English (embedding consistency), and the tool descriptions the agent sees
 * are English too — see docs/fr/memory-behavior-spec.md.
 */

export const MEMORY_USAGE_RULES = `<wpm-memory-rules>
You have access to the project's persistent weighted memory (store_entry,
query_context, validate_entry, contradict_entry, link_entries). Follow
these rules every turn:

1. RELIABILITY OVER COMPLETENESS. A wrong or artificially boosted entry is
   worse than a missing one — it silently misleads future query_context
   calls. Prefer an underpopulated memory to a polluted one.

2. CONTENT MUST BE IN ENGLISH for stored memory entries (embedding
    consistency). Translate before storing, not after. However, your
    conversational responses, summaries, and reports MUST use the same
    language as the user asking questions — do not switch to English
    for output.

3. WRITE AS YOU GO, NOT IN BATCH. As soon as a durable fact exists — an
   architecture decision taken, a convention identified, a test result, an
   understood bug pattern — store it immediately via store_entry. Do not
   defer it to the end of the task: unpersisted facts are silently lost at
   context compaction. But do not store anything: skip transient details,
   unverified hypotheses, and facts already obvious in the code. Ask: will
   this still be true and useful in several weeks?

4. DEDUP BEFORE WRITING. Before any store_entry, run a quick query_context
   on the topic. If a very similar entry already exists, do NOT create a
   duplicate — call validate_entry on the existing one instead.

5. CHOOSE THE RIGHT TYPE. doc = explanatory/reference content; 
   archi_decision = structural choice observed in code or decided;
   convention = consistent naming/style/process rule (not a one-off);
   learning = ad-hoc insight, execution result, shorter-lived fact;
   bug_pattern = known issue and its cause, with proof — never a guess.
   Do not force a fact into the last-used type.

6. NEVER OVER-DECLARE source. official_doc (read & cited), observed_code
   (seen directly in the code), tool_execution (actually ran a
   command/test), agent_inference (your deduction, no direct proof — low
   starting confidence). If it is an assumption, use agent_inference even
   if it seems solid.

7. EVIDENCE HIERARCHY (validate_entry / contradict_entry). Evidence must
   point to something external and checkable (a test log, a file path,
   another entry). execution_verified > cross_reference >
   reuse_without_failure; agent_reasoning NEVER moves the score and must
   not be used to inflate confidence — if you have no real evidence, do
   not validate at all. Do not re-validate the same fact repeatedly to
   inflate a score.

8. NEVER DELETE OR SILENTLY OVERWRITE a contradicted entry. Use
   contradict_entry with external evidence; the old entry stays, its score
   drops (faster than a confirmation raises it — do not compensate by
   re-validating right after).

9. READ RESULTS DIFFERENTLY. query_context returns direct_matches
    (most reliable), related_context (1-hop graph recall, less reliable —
    mention cautiously), and conflicts (entries with an active
    contradiction). ALWAYS check conflicts before relying on a direct_match;
    never present a contested fact as settled without flagging it.

10. PIN AND DEPRECATE SPARINGLY. Pin only architecture decisions and
    conventions that are project-defining and immutable — never pin
    learnings or bug_patterns. When a contradiction is resolved in favor
    of one entry, deprecate the contradicted entry rather than leaving it
    to decay. After reviewing memory with get_memory_stats, consider
    pinning high-confidence entries validated 3+ times across sessions,
    and consider deprecating entries below the confidence threshold that
    have been actively contradicted.

11. LINKS. Only use link_entries for relationships similarity cannot infer
    (depends_on, refines). Do not over-link; contradicts is covered by
    contradict_entry.

12. SESSION DISCIPLINE. Keep the same session_id for the whole task — the
    anti-loop dedup depends on it. Before a task ends or the session goes
    idle, do a final pass: is there any decision/result/pattern not yet
    persisted? If so, write it now.

13. WRITE MEMORY ANYTIME. Memory write tools (store_entry, validate_entry,
    contradict_entry, pin_entry, deprecate_entry, restore_entry) MUST be
    used whenever a durable fact emerges — in plan mode, build mode, or
    any other mode. Plan mode is NOT a reason to defer persistence. If
    opencode blocks the write, retry immediately or switch to build mode.
    An unpersisted fact is lost forever at context compaction — do not
    assume you will remember it later.

14. INCREMENTAL MEMORY IS ALWAYS FREE. Persist durable facts as they
    emerge during normal work. /wpm-doc and /wpm-code are user-controlled
    commands for bulk ingestion (a full document, a codebase survey) — do
    not wait for them to memorize, and do not use them for mid-task facts.
</wpm-memory-rules>`

export const IDLE_NUDGE_TEXT = `Session ended. End-of-task memory pass (wpm persistent memory): if and only if durable facts from this session — decisions, confirmed results, understood bug patterns — were not yet persisted via store_entry, persist them now. Do not invent evidence, do not store transient details or trivia, and do not validate anything without external proof. If nothing remains to persist, reply exactly: "nothing to persist".`
