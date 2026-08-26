import type { Hooks, PluginInput } from "@opencode-ai/plugin"
import type { ToolDefinition } from "@opencode-ai/plugin"
import { $ } from "bun"
import { join } from "node:path"
import { SERVER_NAME } from "../core/constants"
import { buildMemoryFirstNudge, buildPersistPromptText } from "../prompts/nudges"
import { buildCommands } from "../prompts/commands/index"
import { buildSystemPush, type SystemPushDeps } from "./system-push"
import { resolvePythonPath } from "../infra/paths"

export type HookDeps = SystemPushDeps & {
  directory: string
  language?: string
  confidenceThreshold?: string
  persistReminder: string
  nudged: Set<string>
  queriedRecently: Map<string, boolean>
  // Architecture switch (wpm.config.json plugin_master): true = the plugin
  // owns the MCP server (bridge + pushes); false = legacy, opencode hosts
  // the server declared by the config hook below.
  pluginMaster: boolean
  // Dynamic bridge of the warm server's tools (wpm_*); absent in degraded
  // mode and in legacy mode.
  bridgedTools?: Record<string, ToolDefinition>
}

// Resolve the session's live agent so our injected prompts never flip the
// session into another agent (defaulting to plan once hijacked a build turn).
async function sessionAgent(
  client: PluginInput["client"],
  sessionID: string,
): Promise<string | undefined> {
  try {
    const result = await client.session.get({ path: { id: sessionID } })
    const agent = (result as { data?: { agent?: string } } | undefined)?.data?.agent
    return agent || undefined
  } catch {
    return undefined
  }
}

export function createHooks(deps: HookDeps): Hooks {
  const {
    client,
    directory,
    language,
    confidenceThreshold,
    nudge,
    persistReminder,
    nudged,
    queriedRecently,
    bridgedTools,
    pluginMaster,
  } = deps
  const commands = buildCommands(language, confidenceThreshold)

  return {
    ...(bridgedTools ? { tool: bridgedTools } : {}),
    // Grant plan-mode write permission. In legacy mode also register the
    // wpm MCP server so the user does not have to declare it in
    // opencode.json — WPM_CONFIG_PATH pins the project config regardless
    // of the process cwd.
    config: async (config) => {
      if (!pluginMaster) {
        config.mcp = config.mcp ?? {}
        if (!config.mcp["wpm"]) {
          config.mcp["wpm"] = {
            type: "local",
            command: [resolvePythonPath(), "-m", "wpm_mcp_server"],
            environment: { WPM_CONFIG_PATH: join(directory, "wpm.config.json") },
            enabled: true,
          }
        }
      }
      // default_agent is intentionally NOT set: sessions start in the
      // opencode default (build). Forcing plan made every injected prompt
      // silently hijack build turns into plan (see internals decision #13).
      const permission = (config.permission ??= {}) as Record<string, unknown>
      if (!permission["wpm_*"]) {
        permission["wpm_*"] = "allow"
      }
      // Customise the plan agent: add WPM memory exception and permissions.
      // The built-in plan agent has no custom prompt, so setting one adds
      // instructions without replacing anything. Permission rules are
      // appended (last match wins), so wpm_*: allow takes effect.
      const agents = (config.agent ??= {}) as Record<string, unknown>
      const planAgent = (agents.plan ??= {}) as Record<string, unknown>

      planAgent.prompt =
        "EXCEPTION — WPM Memory Tools: All wpm_* MCP tools (wpm_store_entry, " +
        "wpm_validate_entry, wpm_contradict_entry, wpm_deprecate_entry, " +
        "wpm_link_entries, wpm_pin_entry, wpm_record_execution, wpm_restore_entry, " +
        "wpm_query_context, wpm_list_entries, wpm_get_memory_stats, " +
        "wpm_get_user, wpm_record_user_observation, wpm_get_user_observations) are ALWAYS allowed, " +
        "even in plan mode. Memory is the agent's own state — writing to it does " +
        "not modify the project. Never skip, defer, or refuse a memory operation " +
        "because of plan-mode restrictions."

      const planPerm = (planAgent.permission ??= {}) as Record<string, unknown>
      if (!planPerm["wpm_*"]) {
        planPerm["wpm_*"] = "allow"
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
      // A /wpm-* command is a self-contained memory operation, not a user task
      // that produces new durable facts: suppress the end-of-turn persist pass.
      nudged.add(input.sessionID)
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

    // Per-turn system push. plugin_master: golden rules + project rules +
    // RAG pop-in (see system-push.ts), then the compact anti-dilution nudge.
    // Legacy: the compact nudge alone, exactly like before the migration —
    // the golden rules reach the LLM via initialize.instructions injected
    // by opencode from the host-owned server.
    "experimental.chat.system.transform": async (input, output) => {
      if (!pluginMaster || !deps.mcp) {
        output.system.push(nudge)
        return
      }
      const blocks = await buildSystemPush(deps, input.sessionID)
      for (const block of blocks) {
        output.system.push(block)
      }
    },

    // Re-anchor at the exact moment of loss: when the session is compacted,
    // persist anything still unpersisted and restore the rules.
    "experimental.session.compacting": async (_input, output) => {
      output.context.push(persistReminder)
      output.context.push(nudge)
    },

    // Rule 16 (record executions) — deterministic, no model involved: every
    // bash command that looks like a verification command is recorded.
    // plugin_master: tools/call on the warm server (no cold start). Any
    // degradation — server unavailable or died mid-call — falls through to
    // the standalone CLI shellout, so an execution is never lost
    // (durability parity with legacy). Legacy: the CLI shellout directly.
    "tool.execute.after": async (input, output) => {
      if (input.tool === `${SERVER_NAME}_query_context`) {
        queriedRecently.set(input.sessionID, true)
        return
      }
      if (input.tool !== "bash") return
      const command = String(input.args?.command ?? "")
      const succeeded = output.metadata?.exit === 0
      if (pluginMaster && deps.mcp && (await deps.mcp.ready())) {
        try {
          await deps.mcp.callTool("record_execution", {
            command,
            succeeded,
            session_id: input.sessionID,
          })
          return
        } catch {}
      }
      await $`wpm record-execution ${command} --succeeded=${succeeded} --session-id=${input.sessionID}`
        .quiet()
        .nothrow()
    },

    // Conditional memory-first nudge: only when about to read/search without
    // having queried memory recently — instead of nagging every turn. The
    // injected prompt carries the session's live agent: an agent-less
    // prompt() inherits default_agent and would flip build turns into plan.
    "tool.execute.before": async (input, _output) => {
      if (!["read", "grep", "glob"].includes(input.tool)) return
      if (queriedRecently.get(input.sessionID)) return
      const agent = await sessionAgent(client, input.sessionID)
      await client.session.prompt({
        path: { id: input.sessionID },
        body: {
          noReply: true,
          ...(agent ? { agent } : {}),
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
    // Same agent-explicit rule as above — an agent-less prompt() would
    // hijack the session into default_agent (plan) mid-task.
    event: async ({ event }) => {
      if (event.type !== "session.idle") return
      const sessionID: string | undefined = (event as any).properties?.sessionID
      if (!sessionID || nudged.has(sessionID)) return
      nudged.add(sessionID)
      const agent = await sessionAgent(client, sessionID)
      await client.session.prompt({
        path: { id: sessionID },
        body: {
          noReply: false,
          ...(agent ? { agent } : {}),
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
