"""Every agent-facing text emitted by the MCP layer, gathered in one place.

Tool descriptions, resource descriptions, and tool_result reminders are
assembled here via PromptTask so the wording lives apart from handler
logic. Kept in English on purpose: these are agent instructions.
"""

from wpm_mcp_server.prompts.entities import PromptTask
from wpm_mcp_server.prompts.mode import push_mode


REMINDER_DEDUP = (
    PromptTask("Memory deduplication reminder")
    .add_instruction(
        "Potential contradictions were found: compare the candidate contents and prefer validating an existing near-duplicate with validate_entry instead of creating a new entry.",
    )
    .to_string()
)

REMINDER_MEMORY_FIRST = (
    PromptTask("Memory first reminder")
    .add_instruction(
        "MEMORY FIRST: call query_context on this topic before storing a new entry to check for existing or near-duplicate knowledge.",
    )
    .to_string()
)

REMINDER_VALIDATE = (
    PromptTask("Memory validation reminder")
    .add_instruction(
        "This entry is currently unvalidated: call validate_entry with external, checkable evidence once the entry has been independently confirmed.",
    )
    .add_constraint(
        "Do not use agent reasoning alone as validation evidence.",
    )
    .to_string()
)

REMINDER_CONFLICTS = (
    PromptTask("Memory conflict reminder")
    .add_instruction(
        "Conflicts were found: inspect them before relying on a direct_match.",
        "If the evidence remains contested, explicitly flag the conflict instead of presenting the fact as settled.",
    )
    .to_string()
)

STORE_ENTRY_PROMPT = (
    PromptTask("store_entry")
    .add_instruction(
        "Store exactly one durable memory entry, written in its native language as it emerged (e.g. French, keeping technical EN/FR code-switching verbatim — function names, technical terms).",
        "type: doc = explanatory project content; archi_decision = structural choice (observed or decided); convention = consistent naming/style/process rule; insight = discovered understanding durable for weeks (not a decision); bug_pattern = known issue and its cause, supported by proof; execution_result = use record_execution instead.",
        "source: official_doc = cited from an official project document; observed_code = directly observed in source code; tool_execution = confirmed by running a command or tool; agent_inference = deduction without direct external proof.",
        "Only store facts expected to remain true and useful for weeks; content must be factual, concise, self-contained, and understandable without the surrounding conversation.",
        "Immediately before calling store_entry, call query_context on the same topic.",
        "If query_context reveals a near-duplicate entry, call validate_entry on the existing entry instead of creating a duplicate when the current evidence confirms it.",
        "Every newly stored entry starts unvalidated; once independently confirmed, call validate_entry with real, external, checkable evidence.",
    )
    .add_constraint(
        "Do not store temporary observations, transient task state, speculative assumptions, or conversational context.",
        "Do not validate or increase an entry's confidence using agent reasoning alone.",
    )
    .to_string()
)

QUERY_CONTEXT_PROMPT = (
    PromptTask("query_context")
    .add_instruction(
        "Retrieve relevant project memory via hybrid retrieval (vector similarity, confidence weighting, graph centrality, 1-hop expansion).",
        "Call query_context before reading a file, running grep, or searching the codebase on the relevant topic, and at the start of every substantive answer.",
        "Write the query in the same language as the memory it targets — the embedding model is multilingual, so queries match best when they share the language of the stored content.",
        "Use direct_matches as the primary source of relevant memory; always inspect conflicts before relying on any direct_match.",
        "Use related_context for associative recall from linked entries, but treat it as lower-confidence context, not a strong direct_match.",
        "Treat an entry with an active contradicts relationship as potentially unreliable until resolved.",
        "Use min_confidence to exclude entries below the required threshold, and token_budget to control the amount of context returned.",
    )
    .add_constraint(
        "Do not assume that the absence of a result means the information does not exist in the project.",
        "Do not translate a native-language query into English: the multilingual model matches best in the original language.",
    )
    .to_string()
)

VALIDATE_ENTRY_PROMPT = (
    PromptTask("validate_entry")
    .add_instruction(
        "Record external, checkable evidence that a memory entry has been confirmed.",
        "evidence_type: execution_verified = a test/build/command/tool execution produced the expected result (strongest); cross_reference = independently confirmed by another source; reuse_without_failure = reused successfully, weak evidence subject to the confidence cap; agent_reasoning = reasoning without external proof, recorded for traceability but MUST NOT increase confidence.",
        "Set evidence_ref to the concrete source supporting the validation (test log, file path, command output, or another entry_id).",
        "Use session_id to deduplicate repeated validation of the same entry within the same session.",
        "Before validating, ensure the evidence actually supports the specific claim stored in the entry.",
    )
    .add_constraint(
        "Do not claim an entry is validated when the supplied evidence does not directly support its content.",
        "Do not use vague or unverifiable evidence_ref when a concrete source is available.",
        "Do not treat reuse_without_failure as equivalent to execution_verified or cross_reference.",
    )
    .to_string()
)

