import { SERVER_NAME } from "./constants"
import { buildPersistPromptText } from "./nudges"
import { languageNote } from "./language"
import { PromptTask, PromptContext } from "./promptEntities"

// Slash-command templates, formerly MCP prompts (server.py @mcp.prompt).
// Registered by the config hook as first-class OpenCode commands and hidden
// at execution by command.execute.before (synthetic part + short label).

function buildAuditPromptText(language?: string, confidenceThreshold?: string): string {
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

function buildLearnPromptText(language?: string): string {
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
        );

    return learnPrompt.toString()
}

function buildMapPromptText(language?: string): string {
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
        );

    return mapPrompt.toString()
}

function buildBootstrapPromptText(language?: string): string {
    const bootstrapPrompt = new PromptContext("wpm-memory-bootstrap")
        .addPurpose(
            "Bootstrap the project's persistent memory from its existing project artifacts.",
            "Perform a one-time initial population of durable project knowledge while preserving the normal incremental memory workflow.",
        )
        .addInstruction(
            "Process the available project artifacts systematically before producing the final summary.",
            "Do not ask for confirmation between processing steps.",
            languageNote(language),
        )
        .addTask(
            new PromptTask("Read project documentation")
                .addInstruction(
                    "Read README.md and extract durable facts about the project's purpose and domain, technology stack, architecture, contribution guidelines, and testing or build procedures.",
                    "Search docs/, doc/, and documentation/ for relevant Markdown or reStructuredText documentation.",
                    "Extract explicit architecture decisions, documented conventions, and explicitly documented pitfalls.",
                )
                .addConstraint(
                    "Skip CHANGELOG, LICENSE, and generated documentation.",
                    "Only classify a documented pitfall as bug_pattern when the issue is explicitly documented.",
                ),
        )
        .addTask(
            new PromptTask("Inspect lint and style configuration")
                .addInstruction(
                    "Inspect applicable linting, formatting, type-checking, and style configuration files.",
                    "Consider .editorconfig, .prettierrc*, eslint.config.*, ruff.toml, .mypy.ini, tsconfig*.json, .flake8, tox.ini, .hadolint.yaml, .markdownlint.*, and biome.json when present.",
                    "Extract conventions such as indentation, quoting, line length, type strictness, and enforced rules that establish a coding standard.",
                )
                .addConstraint(
                    "Record only rules that are actually configured or enforced.",
                    "Do not infer conventions from defaults that are not configured or enforced by the project.",
                ),
        )
        .addTask(
            new PromptTask("Inspect dependencies and tooling")
                .addInstruction(
                    "Inspect pyproject.toml, package.json, Cargo.toml, go.mod, Makefile, and Justfile when present.",
                    "Identify the primary framework and runtime.",
                    "Identify the package manager.",
                    "Identify standard build, test, and lint commands.",
                )
                .addConstraint(
                    "Prefer commands explicitly defined by the project over commands inferred from ecosystem defaults.",
                    "Record the evidence source for each fact.",
                ),
        )
        .addTask(
            new PromptTask("Inspect CI/CD")
                .addInstruction(
                    "Inspect CI/CD configuration under .github/workflows/, .gitlab-ci.yml, .circleci/config.yml, and Jenkinsfile when present.",
                    "Identify the CI provider, key pipeline stages, required checks, and official build or test commands.",
                    "Use CI-defined build and test commands as the authoritative source when they conflict with commands inferred from package or project configuration.",
                )
                .addConstraint(
                    "Do not infer CI requirements from conventions that are not actually configured in the pipeline.",
                    "Do not treat locally inferred commands as authoritative when CI explicitly defines different commands.",
                ),
        )
        .addTask(
            new PromptTask("Inspect directory structure")
                .addInstruction(
                    "Inspect the top two directory levels while respecting .gitignore.",
                    "For each relevant top-level non-configuration directory, identify its likely module or architectural layer.",
                    "Inspect one or two representative files inside each directory to confirm its actual role before recording a fact.",
                )
                .addConstraint(
                    "Skip node_modules, .git, dist, build, __pycache__, .venv, target, .next, and coverage.",
                    "Do not record a convention or architecture decision based solely on a directory name.",
                    "Do not treat a directory name as architectural evidence without checking representative source files.",
                ),
        )
        .addTask(
            new PromptTask("Persist discovered facts")
                .addInstruction(
                    `Before storing each candidate fact, call ${SERVER_NAME}_query_context with min_confidence set to 0.3.`,
                    `If a direct match above approximately 0.85 already exists, call ${SERVER_NAME}_validate_entry instead of creating a duplicate.`,
                    `Use evidence_type 'cross_reference' and set evidence_ref to the relevant file path when revalidating a matching entry.`,
                    `Otherwise call ${SERVER_NAME}_store_entry with concise content in the document's native language naming the actual files or configurations supporting the fact.`,
                    "Assign the memory type that best matches the evidence.",
                    "Use the evidence source that accurately reflects how the fact was established.",
                )
                .addConstraint(
                    "Use official_doc for facts directly established by README or project documentation.",
                    "Use observed_code for facts established directly from configuration, CI, or source code.",
                    "Use agent_inference only for facts that are genuinely inferred rather than directly established.",
                    "Do not overstate the evidence source.",
                    "Do not create duplicate entries when a direct match already exists.",
                    "Do not validate an entry without supporting evidence.",
                ),
        )
        .addExpectedBehavior(
            "Provide a concise final bootstrap summary after the complete pipeline has finished.",
            "Group results by memory type.",
            "For each type, report the number of newly stored entries and the number of revalidated entries.",
            "Report facts that were considered but skipped because the available evidence was insufficient.",
        );

    return bootstrapPrompt.toString()

}

function buildPatternPromptText(language?: string): string {
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


export type WpmCommand = { template: string; description: string; agent?: "plan" | "build" }

export function buildCommands(language?: string, confidenceThreshold?: string): Record<string, WpmCommand> {
  return {
    "wpm-persist": {
      template: buildPersistPromptText(language),
      description:
        "End-of-task persistence checklist — call this yourself when a task or session is wrapping up, don't wait for the user to ask.",
    },
    "wpm-audit": {
      template: buildAuditPromptText(language, confidenceThreshold),
      description: "Review the health of the project's persistent memory (read-only dashboard).",
    },
    "wpm-learn": {
      template: buildLearnPromptText(language),
      description:
        "Ingest one or more markdown documents into persistent memory, chunked by section. This is for bulk ingestion of an existing document — it does not replace storing facts incrementally as they emerge during normal work.",
    },
    "wpm-map": {
      template: buildMapPromptText(language),
      description:
        "Map the structure, architecture and conventions of the given code directories/files into persistent memory. This is a bulk codebase survey — it does not replace storing facts incrementally as they emerge during normal work.",
    },
    "wpm-bootstrap": {
      template: buildBootstrapPromptText(language),
      description:
        "Bootstrap the project's persistent memory from existing artifacts (README, docs, configs, CI, structure). This is a one-time initial population.",
    },
    "wpm-patterns": {
      template: buildPatternPromptText(language),
      description:
        "Analyze memory for recurring patterns and suggest (and execute) new conventions or architecture decisions. This is a bulk metacognitive analysis.",
    },
  }
}