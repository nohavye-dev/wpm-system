/**
 * E2E test for the MemoryClient against the real Python MCP server.
 *
 * Launches the server via stdio, calls all 5 tools, and asserts results.
 * Run with: npx tsx test_plugin.ts
 * Or compiled: node dist/test_plugin.js
 */

import { MemoryClient } from "./src/mcp-client.js"
import type { MemoryServerConfig } from "./src/mcp-client.js"
import { existsSync, unlinkSync } from "node:fs"
import { resolve } from "node:path"

const TEST_DIR = "/tmp/wpm-test-project"
const DB_PATH = resolve(TEST_DIR, ".wpm", "wpm.db")
const PYTHON = resolve(
  import.meta.dirname ?? __dirname,
  "..",
  "wpm-mcp-server",
  ".venv",
  "bin",
  "python",
)
const SRC_DIR = resolve(
  import.meta.dirname ?? __dirname,
  "..",
  "wpm-mcp-server",
  "src",
)

const config: MemoryServerConfig = {
  command: PYTHON,
  args: ["-m", "wpm_mcp_server"],
  cwd: TEST_DIR,
  env: {
    PYTHONPATH: SRC_DIR,
    WPM_CONFIG_PATH: resolve(TEST_DIR, "wpm.config.json"),
  },
}

let pass = 0
let fail = 0

function check(label: string, cond: boolean, detail?: string): void {
  if (cond) {
    pass++
    console.log(`  OK  ${label}`)
  } else {
    fail++
    console.log(`  FAIL ${label}${detail ? `: ${detail}` : ""}`)
  }
}

function parseToolText(result: unknown): Record<string, unknown> {
  const r = result as {
    content?: { type: string; text?: string }[]
  }
  const text = r.content?.find((c) => c.type === "text")?.text
  if (!text) throw new Error("no text content in tool result")
  return JSON.parse(text) as Record<string, unknown>
}

async function main(): Promise<void> {
  // Cleanup previous db
  for (const f of [DB_PATH, DB_PATH + "-wal", DB_PATH + "-shm"]) {
    if (existsSync(f)) unlinkSync(f)
  }

  const client = new MemoryClient(config)

  try {
    // --- store_entry (4 types) ---
    console.log("\n1. store_entry")

    const d1 = parseToolText(
      await client.storeEntry({
        type: "archi_decision",
        content: "CQRS separates read/write models",
        source: "official_doc",
      }),
    )
    const e1 = d1.entry_id as string
    check("archi_decision stored", typeof e1 === "string" && e1.length > 0)
    check("  provenance=0.9", d1.provenance_score === 0.9)

    const d2 = parseToolText(
      await client.storeEntry({
        type: "convention",
        content: "CQRS handlers return Result<T,Error>",
        source: "observed_code",
      }),
    )
    const e2 = d2.entry_id as string
    check("convention stored", typeof e2 === "string")

    const d3 = parseToolText(
      await client.storeEntry({
        type: "bug_pattern",
        content: "Read model fails on pool exhaustion",
        source: "tool_execution",
      }),
    )
    const e3 = d3.entry_id as string
    check("bug_pattern stored", typeof e3 === "string")

    const d4 = parseToolText(
      await client.storeEntry({
        type: "learning",
        content: "Session-scoped pytest fixtures reduce runtime",
        source: "agent_inference",
      }),
    )
    check("learning stored (low confidence)", (d4.confidence as number) <= 0.4)

    // --- link_entries ---
    console.log("\n2. link_entries")

    const link1 = parseToolText(
      await client.callTool("link_entries", {
        source_id: e2,
        target_id: e1,
        relation_type: "depends_on",
      }),
    )
    check("depends_on link", link1.relation_type === "depends_on")

    // --- query_context ---
    console.log("\n3. query_context")

    const q = parseToolText(
      await client.queryContext({
        query: "CQRS pattern",
        min_confidence: 0,
      }),
    )
    const direct = q.direct_matches as unknown[]
    const conflicts = q.conflicts as unknown[]
    check("direct_matches > 0", Array.isArray(direct) && direct.length > 0)
    check("no conflicts before contradict", Array.isArray(conflicts) && conflicts.length === 0)

    // --- validate_entry ---
    console.log("\n4. validate_entry")

    const v1 = parseToolText(
      await client.validateEntry({
        entry_id: e1,
        evidence_type: "execution_verified",
        evidence_ref: "plugin_test",
        session_id: "plugin-session",
      }),
    )
    check("execution_verified > 0", (v1.validation_score as number) > 0)

    // dedup
    const v1b = parseToolText(
      await client.validateEntry({
        entry_id: e1,
        evidence_type: "execution_verified",
        evidence_ref: "plugin_test",
        session_id: "plugin-session",
      }),
    )
    check("dedup in session", (v1b.note as string)?.includes("dedup"))

    // agent_reasoning excluded
    const v2 = parseToolText(
      await client.validateEntry({
        entry_id: e2,
        evidence_type: "agent_reasoning",
        evidence_ref: "i think so",
        session_id: "plugin-session",
      }),
    )
    check(
      "agent_reasoning excluded",
      v2.note === "agent_reasoning excluded from score",
    )

    // --- contradict_entry ---
    console.log("\n5. contradict_entry")

    const c = parseToolText(
      await client.callTool("contradict_entry", {
        entry_id: e2,
        conflicting_entry_id: e3,
        evidence_type: "cross_reference",
        evidence_ref: "observed code pattern",
      }),
    )
    check("contradict", c.conflicting_entry_id === e3)

    // --- error paths ---
    console.log("\n6. error paths")

    const err1 = parseToolText(
      await client.storeEntry({
        type: "not_a_real_type",
        content: "x",
        source: "agent_inference",
      }),
    )
    check("invalid type rejected", err1.error === true)

    const err2 = parseToolText(
      await client.callTool("link_entries", {
        source_id: "nonexistent-id",
        target_id: e1,
        relation_type: "related",
      }),
    )
    check("missing entry rejected", err2.error === true)

    console.log(`\n${"=".repeat(40)}`)
    console.log(`Plugin E2E: ${pass} passed, ${fail} failed`)
    if (fail > 0) process.exit(1)
  } finally {
    try { await client.close() } catch { /* ignore */ }
    for (const f of [DB_PATH, DB_PATH + "-wal", DB_PATH + "-shm"]) {
      if (existsSync(f)) unlinkSync(f)
    }
  }
}

main()
