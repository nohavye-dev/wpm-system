import type { Plugin } from "@opencode-ai/plugin"
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

export const WpmPlugin: Plugin = async ({ client, directory }) => {
  if (!isEnabled(directory)) {
    return {}
  }

  const languageConfig = readConfigParam(directory, "response_language")
  const thresholdConfig = readConfigParam(directory, "confidence_threshold")

  const language = resolveResponseLanguage(
    languageConfig ? String(languageConfig) : undefined,
    process.env.WPM_RESPONSE_LANGUAGE,
  )
  const confidenceThreshold = thresholdConfig ? String(thresholdConfig) : undefined

  // The plugin spawns and owns the MCP server: warm embedding + rule cache,
  // shared by the tool bridge and the deterministic pushes. Degraded mode
  // (server unreachable at boot) keeps the static hooks alive.
  const mcp = new WpmMcpClient({ configPath: join(directory, "wpm.config.json") })
  registerTeardown(mcp)

  const started = await mcp.start()
  const [bridgedTools, goldenRules] = await Promise.all([
    started ? buildBridgedTools(mcp).catch(() => undefined) : Promise.resolve(undefined),
    started ? mcp.readMemoryRules().catch(() => undefined) : Promise.resolve(undefined),
  ])

  return createHooks({
    client,
    directory,
    language,
    confidenceThreshold,
    nudge: buildNudge(language),
    persistReminder: buildPersistReminder(),
    nudged: new Set<string>(),
    queriedRecently: new Map<string, boolean>(),
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