CONTRADICT_ENTRY_PROMPT = (
    PromptTask("contradict_entry")
    .add_instruction(
        "Record that entry_id is contradicted by conflicting_entry_id, using the same evidence_type rules as validate_entry.",
        "Use evidence_ref to identify the concrete evidence supporting the contradiction (test log, file path, command output, or another entry_id).",
        "Lower entry_id's validation_score (a stronger reduction than the corresponding confirmation increase) and create a visible 'contradicts' link between the two entries.",
        "Preserve both entries so future query_context calls surface the contradiction and no historical or contextual information is lost.",
    )
    .add_constraint(
        "Never delete or hide entry_id or conflicting_entry_id.",
        "Do not create a contradiction based solely on agent reasoning, or without evidence supporting the conflict.",
        "Do not treat a contradiction as proof that either entry is automatically correct.",
    )
    .to_string()
)

LINK_ENTRIES_PROMPT = (
    PromptTask("link_entries")
    .add_instruction(
        "Create or update an explicit relationship between two memory entries.",
        "relation_type: related = meaningfully related; contradicts = conflicting information; depends_on = source depends on target; refines = source adds precision, detail, or clarification to target.",
        "Preserve the direction of directional relationships (depends_on, refines).",
        "Use explicit links only for relationships semantic similarity would not reliably discover (e.g. a dependency between an archi_decision and a convention); implicit 'related' links are created automatically by store_entry.",
        "Use weight for relationship strength (default 1.0); update an existing relationship instead of duplicating it.",
    )
    .add_constraint(
        "Do not create a relationship when there is no meaningful semantic or structural connection between the entries.",
        "Do not use this tool to replace, merge, delete, or modify the content of either entry.",
        "Do not choose a relation_type merely because it is convenient; pick the one that accurately describes the relationship.",
    )
    .to_string()
)

RECORD_EXECUTION_PROMPT = (
    PromptTask("record_execution")
    .add_instruction(
        "Capture the result of a verification command as durable memory.",
        "Store the result as an execution_result entry with source=tool_execution; when succeeded, also validate it as execution_verified in the same operation.",
        # Push variant omits the resource pointer: no resource-read tool
        # exists when the plugin owns the server.
        "Call record_execution immediately after running a qualifying verification command (e.g. pytest, npm test, cargo build"
        + ("" if push_mode() else "; see the wpm://verification-commands resource for the full list")
        + ").",
        "Use succeeded to record the outcome; a failed command is preserved as evidence without being validated.",
        "Use the current session_id for every record.",
    )
    .add_constraint(
        "Do not use this tool for trivial or inspection commands (ls, cat, echo, grep, git status/diff) — exit 0 on those proves nothing.",
        "Do not claim execution_verified unless the command actually ran and succeeded.",
        "Do not use agent reasoning as a substitute for actually running the command.",
        "Do not use a fabricated, stale, or unrelated session_id.",
    )
    .to_string()
)

PIN_ENTRY_PROMPT = (
    PromptTask("pin_entry")
    .add_instruction(
        "Pin a memory entry so its confidence never decays; reserve for durable project knowledge that should stay authoritative and stable.",
        "Pin when the entry is a fundamental architecture decision, an established convention acting as policy, or knowledge independently validated repeatedly across sessions.",
        "Before pinning, verify the content is still valid and has no active contradiction; pinning is reversible via restore_entry.",
    )
    .add_constraint(
        "Do not pin recent or insufficiently validated insights, temporary bug patterns, or entries with active contradictions.",
        "Do not pin merely because an entry is frequently retrieved or important to the current task, nor solely to prevent confidence decay.",
        "Do not use pinning as a substitute for validation, or pin based solely on agent reasoning.",
    )
    .to_string()
)

