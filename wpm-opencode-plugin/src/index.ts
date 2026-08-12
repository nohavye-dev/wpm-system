import { existsSync } from "node:fs"
import { join } from "node:path"
import type { Plugin } from "@opencode-ai/plugin"
import { tool } from "@opencode-ai/plugin"
import { MemoryClient } from "./mcp-client.js"
import {
  getVerificationCommandPatterns,
  getIdleNudgeEnabled,
  loadMemoryServerConfig,
  getConfidenceThreshold,
} from "./config.js"
import { IDLE_NUDGE_TEXT, MEMORY_USAGE_RULES } from "./rules.js"
import {
  COMPACTION_QUERY_MAX_CHARS,
  COMPACTION_WIDE_WINDOW,
  DEFAULT_COMPACTION_QUERY,
  MAX_RULES_CHARS,
  PROJECT_RULES_QUERY,
  buildProjectRulesBlock,
  deriveCompactionQuery,
  extractUserTexts,
} from "./project-context.js"

const MAX_PROJECT_RULES_CACHE = 50

export const VERIFICATION_COMMAND_PATTERNS: RegExp[] = [
  /\bpytest\b/,
  /\bnpm\s+(run\s+)?test\b/,
  /\bnpm\s+run\s+build\b/,
  /\bpnpm\s+(run\s+)?test\b/,
  /\bpnpm\s+(run\s+)?build\b/,
  /\byarn\s+test\b/,
  /\byarn\s+build\b/,
  /\bbun\s+(run\s+)?test\b/,
  /\bbun\s+run\s+build\b/,
  /\bdotnet\s+test\b/,
  /\bdotnet\s+build\b/,
  /\bcargo\s+test\b/,
  /\bcargo\s+build\b/,
  /\bgo\s+test\b/,
  /\bgo\s+build\b/,
  /\bmake\s+test\b/,
  /\bmix\s+test\b/,
  /\bflutter\s+test\b/,
  /\bmvn\s+test\b/,
  /\bgradle\s+test\b/,
  /\bsbt\s+test\b/,
  /\bvitest\b/,
  /\bjest\b/,
  /\bdeno\s+test\b/,
  /\btox\b/,
  /\bphpunit\b/,
  /\brake\s+test\b/,
  /\bcompileall\b/,
  /\bpy_compile\b/,
  /\bbash\s+-n\b/,
  /\bshellcheck\b/,
  /\btsc\s+--noEmit\b/,
  /\bruff\s+check\b/,
  /\bmypy\b/,
  /\beslint\b/,
]

// Tools that mutate the project — used to detect whether a session did real
// work before allowing an idle nudge.
export const WORK_TOOLS = new Set(["edit", "write", "apply_patch", "bash", "task"])

// Memory tools that change the stored state — invalidating the project-rules
// cache so freshly persisted rules reach the system prompt promptly.
export const MEMORY_MUTATION_TOOLS = new Set([
  "store_entry",
  "validate_entry",
  "contradict_entry",
  "link_entries",
  "pin_entry",
  "deprecate_entry",
  "restore_entry",
])

export function looksLikeVerificationCommand(
  command: string | undefined,
  patterns: (RegExp | null)[],
): boolean {
  if (!command) return false
  return patterns.some((re) => re !== null && re.test(command))
}

