import type { PluginInput } from "@opencode-ai/plugin"
import { InjectionBlock } from "../prompts/entities"
import { PROJECT_RULES_URI, type WpmMcpClient } from "../mcp/client"
import type { McpCallToolResult } from "../mcp/entities"

export const DEFAULT_RAG_SIMILARITY_THRESHOLD = 0.45
export const DEFAULT_RAG_MAX_ITEMS = 3

// Internal diagnostics for the deterministic push path; silent unless
// WPM_DEBUG is set so a degraded server never pollutes the host's output.
function debug(message: string, error: unknown): void {
  if (process.env.WPM_DEBUG) {
    console.error(`[wpm] ${message}:`, error)
  }
}

export type SystemPushDeps = {
  client: PluginInput["client"]
  mcp: WpmMcpClient
  // Golden rules read once at startup from wpm://memory-rules — the same
  // bytes opencode used to receive via initialize.instructions. Pushed at
  // every turn (frozen prompting: never edited here).
  goldenRules?: string
  nudge: string
  confidenceFloor: number
  ragSimilarityThreshold: number
  ragMaxItems: number
}

// Per-turn deterministic push, in order: golden rules (procedural),
// project rules (deterministic data), RAG pop-in (turn-dependent data),
// compact nudge last so the anti-dilution anchor stays at the bottom of
// context. Every server-dependent step degrades silently to keep the push
// off the critical path when the warm server is unavailable.
export async function buildSystemPush(
  deps: SystemPushDeps,
  sessionID?: string,
): Promise<string[]> {
  const blocks: string[] = []

  if (deps.goldenRules?.trim()) {
    blocks.push(deps.goldenRules.trim())
  }

  if (await deps.mcp.ready()) {
    let rulesBody: string | undefined
    try {
      rulesBody = (await deps.mcp.readResource(PROJECT_RULES_URI))?.trim()
    } catch (error) {
      debug("project-rules read failed", error)
    }
    if (rulesBody) {
      blocks.push(rulesBody)
    }
    if (sessionID) {
      try {
        const recall = await buildRecallBlock(deps, sessionID, rulesBody)
        if (recall) {
          blocks.push(recall)
        }
      } catch (error) {
        debug("recall block failed", error)
      }
    }
  }

  blocks.push(deps.nudge)
  return blocks
}

type RecallEntry = {
  entry_id?: string
  type?: string
  content?: string
  similarity?: number
  confidence?: number
}

type QueryContextResult = {
  direct_matches?: RecallEntry[]
  related_context?: RecallEntry[]
  conflicts?: Array<{ entry_id?: string; contradicted_by?: string }>
}

async function buildRecallBlock(
  deps: SystemPushDeps,
  sessionID: string,
  rulesBody: string | undefined,
): Promise<string | undefined> {
  const query = await lastUserMessageText(deps.client, sessionID)
  if (!query) {
    debug("recall skipped: no user message", "")
    return undefined
  }

  const result = await deps.mcp.callTool("query_context", {
    query,
    min_confidence: deps.confidenceFloor,
  })
  const data = extractStructured(result)
  if (!data) {
    debug("recall skipped: unparseable query_context result", result)
    return undefined
  }

  const candidates: RecallEntry[] = [
    ...(data.direct_matches ?? []),
    ...(data.related_context ?? []),
  ]
  const conflictsByEntry = new Map<string, string>()
  for (const conflict of data.conflicts ?? []) {
    if (conflict.entry_id && conflict.contradicted_by) {
      conflictsByEntry.set(conflict.entry_id, conflict.contradicted_by)
    }
  }

  const seen = new Set<string>()
  const picked = candidates
    .filter((entry) => typeof entry.content === "string" && entry.content.trim())
    .filter((entry) => (entry.similarity ?? 0) >= deps.ragSimilarityThreshold)
    .filter((entry) => (entry.confidence ?? 0) >= deps.confidenceFloor)
    // An entry already rendered inside the project-rules body must not be
    // injected twice this turn (shared rules↔RAG dedup). The 80-char prefix
    // match survives the server's MAX_PROJECT_RULES_CHARS tail truncation,
    // which can otherwise cut an entry mid-content and hide it from a full
    // substring match.
    .filter((entry) => !renderedInRules(entry.content!, rulesBody))
    .filter((entry) => {
      const id = entry.entry_id ?? entry.content!
      if (seen.has(id)) return false
      seen.add(id)
      return true
    })
    .sort((a, b) => (b.similarity ?? 0) - (a.similarity ?? 0))
    .slice(0, deps.ragMaxItems)

  void logDecision(deps.client, sessionID, {
    candidates,
    picked,
    topSim: Math.max(0, ...candidates.map((entry) => entry.similarity ?? 0)),
  }).catch(() => {})

  if (picked.length === 0) {
    debug(
      `recall empty: ${candidates.length} candidates, threshold sim>=${deps.ragSimilarityThreshold} conf>=${deps.confidenceFloor}`,
      candidates.map((entry) => ({ sim: entry.similarity, conf: entry.confidence })),
    )
    return undefined
  }

  const block = new InjectionBlock("wpm-memory-recall")
    .addPurpose("Automatically recalled durable memories relevant to this request.")
  for (const entry of picked) {
    block.addItem(
      `[${entry.type ?? "unknown"}] ${entry.content} ` +
        `(similarity ${(entry.similarity ?? 0).toFixed(2)}, confidence ${(entry.confidence ?? 0).toFixed(2)})`,
    )
    const contradictedBy = entry.entry_id ? conflictsByEntry.get(entry.entry_id) : undefined
    if (contradictedBy) {
      block.addNote(`entry ${entry.entry_id} is actively contradicted by entry ${contradictedBy}`)
    }
  }

  return block.toString()
}

