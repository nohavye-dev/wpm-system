import { buildPersistPromptText } from "../nudges"
import { buildAuditPromptText } from "./audit"
import { buildLearnPromptText } from "./learn"
import { buildMapPromptText } from "./map"
import { buildBootstrapPromptText } from "./bootstrap"
import { buildPatternPromptText } from "./patterns"

// Slash-command templates, formerly MCP prompts (server.py @mcp.prompt).
// Registered by the config hook as first-class OpenCode commands and hidden
// at execution by command.execute.before (synthetic part + short label).

export type WpmCommand = { template: string; description: string; agent?: "plan" | "build" }

export function buildCommands(language?: string, confidenceThreshold?: string): Record<string, WpmCommand> {
  return {
    "wpm-persist": {
      template: buildPersistPromptText(language),
      description: "End-of-task persistence checklist — call this yourself when a task or session is wrapping up, don't wait for the user to ask.",
    },
    "wpm-audit": {
      template: buildAuditPromptText(language, confidenceThreshold),
      description: "Review the health of the project's persistent memory (read-only dashboard).",
    },
    "wpm-learn": {
      template: buildLearnPromptText(language),
      description: "Ingest one or more markdown documents into persistent memory, chunked by section. This is for bulk ingestion of an existing document — it does not replace storing facts incrementally as they emerge during normal work.",
    },
    "wpm-map": {
      template: buildMapPromptText(language),
      description: "Map the structure, architecture and conventions of the given code directories/files into persistent memory. This is a bulk codebase survey — it does not replace storing facts incrementally as they emerge during normal work.",
    },
    "wpm-bootstrap": {
      template: buildBootstrapPromptText(language),
      description: "Bootstrap the project's persistent memory from existing artifacts (README, docs, configs, CI, structure). This is a one-time initial population.",
    },
    "wpm-patterns": {
      template: buildPatternPromptText(language),
      description: "Analyze memory for recurring patterns and suggest (and execute) new conventions or architecture decisions. This is a bulk metacognitive analysis.",
    },
  }
}
