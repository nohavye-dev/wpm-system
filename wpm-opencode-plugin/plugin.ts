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

// Mirrors the MCP `persist` prompt (server.py wpm_persist) so the
// session.idle hook and the prompt carry the same text — one source of truth.
const PERSIST_PROMPT_TEXT =
  "Session ended. End-of-task memory pass (wpm persistent memory): if " +
  "and only if durable facts from this session — decisions, confirmed " +
  "results, understood bug patterns — were not yet persisted via " +
  `${SERVER_NAME}_store_entry or ${SERVER_NAME}_record_execution, persist them now. ` +
  "Do not invent evidence, do not store transient details or trivia, and do " +
  "not validate anything without external proof. If nothing remains to " +
  'persist, reply exactly: "Nothing to persist." else give a summary of ' +
  'what was persisted and say exactly: "Persistence complete."'

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
    },

    // Re-inject the golden rules at every LLM turn so they cannot be
    // diluted by context growth — the deterministic push a pure MCP server
    // cannot provide.
    "experimental.chat.system.transform": async (input, output) => {
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
          parts: [{ type: "text", text: buildMemoryFirstNudge() }],
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
            { type: "text", text: "Persist session memory." },
            { type: "text", text: PERSIST_PROMPT_TEXT, synthetic: true },
          ],
        },
      })
    },
  }
}

export default WpmPlugin
