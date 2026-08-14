import type { Plugin } from "@opencode-ai/plugin"
import { existsSync } from "node:fs"
import { join } from "node:path"

// Name under which the wpm MCP server is registered in opencode.json.
// MCP tools are namespaced as `<server>_<tool>` (e.g. wpm_query_context),
// so this must match the key of the server entry.
const SERVER_NAME = "wpm"

// Compact, host-specific re-anchor injected into the system prompt every
// turn. Kept short on purpose: the full 16 rules live in the server's
// initialize.instructions (and the wpm://memory-rules resource); this is
// only the dilution counter-measure, re-read at the bottom of context.
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

function buildPersistReminder(): string {
  return [
    "<wpm-memory-reminder>",
    "Before this context is compacted: if any architecture decision, convention, test result, or bug pattern from this session has not yet been persisted, call " +
      `${SERVER_NAME}_store_entry (or ${SERVER_NAME}_record_execution) now, in English, with the appropriate source.`,
    "</wpm-memory-reminder>",
  ].join("\n")
}

function isEnabled(directory: string): boolean {
  return existsSync(join(directory, "wpm.config.json"))
}

export const WpmPlugin: Plugin = async ({ client, directory }) => {
  if (!isEnabled(directory)) {
    return {}
  }

  const nudge = buildNudge()
  const persistReminder = buildPersistReminder()
  const nudged = new Set<string>()

  return {
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

    // End-of-task net: log a reminder when a working session goes idle.
    event: async ({ event }) => {
      if (event.type !== "session.idle") return
      const properties = (event as any).properties ?? {}
      const sessionID: string | undefined = properties.sessionID
      if (!sessionID || nudged.has(sessionID)) return
      nudged.add(sessionID)
      await client.app.log({
        body: {
          service: "wpm-plugin",
          level: "info",
          message:
            `session idle (${sessionID}): verify durable facts were persisted via ${SERVER_NAME}_store_entry`,
        },
      })
    },
  }
}

export default WpmPlugin