// True when the entry's text is already part of the rendered project-rules
// block: full match first, then an 80-char prefix so a tail-truncated body
// still hides its last (cut-off) entry.
function renderedInRules(content: string, rulesBody: string | undefined): boolean {
  if (!rulesBody || !content.trim()) return false
  return rulesBody.includes(content) || rulesBody.includes(content.slice(0, 80))
}

// The transform hook does not receive the user turn: fetch it via the SDK.
// Our own synthetic prompts (persist passes, memory-first nudges) are
// skipped so they never become recall queries.
async function lastUserMessageText(
  client: PluginInput["client"],
  sessionID: string,
): Promise<string | undefined> {
  // The SDK returns every message of the session: cost grows with session
  // length. Acceptable today (localhost HTTP, compacted sessions); if it
  // ever shows up on the critical path, an incremental cursor or a cached
  // last-user-message per sessionID is the pre-identified optimization.
  const result = await client.session.messages({ path: { id: sessionID } })
  const payload = (result as { data?: unknown } | undefined)?.data
  if (!Array.isArray(payload)) return undefined
  for (let index = payload.length - 1; index >= 0; index--) {
    const message = payload[index] as {
      info?: { role?: string }
      parts?: Array<{ type?: string; text?: string; synthetic?: boolean; metadata?: Record<string, unknown> }>
    }
    if (message.info?.role !== "user") continue
    const text = (message.parts ?? [])
      .filter(
        (part) =>
          part.type === "text" &&
          !part.synthetic &&
          part.metadata?.wpm_no_persist_rearm !== true,
      )
      .map((part) => String(part.text ?? ""))
      .join("\n")
      .trim()
    if (text) return text
  }
  return undefined
}

function extractStructured(result: McpCallToolResult | undefined): QueryContextResult | undefined {
  if (!result) return undefined
  if (result.structuredContent != null) {
    return result.structuredContent as QueryContextResult
  }
  const text = (result.content ?? []).find((block) => block.type === "text")?.text
  if (!text) return undefined
  try {
    return JSON.parse(text) as QueryContextResult
  } catch {
    return undefined
  }
}

// One compact trace per turn with candidates — the only auditable evidence
// of the pop-in (the system prompt is not persisted, and opencode's logger
// drops everything below INFO). Fired even when nothing is picked so a
// silent turn is distinguishable from a broken pipeline during calibration.
async function logDecision(
  client: PluginInput["client"],
  sessionID: string,
  decision: { candidates: RecallEntry[]; picked: RecallEntry[]; topSim: number },
): Promise<void> {
  if (decision.candidates.length === 0) return
  await client.app.log({
    body: {
      service: "wpm",
      level: "info",
      message: "rag decision",
      extra: {
        sessionID,
        candidates: decision.candidates.length,
        picked: decision.picked.length,
        top_sim: Number(decision.topSim.toFixed(4)),
        entries: decision.picked.map((entry) => ({
          entry_id: entry.entry_id,
          similarity: entry.similarity,
          confidence: entry.confidence,
        })),
      },
    },
  })
}
