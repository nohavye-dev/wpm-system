/**
 * Thin, independent MCP client used by the plugin to call the Python memory
 * server's tools deterministically from hooks (compaction, tool results,
 * session idle), regardless of whether OpenCode exposes internal access to
 * its own MCP connections to plugins.
 *
 * The plugin opens its own stdio connection to the same server process
 * definition as the one configured in opencode.json — this keeps the plugin
 * stateless and avoids any need to share connection state with the host.
 */

import { Client } from "@modelcontextprotocol/sdk/client/index.js"
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js"

export interface MemoryServerConfig {
  /** Command used to launch the Python MCP server, e.g. "python" or "uv" */
  command: string
  /** Arguments, e.g. ["-m", "wpm_mcp_server"] or ["run", "wpm-mcp-server"] */
  args: string[]
  /** Optional working directory for the server process */
  cwd?: string
  /** Optional extra environment variables (e.g. DB path) */
  env?: Record<string, string>
}

export class MemoryClient {
  private client: Client | null = null
  private connecting: Promise<Client> | null = null

  constructor(private readonly config: MemoryServerConfig) {}

  private async connect(): Promise<Client> {
    if (this.client) return this.client
    if (this.connecting) return this.connecting

    this.connecting = (async () => {
      const transport = new StdioClientTransport({
        command: this.config.command,
        args: this.config.args,
        cwd: this.config.cwd,
        env: { ...processEnv(), ...this.config.env },
      })

      const client = new Client(
        { name: "wpm-opencode-plugin", version: "0.1.0" },
        { capabilities: {} },
      )

      try {
        await client.connect(transport)
        this.client = client
        return client
      } catch (err) {
        // Reset the cached promise so a failed (or died) server is retried on
        // the next call instead of making every future call fail forever.
        this.connecting = null
        await client.close().catch(() => {})
        throw err
      }
    })()

    return this.connecting
  }

  /** Generic tool call, returns the raw MCP tool result content. */
  async callTool(name: string, args: Record<string, unknown>): Promise<unknown> {
    const client = await this.connect()
    try {
      const result = await client.callTool({ name, arguments: args })
      return result
    } catch (err) {
      // Never throw into an OpenCode hook — a memory-server hiccup must not
      // break the agent's session. Log and return a sentinel instead.
      console.error(`[wpm-opencode-plugin] tool call failed: ${name}`, err)
      return { error: true, message: String(err) }
    }
  }

  async storeEntry(input: {
    type: "doc" | "archi_decision" | "learning" | "convention" | "bug_pattern"
    content: string
    source: string
  }): Promise<unknown> {
    return this.callTool("store_entry", input)
  }

  async queryContext(input: {
    query: string
    min_confidence?: number
    token_budget?: number
  }): Promise<unknown> {
    return this.callTool("query_context", input)
  }

  async validateEntry(input: {
    entry_id: string
    evidence_type: "execution_verified" | "cross_reference" | "reuse_without_failure"
    evidence_ref: string
    session_id: string
  }): Promise<unknown> {
    return this.callTool("validate_entry", input)
  }

  async close(): Promise<void> {
    if (this.client) {
      await this.client.close()
      this.client = null
    }
    this.connecting = null
  }
}

function processEnv(): Record<string, string> {
  const env: Record<string, string> = {}
  for (const [k, v] of Object.entries(process.env)) {
    if (v !== undefined) env[k] = v
  }
  return env
}
