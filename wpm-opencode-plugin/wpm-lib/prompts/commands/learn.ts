import { SERVER_NAME } from "../../core/constants"
import { languageNote } from "../clauses"
import { PromptContext, PromptTask } from "../entities"

export function buildLearnPromptText(language?: string): string {
  const learnPrompt = new PromptContext("wpm-memory-learn")
    .addPurpose(
      "Ingest Markdown documents into the project's persistent memory system.",
      `Use ${SERVER_NAME} to create, deduplicate, validate, and link persistent memory entries.`,
    )
    .addInstruction(
      "Treat the command arguments as a space-separated list of Markdown files.",
      "Process the files in the order provided.",
      "Process each document section by section rather than as a whole.",
      languageNote(language),
    )
    .addTask(
      new PromptTask("Process documents")
        .addInstruction(
          "If no file path is provided, report the expected usage and do not call any tool.",
          "If a file does not exist, report it and continue with the next file without guessing an alternative path.",
          "Split each document into sections using ## and ### headings. If the document has no headings, use logical paragraphs as sections.",
          "Treat each section as one candidate memory entry.",
          `Before processing each section, call ${SERVER_NAME}_query_context with a short query summarizing its topic and min_confidence set to 0.3.`,
          `If a direct match with similarity above approximately 0.85 is clearly the same fact, do not create a duplicate. Call ${SERVER_NAME}_validate_entry with evidence_type 'cross_reference' and evidence_ref set to the source file path.`,
          `If no clear duplicate exists, call ${SERVER_NAME}_store_entry to create a new memory entry.`,
          `When one section clearly depends on or refines another section, call ${SERVER_NAME}_link_entries to connect them.`,
          "After processing all files, report the ingestion results.",
        )
        .addConstraint(
          "Never store an entire document as a single memory entry.",
          "Each section must produce at most one candidate memory entry.",
          "Do not create a duplicate when an existing entry clearly represents the same fact.",
          "Do not assume that similar content is a duplicate unless the match is clearly the same fact.",
          "Keep source content in its native language when storing it, preserving technical terms and code as-is.",
          "Rewrite stored content concisely instead of copying formatting artifacts or irrelevant document structure.",
          "Infer the most appropriate memory type: doc by default, or archi_decision, convention, or bug_pattern when appropriate.",
          "Set the source to 'official_doc' for deliberately ingested documents.",
          "Do not over-link entries; create links only when the relationship is clear.",
          "Do not ask for confirmation before individual store operations.",
        ),
    )
    .addExpectedBehavior(
      "Provide a short ingestion summary after all files have been processed.",
      "For each file, report the number of sections stored as new entries.",
      "For each file, report the number of sections deduplicated and revalidated.",
      "Report any skipped sections and explain why they were skipped.",
    )

  return learnPrompt.toString()
}
