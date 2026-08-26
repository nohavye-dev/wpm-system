import { SERVER_NAME } from "../core/constants"
import { expectedResponseLanguage } from "./clauses"
import { PromptTask, PromptContext } from "./entities"

// Compact, host-specific re-anchor injected into the system prompt every
// turn. Kept short on purpose: the server's initialize.instructions carry
// the golden rules + standing policies (and the wpm://memory-rules
// resource); this is only the dilution counter-measure, re-read at the
// bottom of context. Carries the expected-response-language clause so it
// sits at system level on every turn, where it wins over data language.
//
// pluginMaster omits the project-rules pull instruction: in that mode the
// rules are pushed into context every turn and no resource-read tool
// exists. Legacy (default) keeps the historical bytes.
export function buildNudge(language?: string, pluginMaster = false): string {
    const memoryPrompt = new PromptContext("wpm-memory")
        .addPurpose(
            "Use the WPM memory system as the primary source of durable project context.",
            "Maintain memory continuously throughout the session when durable knowledge emerges.",
        )

        .addInstruction(
            pluginMaster
                ? `If no <wpm-memory-recall> was pushed this turn or it is insufficient, call ${SERVER_NAME}_query_context with a reformulated query before reading files, searching the codebase, or starting a substantive answer.`
                : `Before reading files, running grep, or searching the codebase, call ${SERVER_NAME}_query_context first.`,
            `As soon as a durable fact emerges — such as a decision, convention, test result, or bug pattern — call ${SERVER_NAME}_store_entry immediately.`,
            "Memory writes are not project modifications.",
            ...(pluginMaster
                ? [`If identity or language is ambiguous, call ${SERVER_NAME}_get_user.`]
                : [`When a <current-user> block is present in context, apply its preferences (language, stated preferences); otherwise call ${SERVER_NAME}_get_user on demand.`]),
            `When the user states a preference (source=declared) or you notice a pattern about them — habit, workflow, knowledge, context, communication, or personal trait (source=inferred) — call ${SERVER_NAME}_record_user_observation, checking ${SERVER_NAME}_get_user_observations first to reinforce patterns or supersede contradicted preferences. Record silently.`,
        )
    if (!pluginMaster) {
        memoryPrompt.addInstruction(
            { before: true },
            "At session start, read the `wpm://project-rules` resource.",
        )
    }

    memoryPrompt
        .addTask(
            new PromptTask("Store durable knowledge")
                .addInstruction(
                    `Before storing an entry, call ${SERVER_NAME}_query_context to check for existing or related entries.`,
                    `Store durable facts immediately when they emerge instead of waiting until the end of the task or session.`,
                )
                .addConstraint(
                    "Store memory entries in their native language as they emerged (French, keeping technical EN/FR code-switching verbatim).",
                    "Avoid creating duplicate entries.",
                ),
        )

        .addTask(
            new PromptTask("Validate memory")
                .addInstruction(
                    `Use ${SERVER_NAME}_validate_entry when external, checkable evidence supports an existing memory entry.`,
                    `Use ${SERVER_NAME}_contradict_entry when external, checkable evidence contradicts an existing memory entry.`,
                )
                .addConstraint(
                    "Never validate or contradict an entry without external, checkable evidence.",
                    "Never use validation or contradiction operations merely to inflate a score.",
                ),
        )
        .addExpectedBehavior(
            expectedResponseLanguage(language),
        );

    return memoryPrompt.toString()
}

export function buildMemoryFirstNudge(): string {
    const memoryReminder = new PromptContext("wpm-memory")
        .addInstruction(
            `Before reading files, running grep, or searching the codebase, call ${SERVER_NAME}_query_context first.`,
        );

    return memoryReminder.toString()
}

export function buildPersistReminder(): string {
    const memoryReminder = new PromptContext("wpm-memory-reminder")
        .addTask(
            new PromptTask("Persistence")
                .addInstruction(
                    `Before this context is compacted, persist any durable knowledge from the current session that has not yet been stored.`,
                    `Use ${SERVER_NAME}_store_entry or ${SERVER_NAME}_record_execution as appropriate.`,
                )
                .addConstraint(
                    "Architecture decisions, conventions, test results, and bug patterns must not be left unpersisted.",
                    "Memory entries must be written in their native language as they emerged.",
                    "The appropriate source must be provided when persisting an entry.",
                ),
        );

    return memoryReminder.toString()
}

// Single source of truth for the background persistence pass. Used by
// both the session.idle hook and the `/wpm-persist` command. Framed as
// routine housekeeping injected between turns — never as a session end —
// and strictly silent when nothing was persisted. The reply follows the
// configured response language when one is set.
export function buildPersistPromptText(language?: string): string {
    const target = language ? language : "the user's language"

    const sweepPrompt = new PromptContext("wpm-memory-persist-sweep")
        .addPurpose(
            "Perform a memory pass for the completed turn.",
        )
        .addTask(
            new PromptTask("Persistence sweep")
                .addInstruction(
                    `Silently persist any durable facts that have not yet been persisted using ` +
                    `${SERVER_NAME}_store_entry or ${SERVER_NAME}_record_execution.`,
                )
                .addConstraint(
                    "Persist only durable facts from the session.",
                    "Relevant durable facts include decisions, confirmed results, and understood bug patterns.",
                    "Do not invent or infer evidence that was not established during the session.",
                    "Do not persist transient details or trivia.",
                    "Do not validate any memory entry without external, checkable evidence.",
                    "Never report that there was nothing to persist, and never justify an empty pass.",
                ),
        )
        .addExpectedBehavior(
            `If anything was persisted: one short line listing it, in ${target}, no conclusion.`,
            `If nothing was persisted: send no message at all.`,
        );

    return sweepPrompt.toString()
}