DEPRECATE_ENTRY_PROMPT = (
    PromptTask("deprecate_entry")
    .add_instruction(
        "Mark a memory entry as deprecated so it is excluded from future query_context results.",
        "Deprecate only with sufficient external evidence: the entry is conclusively contradicted (with the newer entry independently confirmed), describes an element that no longer exists, or is a bug pattern conclusively fixed.",
        "Prefer caution: leave an uncertain entry active and record a contradiction or validation instead; deprecation is reversible via restore_entry.",
    )
    .add_constraint(
        "Do not deprecate merely because an entry is old, currently unused, superseded by a newer entry, or may be incorrect.",
        "Do not deprecate based solely on agent reasoning, or with an unresolved contradiction.",
        "Do not use deprecation as a replacement for contradict_entry, or to hide uncertainty.",
    )
    .to_string()
)

RESTORE_ENTRY_PROMPT = (
    PromptTask("restore_entry")
    .add_instruction(
        "Restore a pinned or deprecated memory entry to active status, preserving its existing history and evidence rather than creating a replacement.",
        "Restore a deprecated entry when the deprecation was premature or no longer justified (verify the original reason is no longer valid); restore a pinned entry when it is no longer stable or authoritative enough to stay pinned.",
        "After restoring, treat the entry's validity as normal and re-evaluate it through validation and contradiction mechanisms.",
    )
    .add_constraint(
        "Do not restore merely because an entry may be useful, or simply to undo a previous operation without reassessing its validity.",
        "Do not restore based solely on agent reasoning, and do not assume restoration makes the content validated or correct.",
    )
    .to_string()
)

LIST_ENTRIES_PROMPT = (
    PromptTask("list_entries")
    .add_instruction(
        "List memory entries with their current confidence, sorted by confidence descending, with pagination and optional filters.",
        "By default return only active and pinned entries; set status='deprecated' to include deprecated ones.",
        "type filter accepts: doc, archi_decision, insight, convention, bug_pattern, execution_result; status filter accepts: active, pinned, deprecated.",
        "Use min_confidence / max_confidence to bound the confidence range, limit (default 50, max 200) for page size, and offset to page; preserve filters across pages.",
        "Use the returned total to detect additional pages.",
        "Use list_entries to inspect, enumerate, audit, or paginate through memory — not to retrieve entries semantically related to a topic (use query_context).",
    )
    .add_constraint(
        "Do not infer that a high confidence score means an entry is correct; confidence reflects validation state, and ordering is by confidence, not relevance.",
    )
    .to_string()
)

GET_MEMORY_STATS_PROMPT = (
    PromptTask("Memory health statistics")
    .add_instruction(
        "Provides a read-only overview of the current memory store.",
        "Reports the total number of entries and their distribution by type.",
        "Reports the confidence distribution of entries using low, medium, and high confidence levels.",
        "Lists entries that have never been validated.",
        "Lists active contradiction links between entries.",
        "Reports the 5 entries with the lowest computed confidence.",
        "Reports the 10 most recent memory events.",
        "Identifies active architecture decisions and conventions that have been validated at least 3 times and have high confidence as potential pin candidates.",
    )
    .add_constraint(
        "The tool is read-only and does not modify memory.",
        "Confidence is computed from the entry type, provenance score, validation score, last validation timestamp, status, and domain settings.",
        "Confidence levels are: low < 0.3, medium 0.3-0.7, high >= 0.7.",
        "Only active architecture decisions and conventions can be returned as pin candidates.",
    )
    .to_string()
)

REMINDER_RELATED_CONTEXT = (
    "related_context is 1-hop associative recall — lower "
    "confidence than direct_matches, mention it cautiously."
)

PROJECT_RULES_PROMPT_RESOURCE = (
    PromptTask("project_rules")
    .add_instruction(
        "High-confidence project conventions and architecture decisions derived from persistent memory.",
        "Read at session start; re-read after memory changes when conventions or architecture decisions may be affected.",
        "Treat rules as derived knowledge, not immutable facts — verify against current evidence when they conflict with the project state.",
    )
    .to_string()
)

MEMORY_RULES_PROMPT_RESOURCE = (
    PromptTask("memory_rules")
    .add_instruction(
        "The complete memory usage rules (Golden Rules + standing policies).",
        "Re-read when the rules have been diluted by context growth or compaction.",
        "For tool-specific operational details, consult the relevant tool description at the moment of decision.",
    )
    .to_string()
)

VERIFICATION_COMMANDS_PROMPT_RESOURCE = (
    PromptTask("verification_commands")
    .add_instruction(
        "The configured command patterns that qualify as strong execution_verified evidence for record_execution.",
        "Consult before recording a command result as verification evidence; only matching patterns qualify.",
    )
    .to_string()
)
