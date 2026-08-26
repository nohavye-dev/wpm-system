import type { Plugin } from "@opencode-ai/plugin"
import type { ToolDefinition } from "@opencode-ai/plugin"
import { $ } from "bun"
import { join } from "node:path"
import { buildNudge, buildPersistReminder } from "./wpm-lib/prompts/nudges"
import { isEnabled, readConfigParam, resolveResponseLanguage } from "./wpm-lib/config/settings"
import { createHooks } from "./wpm-lib/server/hooks"
import { DEFAULT_RAG_MAX_ITEMS, DEFAULT_RAG_SIMILARITY_THRESHOLD } from "./wpm-lib/server/system-push"
import { WpmMcpClient } from "./wpm-lib/mcp/client"
import { buildBridgedTools } from "./wpm-lib/mcp/bridge"

const liveClients = new Set<WpmMcpClient>()
let teardownRegistered = false

function registerTeardown(client: WpmMcpClient): void {
  liveClients.add(client)
  if (teardownRegistered) return
  teardownRegistered = true
  process.on("exit", () => {
    for (const client of liveClients) {
      client.killSync()
    }
  })
}

function numberParam(value: string | number | boolean | undefined, fallback: number): number {
  const parsed = typeof value === "number" ? value : Number.parseFloat(String(value ?? ""))
  return Number.isFinite(parsed) ? parsed : fallback
}

// Accepts the JSON boolean and its string spelling so a mistyped
// "plugin_master": "true" still opts in, while anything else stays legacy.
function flagParam(value: string | number | boolean | undefined): boolean {
  return value === true || value === "true"
}

export const WpmPlugin: Plugin = async ({ client, directory }) => {
  if (!isEnabled(directory)) {
    return {}
  }

  const languageConfig = readConfigParam(directory, "response_language")
  const thresholdConfig = readConfigParam(directory, "confidence_threshold")
  const pluginMaster = flagParam(readConfigParam(directory, "plugin_master"))

  // Current user's profile language overrides config (resolveResponseLanguage
  // stays the single resolution mechanism — only its input changes, fetched
  // through the wpm CLI to avoid touching any prompt text).
  // Resolved once at plugin load, like wpm.config.json. A mid-session
  // `wpm current-user` switch refreshes the <current-user> block on the
  // next turn (system-push fresh read), but the nudge's language clause
  // only refreshes on restart — the block remains authoritative.
  let userLanguage = ""
  try {
    const out = await $`wpm current-user --language`.quiet().nothrow().text()
    userLanguage = out.trim()
  } catch {}
  const language = resolveResponseLanguage(
    userLanguage || (languageConfig ? String(languageConfig) : undefined),
    process.env.WPM_RESPONSE_LANGUAGE,
  )
  const confidenceThreshold = thresholdConfig ? String(thresholdConfig) : undefined
  const queriedRecently = new Map<string, boolean>()

  // plugin_master mode: the plugin spawns and owns the MCP server — warm
  // embedding + rule cache shared by the tool bridge and the deterministic
  // pushes. Legacy mode (default): opencode hosts the server via the
  // config hook and the plugin only pushes its nudge; nothing here spawns.
  let mcp: WpmMcpClient | undefined
  let bridgedTools: Record<string, ToolDefinition> | undefined
  let goldenRules: string | undefined

  if (pluginMaster) {
    mcp = new WpmMcpClient({
      configPath: join(directory, "wpm.config.json"),
      // The server renders its push prompt variant: rules arrive pushed by
      // the plugin every turn and no resource-read tool exists in this mode.
      env: { WPM_PROMPT_MODE: "push" },
    })
    registerTeardown(mcp)
    if (await mcp.start()) {
      ;[bridgedTools, goldenRules] = await Promise.all([
        // The bridge feeds the memory-first gate itself: host hooks proved
        // unreliable for plugin-defined tools.
        buildBridgedTools(mcp, {
          onQueryContext: (sessionID) => queriedRecently.set(sessionID, true),
        }).catch(() => undefined),
        mcp.readMemoryRules().catch(() => undefined),
      ])
    }
  }

  return createHooks({
    client,
    directory,
    language,
    confidenceThreshold,
    nudge: buildNudge(language, pluginMaster),
    persistReminder: buildPersistReminder(),
    nudged: new Set<string>(),
    queriedRecently,
    pluginMaster,
    mcp,
    goldenRules,
    bridgedTools,
    confidenceFloor: numberParam(thresholdConfig, 0.5),
    ragSimilarityThreshold: numberParam(
      readConfigParam(directory, "rag_similarity_threshold"),
      DEFAULT_RAG_SIMILARITY_THRESHOLD,
    ),
    ragMaxItems: Math.max(
      1,
      Math.round(numberParam(readConfigParam(directory, "rag_max_items"), DEFAULT_RAG_MAX_ITEMS)),
    ),
  })
}

export default WpmPlugin
