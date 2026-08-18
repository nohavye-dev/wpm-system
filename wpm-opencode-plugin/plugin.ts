import type { Plugin } from "@opencode-ai/plugin"
import { $ } from "bun"
import { existsSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"

// Name under which the wpm MCP server is registered (by this plugin's
// config hook). MCP tools are namespaced as `<server>_<tool>` (e.g.
// wpm_query_context), so this must match the registered server name.
const SERVER_NAME = "wpm"

// Compact, host-specific re-anchor injected into the system prompt every
// turn. Kept short on purpose: the server's initialize.instructions carry
// the golden rules + standing policies (and the wpm://memory-rules
// resource); this is only the dilution counter-measure, re-read at the
// bottom of context.
function buildNudge(): string {
  return [
    "<wpm-memory>",
    `MEMORY FIRST: before reading files, running grep, or searching the codebase, call ${SERVER_NAME}_query_context first.`,
    `WRITE AS YOU GO: as soon as a durable fact emerges (decision, convention, test result, bug pattern), call ${SERVER_NAME}_store_entry immediately — English content, dedup via ${SERVER_NAME}_query_context first.`,
    `PROOF BEFORE VALIDATION: call ${SERVER_NAME}_validate_entry / ${SERVER_NAME}_contradict_entry only with external, checkable evidence; never to inflate a score.`,
    `At session start, read the wpm://project-rules resource.`,
    "</wpm-memory>",
  ].join("\n")
}

function buildMemoryFirstNudge(): string {
  return [
    "<wpm-memory>",
    `MEMORY FIRST: before reading files, running grep, or searching the codebase, call ${SERVER_NAME}_query_context first.`,
    "</wpm-memory>",
  ].join("\n")
}

function buildPersistReminder(): string {
  return [
    "<wpm-memory-reminder>",
    "Before this context is compacted: if any architecture decision, convention, test result, or bug pattern from this session has not yet been persisted, call " +
      `${SERVER_NAME}_store_entry (or ${SERVER_NAME}_record_execution) now, in English, with the appropriate source.`,
    "</wpm-memory-reminder>",
  ].join("\n")
}

// Single source of truth for the end-of-task persistence pass. Used by
// both the session.idle hook and the `/wpm-persist` command.
const PERSIST_PROMPT_TEXT =
  "Session ended. End-of-task memory pass (wpm persistent memory): if " +
  "and only if durable facts from this session — decisions, confirmed " +
  "results, understood bug patterns — were not yet persisted via " +
  `${SERVER_NAME}_store_entry or ${SERVER_NAME}_record_execution, persist them now. ` +
  "Do not invent evidence, do not store transient details or trivia, and do " +
  "not validate anything without external proof. If nothing remains to " +
  'persist, reply exactly: "Nothing to persist." else give a summary of ' +
  'what was persisted and say exactly: "Persistence complete."'

// Slash-command templates, formerly MCP prompts (server.py @mcp.prompt).
// Registered by the config hook as first-class OpenCode commands and hidden
// at execution by command.execute.before (synthetic part + short label).
const AUDIT_TEMPLATE = `You are reviewing the health of this project's persistent memory system.

1. Call \`${SERVER_NAME}_get_memory_stats\` — a single, read-only call that returns the full dashboard.

2. Present the results in a compact, scannable format:

   WPM Memory Review
   Total: <N> entries
     archi_decision: <N>   convention: <N>   doc: <N>   insight: <N>   bug_pattern: <N>   execution_result: <N>
   Confidence: High (>0.7) <N> / Medium (0.3-0.7) <N> / Low (<0.3) <N>

3. Highlight problems under dedicated headings:
   - 'Entries never validated' — list them; they should be verified or downgraded.
   - 'Active contradictions' — for each pair, describe what is known about the two conflicting entries (call ${SERVER_NAME}_query_context on their topics if needed). Ask whether any should be resolved.
   - 'Lowest confidence (bottom 5)' — list each with its confidence and a short preview; entries below the project's confidence threshold (read from wpm.config.json, default 0.5) are especially concerning.
   - 'Recent activity' — the last 10 events; flag sessions where no persistence happened.

4. If the dashboard reveals problems, suggest concrete actions (${SERVER_NAME}_pin_entry, ${SERVER_NAME}_deprecate_entry, ${SERVER_NAME}_restore_entry) — do not execute them.

5. End with a one-line verdict: 'Memory is healthy' / 'N issues need attention'.

Do not modify anything — this is a read-only review.`

const LEARN_TEMPLATE = `You are ingesting markdown documents into the project's persistent memory system (the wpm MCP server: ${SERVER_NAME}_store_entry, ${SERVER_NAME}_query_context, ${SERVER_NAME}_validate_entry, ${SERVER_NAME}_contradict_entry, ${SERVER_NAME}_link_entries).

USAGE: learn <path-to-doc.md> [more-docs.md ...] — ingest one or more markdown files, section by section, into persistent memory.

Paths: $ARGUMENTS

If no path is given, reply with this usage message and do NOT call any tool.

Follow these steps exactly:

1. Treat $ARGUMENTS as a space-separated list of files. Process each file in order. If a file does not exist, say so and move on to the next — do not guess a file.

2. For each file, split it into sections along its ##/### headings (or logical paragraphs if it has no headings). Each section becomes ONE candidate memory entry. Do NOT store a whole file as a single entry — this destroys retrieval granularity.

3. For each section, before storing:
   a. Call ${SERVER_NAME}_query_context with a short query summarizing the section's topic, min_confidence: 0.3.
   b. If a direct_match with similarity above ~0.85 already exists and is clearly the same fact: do NOT create a duplicate. Call ${SERVER_NAME}_validate_entry on it with evidence_type 'cross_reference' and evidence_ref pointing to this file path.
   c. Otherwise, call ${SERVER_NAME}_store_entry:
      - content: the section's content, TRANSLATED TO ENGLISH if the source is not English (embedding consistency), rewritten concisely, not a verbatim copy of formatting artifacts;
      - type: infer the best fit — doc (default), archi_decision, convention, bug_pattern;
      - source: 'official_doc' (manual, deliberate ingestion of a real document).

4. Link related sections to each other with ${SERVER_NAME}_link_entries when one section clearly depends on or refines another — don't over-link.

5. Report back a short summary: for each file, how many sections stored as new entries, how many deduplicated/revalidated instead, and any section skipped and why.

Do not ask for confirmation before each individual ${SERVER_NAME}_store_entry call — work through the whole list, then report the summary at the end.`

const MAP_TEMPLATE = `You are mapping the structure of this codebase into the project's persistent memory system (the wpm MCP server: ${SERVER_NAME}_store_entry, ${SERVER_NAME}_query_context, ${SERVER_NAME}_validate_entry, ${SERVER_NAME}_contradict_entry, ${SERVER_NAME}_link_entries).

USAGE: map <path-or-dir> [more-paths ...] — survey the given directories/files and store durable structural facts.

Scopes to map: $ARGUMENTS

If no scope is given, reply with this usage message and do NOT call any tool.

This is NOT a file-by-file index — that would flood memory with noise and give no retrieval value. You are extracting a small number of durable, high-value structural facts an engineer would want recalled months later.

Follow these steps:

1. Treat $ARGUMENTS as a space-separated list of directories/files. For each one, survey the structure — list its directory tree (respecting .gitignore; skip build artifacts, node_modules, bin/obj, dist, .venv, etc). Identify the main layers/modules and what each is responsible for.

2. Read enough real code to ground your findings — key entry points, the most central classes/modules per layer, existing README/docs in each scope, project/config files. Do not infer architecture purely from folder names without checking the code actually matches.

3. Identify durable facts, each becoming ONE candidate entry:
   - archi_decision — a structural choice actually observed in the code;
   - convention — a naming/style/error-handling pattern consistently followed across multiple files;
   - bug_pattern — only if you find a documented known issue; never speculate about bugs you have not verified.
   Skip anything you are not reasonably confident about — a wrong architecture entry is worse than a missing one.

4. For each candidate fact, before storing:
   a. Call ${SERVER_NAME}_query_context with a short query on the topic, min_confidence: 0.3.
   b. If a very similar direct_match already exists: call ${SERVER_NAME}_validate_entry on it instead, evidence_type 'execution_verified' if you actually traced the code path, otherwise 'cross_reference' with evidence_ref set to the file path(s) you checked.
   c. Otherwise ${SERVER_NAME}_store_entry with type archi_decision, convention, or bug_pattern, content in English naming the actual files/modules, source 'observed_code'.

5. Link entries with ${SERVER_NAME}_link_entries where the relationship is explicit in the code.

6. Report back: what was stored (grouped by type), what was revalidated instead of duplicated, and anything you considered but skipped because you weren't confident enough.

Do not ask for confirmation before each individual ${SERVER_NAME}_store_entry call — do the full survey, then report the summary at the end.`

const BOOTSTRAP_TEMPLATE = `You are bootstrapping this project's persistent memory from its existing artifacts: README, documentation, configuration files, CI/CD pipelines, and directory structure. This is a one-time initial population — the normal incremental persist-as-you-work behavior continues alongside it.

Follow these steps exactly:

1. README: read README.md and extract durable facts: project purpose/domain (doc or archi_decision), key dependencies/tech stack (archi_decision), architectural overview (archi_decision), contribution guidelines (convention), testing/build instructions (insight).

2. Documentation: search docs/, doc/, documentation/. Read relevant .md/.rst files (skip CHANGELOG, LICENSE, generated docs). Extract explicit architecture decisions (archi_decision), documented conventions (convention), documented pitfalls (bug_pattern only if explicitly documented).

3. Lint and style config: .editorconfig, .prettierrc*, eslint.config.*, ruff.toml, .mypy.ini, tsconfig*.json, .flake8, tox.ini (flake8), .hadolint.yaml, .markdownlint.*, biome.json. Extract conventions: indentation, quotes, line length, strictness, enforced rules implying a coding standard.

4. Dependencies and tooling: pyproject.toml / package.json / Cargo.toml / go.mod / Makefile / Justfile. Extract primary framework/runtime (archi_decision), package manager (convention), standard build/test/lint commands (insight).

5. CI/CD: .github/workflows/, .gitlab-ci.yml, .circleci/config.yml, Jenkinsfile. Extract provider, key stages, required checks; if CI defines official test/build commands, they supersede package-config inference.

6. Directory structure: list the top 2 levels respecting .gitignore (skip node_modules, .git, dist, build, __pycache__, .venv, target, .next, coverage). For each top-level non-config directory, name the module/layer and infer its role — check 1-2 files inside to confirm before recording anything. Do NOT record a convention or archi_decision based solely on a directory name.

7. Persist each fact: before storing, call ${SERVER_NAME}_query_context (min_confidence: 0.3). If a direct_match above ~0.85 already exists, ${SERVER_NAME}_validate_entry with evidence_type 'cross_reference' and evidence_ref = the file path. Otherwise ${SERVER_NAME}_store_entry: content in English naming actual files/configs, correct type, and the source that matches the evidence (rule 7, never over-declare): official_doc for facts read from README or docs, observed_code for facts read directly in configs, CI or code, agent_inference for anything inferred or assumed.

8. Report: group stored entries by type with counts (stored vs revalidated), plus any facts skipped because evidence was too thin.

Do not ask for confirmation between steps — work through the full pipeline, then report the summary at the end.`

const PATTERNS_TEMPLATE = `You are analyzing the project's persistent memory to detect recurring patterns and identify opportunities for improvement. This is metacognitive analysis — the memory system examining itself.

Type filter: $ARGUMENTS (leave empty to analyze all types)

1. Gather entries: call ${SERVER_NAME}_list_entries(type=$ARGUMENTS, limit=100) for the target type(s) — omit the type when the filter is empty. If total > 100, note in your report that only the top 100 by confidence were analyzed.

2. Read and categorize: group entries by semantic themes using human judgment (not vector similarity). Each entry belongs to exactly one theme; if fewer than 3 entries share a theme, label them 'isolated'.

3. Identify actionable patterns for each theme with 3+ entries: a root cause suggesting a new archi_decision or convention; a missing rule (several bug_patterns with the same cause); an entry repeatedly confirmed (suggest ${SERVER_NAME}_pin_entry); lingering contradictions to resolve.

4. Propose and execute: for each actionable pattern, present your reasoning then execute it automatically — do NOT ask for confirmation per action:
   - 4+ bug_patterns with the same cause -> create a convention (${SERVER_NAME}_store_entry, type convention);
   - convention validated 3+ times -> ${SERVER_NAME}_pin_entry;
   - long-standing contradiction -> ${SERVER_NAME}_deprecate_entry the weaker one;
   - 3+ insights confirming the same architecture decision -> ${SERVER_NAME}_store_entry (type archi_decision) + ${SERVER_NAME}_pin_entry.
   For each ${SERVER_NAME}_store_entry follow the standard rules: dedup via ${SERVER_NAME}_query_context first, English content, source 'observed_code' if grounded in real entries, 'agent_inference' if inferred.

5. Report a structured summary: themes found (with counts), actions taken, and themes needing no action. Do NOT invent patterns where none exist — a negative result is valid.

If no actionable patterns are found, report this clearly and end.`

type WpmCommand = { template: string; description: string }
const WPM_COMMANDS: Record<string, WpmCommand> = {
  "wpm-persist": {
    template: PERSIST_PROMPT_TEXT,
    description:
      "End-of-task persistence checklist — call this yourself when a task or session is wrapping up, don't wait for the user to ask.",
  },
  "wpm-audit": {
    template: AUDIT_TEMPLATE,
    description: "Review the health of the project's persistent memory (read-only dashboard).",
  },
  "wpm-learn": {
    template: LEARN_TEMPLATE,
    description:
      "Ingest one or more markdown documents into persistent memory, chunked by section. This is for bulk ingestion of an existing document — it does not replace storing facts incrementally as they emerge during normal work.",
  },
  "wpm-map": {
    template: MAP_TEMPLATE,
    description:
      "Map the structure, architecture and conventions of the given code directories/files into persistent memory. This is a bulk codebase survey — it does not replace storing facts incrementally as they emerge during normal work.",
  },
  "wpm-bootstrap": {
    template: BOOTSTRAP_TEMPLATE,
    description:
      "Bootstrap the project's persistent memory from existing artifacts (README, docs, configs, CI, structure). This is a one-time initial population.",
  },
  "wpm-patterns": {
    template: PATTERNS_TEMPLATE,
    description:
      "Analyze memory for recurring patterns and suggest (and execute) new conventions or architecture decisions. This is a bulk metacognitive analysis.",
  },
}

function isEnabled(directory: string): boolean {
  return existsSync(join(directory, "wpm.config.json"))
}

// Resolve the wpm server venv Python the same way install.sh lays it out
// (DATA_DIR = $XDG_DATA_HOME/wpm-system, default ~/.local/share/wpm-system).
function resolvePythonPath(): string {
  const dataHome = process.env.XDG_DATA_HOME ?? join(homedir(), ".local", "share")
  return join(dataHome, "wpm-system", "venv", "bin", "python")
}

export const WpmPlugin: Plugin = async ({ client, directory }) => {
  if (!isEnabled(directory)) {
    return {}
  }

  const nudge = buildNudge()
  const persistReminder = buildPersistReminder()
  const nudged = new Set<string>()
  const queriedRecently = new Map<string, boolean>()

  return {
    // Register the wpm MCP server so the user does not have to declare it
    // in opencode.json. WPM_CONFIG_PATH pins the project config regardless
    // of the process cwd. Also grant plan-mode write permission.
    config: async (config) => {
      config.mcp = config.mcp ?? {}
      if (!config.mcp["wpm"]) {
        config.mcp["wpm"] = {
          type: "local",
          command: [resolvePythonPath(), "-m", "wpm_mcp_server"],
          environment: { WPM_CONFIG_PATH: join(directory, "wpm.config.json") },
          enabled: true,
        }
      }
      const permission = (config.permission ??= {}) as Record<string, unknown>
      if (!permission["wpm_*"]) {
        permission["wpm_*"] = "allow"
      }
      const commands = (config.command ??= {})
      for (const [name, def] of Object.entries(WPM_COMMANDS)) {
        if (!commands[name]) {
          commands[name] = {
            template: def.template,
            description: def.description,
            agent: "plan",
          }
        }
      }
    },

    // Slash commands run first-class: replace the long instruction prompt
    // with a short visible label so the /wpm commands read cleanly.
    "command.execute.before": async (input, output) => {
      if (!(input.command in WPM_COMMANDS)) return
      for (const part of output.parts ?? []) {
        if (part.type === "text") part.synthetic = true
      }
      const label = ["/" + input.command, input.arguments].filter(Boolean).join(" ")
      output.parts.unshift({ type: "text", text: label } as any)
    },

    // Re-arm the end-of-task persist net when a real user message arrives,
    // so a session that continues after a persist pass gets persisted again.
    // Our own injected prompts carry metadata.wpm_injected so they do not
    // count as real user input.
    "chat.message": async (input, output) => {
      const injected = (output.parts ?? []).some(
        (p) => p.type === "text" && p.metadata?.wpm_injected === true,
      )
      if (!injected) nudged.delete(input.sessionID)
    },

    // Re-inject the golden rules at every LLM turn so they cannot be
    // diluted by context growth — the deterministic push a pure MCP server
    // cannot provide.
    "experimental.chat.system.transform": async (_input, output) => {
      output.system.push(nudge)
    },

    // Re-anchor at the exact moment of loss: when the session is compacted,
    // persist anything still unpersisted and restore the rules.
    "experimental.session.compacting": async (_input, output) => {
      output.context.push(persistReminder)
      output.context.push(nudge)
    },

    // Rule 16 (record executions) — deterministic, no model involved: every
    // bash command that looks like a verification command is recorded via
    // the CLI. Also tracks query_context usage for the conditional
    // memory-first nudge below.
    "tool.execute.after": async (input, output) => {
      if (input.tool === `${SERVER_NAME}_query_context`) {
        queriedRecently.set(input.sessionID, true)
        return
      }
      if (input.tool !== "bash") return
      const command = String(input.args?.command ?? "")
      const succeeded = output.metadata?.exit === 0
      await $`wpm record-execution ${command} --succeeded=${succeeded} --session-id=${input.sessionID}`
        .quiet()
        .nothrow()
    },

    // Conditional memory-first nudge: only when about to read/search without
    // having queried memory recently — instead of nagging every turn.
    "tool.execute.before": async (input, _output) => {
      if (!["read", "grep", "glob"].includes(input.tool)) return
      if (queriedRecently.get(input.sessionID)) return
      await client.session.prompt({
        path: { id: input.sessionID },
        body: {
          noReply: true,
          parts: [
            {
              type: "text",
              text: buildMemoryFirstNudge(),
              synthetic: true,
              metadata: { wpm_injected: true },
            },
          ],
        },
      })
    },

    // End-of-task net: actively trigger the persistence pass when a working
    // session goes idle, rather than only logging a reminder nobody reads.
    event: async ({ event }) => {
      if (event.type !== "session.idle") return
      const sessionID: string | undefined = (event as any).properties?.sessionID
      if (!sessionID || nudged.has(sessionID)) return
      nudged.add(sessionID)
      await client.session.prompt({
        path: { id: sessionID },
        body: {
          noReply: false,
          agent: "plan",
          parts: [
            {
              type: "text",
              text: PERSIST_PROMPT_TEXT,
              synthetic: true,
              metadata: { wpm_injected: true },
            },
          ],
        },
      })
    },
  }
}

export default WpmPlugin
