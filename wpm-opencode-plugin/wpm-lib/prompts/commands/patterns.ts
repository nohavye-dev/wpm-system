import { SERVER_NAME } from "../../core/constants"
import { PromptTask, PromptContext } from "../entities"

export function buildPatternPromptText(language?: string): string {
    const targetLanguage = language ? language : "the user's language"
    const patternsPrompt = new PromptContext("wpm-memory-patterns")
        .addPurpose(
            `Produce the entire patterns report in ${targetLanguage}.`,
            "Analyze the project's persistent memory to detect recurring patterns and identify opportunities for improvement.",
            "Perform metacognitive analysis: use the memory system to evaluate and improve the memory system itself.",
        )
        .addInstruction(
            "Treat $ARGUMENTS as an optional memory type filter. When empty, analyze all memory types.",
            `Call ${SERVER_NAME}_list_entries with the requested type filter and a limit of 100. Omit the type filter when $ARGUMENTS is empty.`,
            "If more than 100 entries exist for the selected scope, report that only the 100 highest-confidence entries were analyzed.",
            `Write the whole report in ${targetLanguage}: theme descriptions, explanations, action justifications, and the final summary. Entry type names and verbatim quoted entry content may stay in English, and newly stored memory entries remain in their native language.`,
        )
        .addTask(
            new PromptTask("Identify themes")
                .addInstruction(
                    "Group memory entries into semantic themes using human judgment.",
                    "Assign each entry to exactly one theme.",
                    "Label themes containing fewer than three entries as isolated.",
                )
                .addConstraint(
                    "Do not use vector similarity as the sole basis for thematic grouping.",
                    "Do not assign an entry to multiple themes.",
                    "Do not manufacture themes from unrelated entries.",
                ),
        )
        .addTask(
            new PromptTask("Identify actionable patterns")
                .addInstruction(
                    "For each theme containing at least three entries, look for recurring and actionable patterns.",
                    "Identify root causes that suggest a missing architecture decision or convention.",
                    "Identify missing rules indicated by multiple bug patterns sharing the same cause.",
                    "Identify entries that have been repeatedly confirmed.",
                    "Identify long-standing contradictions that should be resolved.",
                )
                .addConstraint(
                    "Do not infer an actionable pattern from fewer than three related entries.",
                    "Do not invent patterns when the evidence does not support one.",
                    "A negative result is valid: a theme may require no action.",
                ),
        )
        .addTask(
            new PromptTask("Apply improvements")
                .addInstruction(
                    "For each actionable pattern, explain the reasoning before applying the corresponding action.",
                    `When four or more bug patterns share the same cause, create a convention using ${SERVER_NAME}_store_entry.`,
                    `When a convention has been validated at least three times, call ${SERVER_NAME}_pin_entry.`,
                    `When a contradiction is long-standing, call ${SERVER_NAME}_deprecate_entry on the weaker entry.`,
                    `When three or more insights confirm the same architecture decision, create an archi_decision using ${SERVER_NAME}_store_entry and then pin it with ${SERVER_NAME}_pin_entry.`,
                    `Before every ${SERVER_NAME}_store_entry call, use ${SERVER_NAME}_query_context to check for duplicates.`,
                )
                .addConstraint(
                    "Execute applicable actions automatically without asking for confirmation.",
                    "Only execute an action when its stated evidence threshold is satisfied.",
                    "Do not create duplicate memory entries.",
                    "Store new memory content in its native language.",
                    "Use source 'observed_code' when the pattern is grounded in existing memory entries that represent real observed code.",
                    "Use source 'agent_inference' when the pattern is inferred rather than directly grounded in observed code.",
                    "Do not execute an action merely because a theme exists; the required pattern must be demonstrated.",
                ),
        )
        .addExpectedBehavior(
            "Provide a structured summary after the analysis and all applicable actions are complete.",
            "List the themes found and the number of entries in each theme.",
            "List the actions that were taken and briefly explain why each action was justified.",
            "List themes that were analyzed but required no action.",
            "If no actionable patterns were found, state this clearly and end the report.",
            `The entire report must be in ${targetLanguage}, not just the final summary.`,
        );

    return patternsPrompt.toString()
}
