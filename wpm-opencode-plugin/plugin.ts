import { join } from "node:path"
import type { Plugin, ToolDefinition } from "@opencode-ai/plugin"
import { $ } from "bun"
import { isEnabled, readConfigParam, resolveResponseLanguage } from "./wpm-lib/config/settings"
import { buildBridgedTools } from "./wpm-lib/mcp/bridge"
import { WpmMcpClient } from "./wpm-lib/mcp/client"
import { buildNudge, buildPersistReminder } from "./wpm-lib/prompts/nudges"
import { createHooks } from "./wpm-lib/server/hooks"
import {
  DEFAULT_RAG_MAX_ITEMS,
  DEFAULT_RAG_SIMILARITY_THRESHOLD,
} from "./wpm-lib/server/system-push"

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

export const WpmPlugin: Plugin = async ({ client, directory }) => {
  if (!isEnabled(directory)) {
    return {}
  }

  const languageConfig = readConfigParam(directory, "response_language")
  const thresholdConfig = readConfigParam(directory, "confidence_threshold")

  // Current user's profile language overrides config (resolveResponseLanguage
  // stays the single resolution mechanism — only its input changes, fetched
  // through the wpm CLI to avoid touching any prompt text).
  // Resolved once at plugin load, like wpm.config.json. A mid-session
  // `wpm current-user` switch refreshes the <current-user> block on the
  // next turn (system-push fresh read), but the nudge's language clause
  // only refreshes on restart — the block remains authoritative.
  let userLanguage = ""
  try {
    const out = await $`wpm current-user --language`
      .env({ ...process.env, WPM_CONFIG_PATH: join(directory, "wpm.config.json") })
      .quiet()
      .nothrow()
      .text()
    userLanguage = out.trim()
  } catch {}
  const language = resolveResponseLanguage(
    userLanguage || (languageConfig ? String(languageConfig) : undefined),
    process.env.WPM_RESPONSE_LANGUAGE,
  )
  const confidenceThreshold = thresholdConfig ? String(thresholdConfig) : undefined
  const queriedRecently = new Map<string, boolean>()

  // The plugin spawns and owns the MCP server — warm embedding + rule cache
  // shared by the tool bridge and the deterministic pushes.
  let mcp: WpmMcpClient | undefined
  let bridgedTools: Record<string, ToolDefinition> | undefined
  let goldenRules: string | undefined

  mcp = new WpmMcpClient({
    configPath: join(directory, "wpm.config.json"),
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

  return createHooks({
    client,
    language,
    confidenceThreshold,
    nudge: buildNudge(language),
    persistReminder: buildPersistReminder(),
    nudged: new Set<string>(),
    queriedRecently,
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
