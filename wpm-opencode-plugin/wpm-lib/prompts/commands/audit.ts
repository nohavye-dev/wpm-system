import { SERVER_NAME } from "../../core/constants"
import { PromptTask, PromptContext } from "../entities"

export function buildAuditPromptText(language?: string, confidenceThreshold?: string): string {
    const targetLanguage = language ? language : "the user's language"
    const threshold = confidenceThreshold ? confidenceThreshold : "0.5"

    const auditPrompt = new PromptContext("wpm-memory-audit")
        .addPurpose(
            `Produce the entire audit report in ${targetLanguage}.`,
            "Review the health and consistency of the project's persistent memory system.",
            "Identify memory quality problems and provide actionable recommendations without modifying the memory.",
        )
        .addInstruction(
            `Write the whole report in ${targetLanguage}: headings, explanations, analysis, recommendations, and the final verdict. Only memory entry type names (doc, archi_decision, insight, convention, bug_pattern, execution_result) and verbatim quoted entry content may stay in English, because they are stored data.`,
            `Call ${SERVER_NAME}_get_memory_stats once to retrieve the complete memory dashboard.`,
            "Present the audit as a compact, scannable report.",
        )
        .addTask(
            new PromptTask("Analyze memory health")
                .addInstruction(
                    "Report the total number of memory entries.",
                    "Provide a breakdown by entry type.",
                    "Report the confidence distribution using High (>0.7), Medium (0.3–0.7), and Low (<0.3).",
                    "List entries that have never been validated.",
                    `Review active contradictions. For each conflicting pair, describe what is known about both entries. Call ${SERVER_NAME}_query_context on their topics when additional context is needed.`,
                    "List the five entries with the lowest confidence, including their confidence score and a short preview.",
                    "Pay particular attention to entries below the project's confidence threshold.",
                    "Report the ten most recent memory events and identify sessions during which no persistence occurred.",
                )
                .addConstraint(
                    "Entry type names must remain in English because they are stored data.",
                    "Confidence buckets must be presented in the response language.",
                    `Use a confidence threshold of ${threshold}.`,
                ),
        )
        .addTask(
            new PromptTask("Recommend actions")
                .addInstruction(
                    `When problems are found, recommend concrete actions using ${SERVER_NAME}_pin_entry, ${SERVER_NAME}_deprecate_entry, or ${SERVER_NAME}_restore_entry as appropriate.`,
                    "For each recommendation, briefly explain why the action is appropriate.",
                )
                .addConstraint(
                    "Recommendations must not be executed.",
                    "Do not modify, validate, contradict, pin, deprecate, or restore any memory entry.",
                ),
        )
        .addExpectedBehavior(
            `End with a single-line verdict in ${targetLanguage}. State that the memory is healthy when no issues require attention; otherwise state the number of issues requiring attention.`,
            `The entire report must be in ${targetLanguage}, not just the verdict.`,
        );

    return auditPrompt.toString()
}
