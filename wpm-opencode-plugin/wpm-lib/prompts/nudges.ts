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
            `Before reading files, running grep, or searching the codebase, call ${SERVER_NAME}_query_context first.`,
            `As soon as a durable fact emerges — such as a decision, convention, test result, or bug pattern — call ${SERVER_NAME}_store_entry immediately.`,
            "Memory writes are not project modifications.",
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

// Single source of truth for the end-of-task persistence pass. Used by
// both the session.idle hook and the `/wpm-persist` command. The reply
// follows the configured response language when one is set.
export function buildPersistPromptText(language?: string): string {
    const target = language ? language : "the user's language"

    const sessionEndPrompt = new PromptContext("wpm-memory-session-end")
        .addInstruction(
            "Perform a final memory pass for the completed session.",
        )
        .addTask(
            new PromptTask("Persistence")
                .addInstruction(
                    `Persist any durable facts that have not yet been persisted using ` +
                    `${SERVER_NAME}_store_entry or ${SERVER_NAME}_record_execution.`,
                )
                .addConstraint(
                    "Persist only durable facts from the session.",
                    "Relevant durable facts include decisions, confirmed results, and understood bug patterns.",
                    "Do not invent or infer evidence that was not established during the session.",
                    "Do not persist transient details or trivia.",
                    "Do not validate any memory entry without external, checkable evidence.",
                ),
        )
        .addExpectedBehavior(
            `If nothing remains to be persisted, state in ${target} that nothing needed to be persisted.`,
            // `If nothing remains to be persisted, does nothing and does not respond.`,
            `If anything was persisted, summarize what was persisted in ${target} and state that persistence is complete.`,
        );

    return sessionEndPrompt.toString()
}
