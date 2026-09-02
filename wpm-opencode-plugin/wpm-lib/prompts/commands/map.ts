import { SERVER_NAME } from "../../core/constants"
import { languageNote } from "../clauses"
import { PromptContext, PromptTask } from "../entities"

export function buildMapPromptText(language?: string): string {
  const mapPrompt = new PromptContext("wpm-memory-map")
    .addPurpose(
      "Map the durable structure and architecture of a codebase into persistent memory.",
      "Extract a small number of high-value structural facts that will remain useful to an engineer months later.",
    )
    .addInstruction(
      "Treat the command arguments as a space-separated list of files or directories to survey.",
      "Process each scope in the order provided.",
      "If no scope is provided, report the expected usage and do not call any tool.",
      languageNote(language),
    )
    .addTask(
      new PromptTask("Survey the codebase")
        .addInstruction(
          "Survey the structure of each provided scope.",
          "Respect .gitignore and skip generated or dependency directories such as build artifacts, node_modules, bin, obj, dist, and .venv.",
          "Identify the main architectural layers or modules and determine the responsibility of each.",
          "Read enough real code to ground the architectural findings.",
          "Inspect key entry points, central classes or modules, README and documentation files, and relevant project or configuration files.",
        )
        .addConstraint(
          "Do not infer architecture solely from directory or file names.",
          "Verify architectural findings against the actual code.",
          "Do not create a file-by-file index.",
          "Do not store low-value or transient structural details.",
        ),
    )
    .addTask(
      new PromptTask("Extract durable facts")
        .addInstruction(
          "Identify a small number of durable, high-value structural facts.",
          "Classify each candidate using the most appropriate memory type.",
          "Use archi_decision for structural choices actually observed in the code.",
          "Use convention for naming, style, or error-handling patterns consistently followed across multiple files.",
          "Use bug_pattern only for documented and verified known issues.",
        )
        .addConstraint(
          "Each durable fact must become at most one candidate memory entry.",
          "Do not speculate about architecture or bugs.",
          "Do not create a bug_pattern from an unverified suspicion.",
          "Skip facts when confidence is insufficient.",
          "A missing architecture entry is preferable to an incorrect one.",
        ),
    )
    .addTask(
      new PromptTask("Persist and verify")
        .addInstruction(
          `Before storing each candidate, call ${SERVER_NAME}_query_context with a short query about its topic and min_confidence set to 0.3.`,
          `If a very similar direct match already exists, call ${SERVER_NAME}_validate_entry instead of creating a duplicate.`,
          `Use evidence_type 'execution_verified' when the relevant code path was actually traced.`,
          `Otherwise use evidence_type 'cross_reference' and provide the checked file paths as evidence_ref.`,
          `When no sufficiently similar entry exists, call ${SERVER_NAME}_store_entry with the appropriate type and content in its native language.`,
          "Include the actual files or modules supporting the stored architectural fact.",
          `Use source 'observed_code' for entries derived from the codebase.`,
          `Call ${SERVER_NAME}_link_entries when a clear relationship between stored entries is explicitly supported by the code.`,
        )
        .addConstraint(
          "Do not create duplicate entries when an existing entry clearly represents the same fact.",
          "Do not validate an entry without evidence from the inspected code.",
          "Do not invent evidence or claim that a code path was traced when it was not.",
          "Do not create links when the relationship is merely plausible or inferred.",
          "Do not ask for confirmation before individual persistence operations.",
        ),
    )
    .addExpectedBehavior(
      "Provide a concise summary after the full survey is complete.",
      "Group newly stored entries by memory type.",
      "Report entries that were revalidated instead of duplicated.",
      "Report candidate facts that were considered but skipped because confidence was insufficient.",
    )

  return mapPrompt.toString()
}
