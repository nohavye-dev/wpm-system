import { SERVER_NAME } from "../../core/constants"
import { languageNote } from "../clauses"
import { PromptTask, PromptContext } from "../entities"

export function buildBootstrapPromptText(language?: string): string {
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
