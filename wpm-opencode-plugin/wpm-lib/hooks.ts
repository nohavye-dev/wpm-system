import type { Hooks, PluginInput } from "@opencode-ai/plugin"
import { $ } from "bun"
import { join } from "node:path"
import { SERVER_NAME } from "./constants"
import { buildMemoryFirstNudge, buildPersistPromptText } from "./nudges"
import { buildCommands } from "./commands"
import { resolvePythonPath } from "./helpers"

export type HookDeps = {
  client: PluginInput["client"]
  directory: string
  language?: string
  confidenceThreshold?: string
  nudge: string
  persistReminder: string
  nudged: Set<string>
  queriedRecently: Map<string, boolean>
}

export function createHooks(deps: HookDeps): Hooks {
  const { client, directory, language, confidenceThreshold, nudge, persistReminder, nudged, queriedRecently } = deps
  const commands = buildCommands(language, confidenceThreshold)

  return {
    // Register the wpm MCP server so the user does not have to declare it
    // in opencode.json. WPM_CONFIG_PATH pins the project config regardless
    // of the process cwd. Also grant plan-mode write permission.
    config: async (config) => {
      config.default_agent = "plan"
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
      const commandsConfig = (config.command ??= {})
      for (const [name, def] of Object.entries(commands)) {
        if (!commandsConfig[name]) {
          commandsConfig[name] = {
            template: def.template,
            description: def.description,
            agent: def.agent ?? "plan",
          }
        }
      }
    },

    // Slash commands run first-class: replace the long instruction prompt
    // with a short visible label so the /wpm commands read cleanly.
    "command.execute.before": async (input, output) => {
      if (!(input.command in commands)) return
      for (const part of output.parts ?? []) {
        if (part.type === "text") {
          part.synthetic = true
          part.metadata = { wpm_no_persist_rearm: true }
        }
      }
      const label = ["/" + input.command, input.arguments]
        .filter(Boolean).join(" ")
      output.parts.unshift({ type: "text", text: label } as any)
    },

    // Re-arm the end-of-task persist net when a real user message arrives,
    // so a session that continues after a persist pass gets persisted again.
    // Our own injected prompts carry metadata.wpm_no_persist_rearm so they do not
    // count as real user input.
    "chat.message": async (input, output) => {
      const noPersistRearm = (output.parts ?? []).some(
        (p) => p.type === "text" && p.metadata?.wpm_no_persist_rearm === true,
      )
      if (!noPersistRearm) nudged.delete(input.sessionID)
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
              metadata: { wpm_no_persist_rearm: true },
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
              text: buildPersistPromptText(language),
              synthetic: true,
              metadata: { wpm_no_persist_rearm: true },
            },
          ],
        },
      })
    },
  }
}