export const WpmPlugin: Plugin = async ({ client, directory }) => {
  const configPath = join(directory, "wpm.config.json")
  if (!existsSync(configPath)) {
    await client.app.log({
      body: {
        service: "wpm-opencode-plugin",
        level: "debug",
        message: "wpm: inactive (no wpm.config.json)",
      },
    })
    return {}
  }

  await client.app.log({
    body: {
      service: "wpm-opencode-plugin",
      level: "info",
      message: "wpm: active",
    },
  })

  const config = loadMemoryServerConfig(directory)
  const memory = new MemoryClient(config)

  // OpenCode's plugin API has no teardown hook. beforeExit fires before
  // the event loop drains and supports the async close() for a clean stdio
  // transport shutdown. The exit fallback handles explicit process.exit()
  // calls where beforeExit may not fire — it does a best-effort sync kill
  // of the Python subprocess.
  let cleanedUp = false
  const cleanup = () => {
    if (cleanedUp) return
    cleanedUp = true
    void memory.close()
  }
  process.once("beforeExit", cleanup)
  process.once("exit", () => {
    if (!cleanedUp) memory.closeSync()
  })

  const confidenceThreshold = getConfidenceThreshold(directory)
  const idleNudgeEnabled = getIdleNudgeEnabled(directory)
  const verificationPatterns = [
    ...VERIFICATION_COMMAND_PATTERNS,
    ...getVerificationCommandPatterns(directory).map((pattern) => {
      try {
        return new RegExp(pattern)
      } catch (err) {
        void client.app.log({
          body: {
            service: "wpm-opencode-plugin",
            level: "error",
            message: `invalid verification_command_pattern regex ${JSON.stringify(pattern)}: ${String(err)}`,
          },
        })
        return null
      }
    }),
  ]
  const activeSessions = new Set<string>()
  const nudgedSessions = new Map<string, number>()
  const projectRulesCache = new Map<string, string>()

  const cacheKey = (sessionID: string | undefined) => sessionID ?? "default"

  const resolveProjectRules = async (
    sessionID: string | undefined,
  ): Promise<string> => {
    const key = cacheKey(sessionID)
    const cached = projectRulesCache.get(key)
    if (cached !== undefined) return cached

    const result = await memory.queryContext({
      query: PROJECT_RULES_QUERY,
      min_confidence: confidenceThreshold,
      token_budget: 800,
    })
    const text = extractTextFromToolResult(result)
    const rules = text ? text.slice(0, MAX_RULES_CHARS) : ""

    if (projectRulesCache.size >= MAX_PROJECT_RULES_CACHE) {
      const oldest = projectRulesCache.keys().next().value
      if (oldest !== undefined) projectRulesCache.delete(oldest)
    }
    projectRulesCache.set(key, rules)
    return rules
  }

  return {
    tool: {
      store_entry: tool({
        description:
          "Store a new memory entry (doc, archi_decision, learning, convention, " +
          "or bug_pattern). CONTENT MUST BE IN ENGLISH. " +
          "'source' should be one of: official_doc, observed_code, " +
          "tool_execution, agent_inference (unknown sources get a neutral " +
          "default confidence). Before storing, run query_context on the " +
          "topic: if a near-duplicate already exists, call validate_entry on " +
          "it instead of creating a duplicate. Only store durable facts that " +
          "will still be true and useful in weeks. Returns the new entry_id " +
          "and its initial confidence — this entry starts unvalidated; call " +
          "validate_entry with real evidence once it is confirmed.",
        args: {
          type: tool.schema.string(),
          content: tool.schema.string(),
          source: tool.schema.string(),
        },
        execute: async (args) => {
          const result = await memory.callTool("store_entry", args)
          return toolResultToString(result)
        },
      }),

      query_context: tool({
        description:
          "Hybrid retrieval: vector similarity + confidence weighting + graph " +
          "centrality, plus 1-hop graph expansion for associative recall " +
          "(spec section 6). Query text should be in English for best " +
          "similarity matching. Returns direct_matches (strong hits), " +
          "related_context (associative, lower-confidence recall via linked " +
          "entries), and conflicts (entries with an active 'contradicts' " +
          "link) — always check conflicts before relying on a direct_match.",
        args: {
          query: tool.schema.string(),
          min_confidence: tool.schema.number().default(0),
          token_budget: tool.schema.number().int().default(2000),
        },
        execute: async (args) => {
          const result = await memory.callTool("query_context", args)
          return toolResultToString(result)
        },
      }),

      validate_entry: tool({
        description:
          "Record EXTERNAL, CHECKABLE evidence that an entry was confirmed. " +
          "evidence_type must be one of: execution_verified (test/build/command " +
          "ran with expected result — strongest), cross_reference (confirmed " +
          "independently by another source), reuse_without_failure (reused " +
          "without issue — weak, capped), agent_reasoning (no external proof — " +
          "logged but does NOT move the score, do not use this to inflate " +
          "confidence). evidence_ref should point to what proves it (a test " +
          "log, a file path, another entry_id). session_id is required for " +
          "dedup: repeated validation of the same entry within one session " +
          "only counts once. Never re-validate repeatedly to inflate a score, " +
          "and never use agent_reasoning as a way to raise confidence — it " +
          "has no effect on the score by construction.",
        args: {
          entry_id: tool.schema.string(),
          evidence_type: tool.schema.string(),
          evidence_ref: tool.schema.string(),
          session_id: tool.schema.string(),
        },
        execute: async (args) => {
          const result = await memory.callTool("validate_entry", args)
          return toolResultToString(result)
        },
      }),

      contradict_entry: tool({
        description:
          "Record that entry_id is contradicted by conflicting_entry_id, with " +
          "external evidence (same evidence_type rules as validate_entry). " +
          "NEVER deletes either entry — only lowers entry_id's validation_score " +
          "(contradiction lowers the score faster than a confirmation raises " +
          "it) and creates a visible 'contradicts' link so future " +
          "query_context calls surface the conflict instead of hiding it.",
        args: {
          entry_id: tool.schema.string(),
          conflicting_entry_id: tool.schema.string(),
          evidence_type: tool.schema.string(),
          evidence_ref: tool.schema.string(),
        },
        execute: async (args) => {
          const result = await memory.callTool("contradict_entry", args)
          return toolResultToString(result)
        },
      }),

      link_entries: tool({
        description:
          "Create or update an EXPLICIT link between two entries. relation_type " +
          "must be one of: related, contradicts, depends_on, refines. Implicit " +
          "'related' links are created automatically by store_entry above a " +
          "similarity threshold — use this tool for relationships the " +
          "similarity search would not infer on its own (e.g. a dependency " +
          "between an architecture decision and a convention).",
        args: {
          source_id: tool.schema.string(),
          target_id: tool.schema.string(),
          relation_type: tool.schema.string(),
          weight: tool.schema.number().default(1),
        },
        execute: async (args) => {
          const result = await memory.callTool("link_entries", args)
          return toolResultToString(result)
        },
      }),

      get_memory_stats: tool({
        description:
          "Review memory health: total entries by type, confidence distribution " +
          "(low <0.3 / medium 0.3-0.7 / high >0.7), entries never validated, " +
          "active contradictions, 5 lowest-confidence entries, and the last 10 " +
          "events. Read-only diagnostic.",
        args: {},
        execute: async () => {
          const result = await memory.callTool("get_memory_stats", {})
          return toolResultToString(result)
        },
      }),

      pin_entry: tool({
        description:
          "Pin an entry so its confidence NEVER decays. USE WHEN: a fundamental " +
          "architecture decision that defines the project, a convention that is " +
          "company/project policy, or an entry that has been validated repeatedly " +
          "across many sessions and is now considered settled. DO NOT use for: " +
          "recent learnings, bug patterns that may be fixed, entries with active " +
          "contradictions. Pinning is reversible via restore_entry.",
        args: {
          entry_id: tool.schema.string(),
        },
        execute: async (args) => {
          const result = await memory.callTool("pin_entry", args)
          return toolResultToString(result)
        },
      }),

      deprecate_entry: tool({
        description:
          "Mark an entry as deprecated — excluded from all future queries. " +
          "USE WHEN: an entry has been conclusively contradicted and the newer " +
          "entry is confirmed, the code/module it references no longer exists, " +
          "or it describes a bug pattern that has been fixed. DO NOT use for: " +
          "entries you are unsure about. Deprecation is reversible via " +
          "restore_entry, but prefer caution.",
        args: {
          entry_id: tool.schema.string(),
        },
        execute: async (args) => {
          const result = await memory.callTool("deprecate_entry", args)
          return toolResultToString(result)
        },
      }),

      restore_entry: tool({
        description:
          "Restore a pinned or deprecated entry back to active status. " +
          "USE WHEN: a deprecation was premature, the entry is relevant again, " +
          "or a pin is no longer warranted.",
        args: {
          entry_id: tool.schema.string(),
        },
        execute: async (args) => {
          const result = await memory.callTool("restore_entry", args)
          return toolResultToString(result)
        },
      }),
    },

    "experimental.chat.system.transform": async (input, output) => {
      output.system.push(MEMORY_USAGE_RULES)
      try {
        const rules = await resolveProjectRules(input.sessionID)
        const block = buildProjectRulesBlock(rules)
        if (block) output.system.push(block)
      } catch (err) {
        await client.app.log({
          body: {
            service: "wpm-opencode-plugin",
            level: "error",
            message: `project rules injection failed: ${String(err)}`,
          },
        })
      }
    },

    "experimental.session.compacting": async (input, output) => {
      try {
        let query = DEFAULT_COMPACTION_QUERY
        try {
          const res = await client.session.messages({
            path: { id: input.sessionID },
            query: { limit: 20 },
          })
          const texts = extractUserTexts(res.data, COMPACTION_WIDE_WINDOW)
          query = deriveCompactionQuery(
            texts.slice(-2),
            texts,
            COMPACTION_QUERY_MAX_CHARS,
          )
        } catch {
          // Session message retrieval is best-effort — keep the generic query.
        }

        const result = await memory.queryContext({
          query,
          min_confidence: confidenceThreshold,
        })

        const text = extractTextFromToolResult(result)
        if (text) {
          output.context.push(
            `<preserved-memory-context>\n${text}\n</preserved-memory-context>`,
          )
        }

        output.context.push(
          "<memory-reminder>Before this context is compacted: if any " +
            "architecture decision, test result, or bug pattern from this " +
            "session has not yet been persisted via store_entry, call it " +
            "now, in English, with evidence_type set appropriately.</memory-reminder>",
        )
      } catch (err) {
        await client.app.log({
          body: {
            service: "wpm-opencode-plugin",
            level: "error",
            message: `compaction hook failed: ${String(err)}`,
          },
        })
      }
    },

    "tool.execute.after": async (input, output) => {
      if (WORK_TOOLS.has(input.tool)) {
        activeSessions.add(input.sessionID)
      }
      if (MEMORY_MUTATION_TOOLS.has(input.tool)) {
        projectRulesCache.delete(cacheKey(input.sessionID))
      }
      if (input.tool !== "bash") return

      const command = (input.args as { command?: string } | undefined)?.command
      if (!looksLikeVerificationCommand(command, verificationPatterns)) return

      const succeeded = !output.metadata?.error
      const sessionId = input.sessionID ?? "unknown-session"

      const storeResult = await memory.storeEntry({
        type: "learning",
        source: "tool_execution",
        content: [
          `Command executed: ${command}`,
          `Result: ${succeeded ? "success" : "failure"}`,
          `Directory: ${directory}`,
        ].join("\n"),
      })

      const entryId = extractEntryId(storeResult)

      if (succeeded && entryId) {
        await memory.validateEntry({
          entry_id: entryId,
          evidence_type: "execution_verified",
          evidence_ref: command ?? "unknown command",
          session_id: sessionId,
        })
      }

      await client.app.log({
        body: {
          service: "wpm-opencode-plugin",
          level: "info",
          message: entryId
            ? `Captured execution evidence (${succeeded ? "success, validated" : "failure, left unvalidated"}) for session ${sessionId} -> entry ${entryId}`
            : `Captured execution evidence (${succeeded ? "success" : "failure"}) for session ${sessionId}, but could not parse entry_id from store_entry result`,
        },
      })
    },

    event: async ({ event }) => {
      if (event.type !== "session.idle") return

      const sessionID = event.properties.sessionID

      await client.app.log({
        body: {
          service: "wpm-opencode-plugin",
          level: "info",
          message: `Session idle (${sessionID}). Reminder: verify all decisions/results from this session were persisted via store_entry.`,
        },
      })

      if (!idleNudgeEnabled) return
      if (nudgedSessions.has(sessionID)) return
      if (!activeSessions.has(sessionID)) return

      nudgedSessions.set(sessionID, Date.now())
      try {
        await client.session.promptAsync({
          path: { id: sessionID },
          body: { parts: [{ type: "text", text: IDLE_NUDGE_TEXT }] },
        })
        await client.app.log({
          body: {
            service: "wpm-opencode-plugin",
            level: "info",
            message: `Idle nudge sent to session ${sessionID}`,
          },
        })
      } catch (err) {
        nudgedSessions.delete(sessionID)
        await client.app.log({
          body: {
            service: "wpm-opencode-plugin",
            level: "error",
            message: `idle nudge failed for session ${sessionID}: ${String(err)}`,
          },
        })
      }
    },
  }
}

function extractTextFromToolResult(result: unknown): string | null {
  if (
    result &&
    typeof result === "object" &&
    "content" in result &&
    Array.isArray((result as { content: unknown[] }).content)
  ) {
    const parts = (result as { content: { type: string; text?: string }[] }).content
      .filter((c) => c.type === "text" && typeof c.text === "string")
      .map((c) => c.text as string)
    return parts.length > 0 ? parts.join("\n") : null
  }
  return null
}

function toolResultToString(result: unknown): string {
  const text = extractTextFromToolResult(result)
  if (text) return text
  return JSON.stringify(result)
}

function extractEntryId(result: unknown): string | null {
  const text = extractTextFromToolResult(result)
  if (!text) return null
  try {
    const parsed = JSON.parse(text) as { entry_id?: unknown }
    return typeof parsed.entry_id === "string" ? parsed.entry_id : null
  } catch {
    return null
  }
}

export default WpmPlugin
