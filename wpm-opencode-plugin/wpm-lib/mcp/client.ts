import type { Subprocess } from "bun"
import { spawn } from "bun"
import { resolvePythonPath } from "../infra/paths"
import {
  isResponse,
  type JsonRpcMessage,
  type McpCallToolResult,
  type McpReadResourceResult,
  type McpToolDefinition,
} from "./entities"

const PROTOCOL_VERSION = "2025-06-18"
const CLIENT_INFO = { name: "wpm-opencode-plugin", version: "1.0.0" }
export const PROJECT_RULES_URI = "wpm://project-rules"
export const CURRENT_USER_URI = "wpm://current-user"
const MEMORY_RULES_URI = "wpm://memory-rules"

const INIT_TIMEOUT_MS = 10_000
const REQUEST_TIMEOUT_MS = 30_000
const TEARDOWN_KILL_GRACE_MS = 1_500

// A death right after spawn means a broken interpreter/venv, not a transient
// crash: back off exponentially so a missing binary does not turn every tool
// call into a spawn loop.
const RESPAWN_BASE_DELAY_MS = 1_000
const RESPAWN_MAX_DELAY_MS = 15_000
const STABLE_AFTER_MS = 10_000

type PendingRequest = {
  resolve: (value: unknown) => void
  reject: (error: Error) => void
  timer: ReturnType<typeof setTimeout>
  // Clears the timeout and detaches the abort listener; every exit path
  // (response, timeout, abort, death, teardown, send failure) must run it.
  dispose: () => void
}

// Hand-rolled MCP client owning the wpm server subprocess (stdio, JSON-RPC
// line-delimited). The plugin is the single master of the server lifecycle:
// lazy start, transparent respawn on death, teardown on process exit.
// Requests are correlated by incrementing id; notifications are routed to
// handlers (resources/updated invalidates the resource cache).
export class WpmMcpClient {
  private readonly configPath: string
  private readonly command?: string[]
  private readonly backoffMs: number
  // Extra environment merged over process.env for the server subprocess.
  private readonly extraEnv?: Record<string, string>
  private readonly onResourcesUpdated?: () => void
  private proc?: Subprocess<"pipe", "pipe", "pipe">
  private nextId = 1
  private pending = new Map<number, PendingRequest>()
  private initialized = false
  private starting?: Promise<boolean>
  private closed = false
  private exitedAt?: number
  private spawnedAt?: number
  private quickDeathStreak = 0
  private lastFailureAt?: number
  private resourceCache = new Map<string, string>()

  constructor(options: {
    configPath: string
    command?: string[]
    backoffMs?: number
    env?: Record<string, string>
    onResourcesUpdated?: () => void
  }) {
    this.configPath = options.configPath
    this.command = options.command
    this.backoffMs = options.backoffMs ?? RESPAWN_BASE_DELAY_MS
    this.extraEnv = options.env
    this.onResourcesUpdated = options.onResourcesUpdated
  }

  // Resolves true once the handshake completed; false in degraded mode
  // (server unreachable) — callers degrade gracefully and later calls retry.
  start(): Promise<boolean> {
    this.starting ??= this.initialize()
      .then(() => {
        this.lastFailureAt = undefined
        return true
      })
      .catch(() => {
        this.starting = undefined
        this.lastFailureAt = Date.now()
        return false
      })
    return this.starting
  }

  async ready(): Promise<boolean> {
    if (this.closed) return false
    if (this.isAlive() && this.initialized) return true
    // Fail fast within the current backoff window so per-turn hooks never
    // stall on a known-broken server; a later turn retries fresh.
    if (
      this.lastFailureAt !== undefined &&
      Date.now() - this.lastFailureAt < this.respawnDelayMs()
    ) {
      return false
    }
    return this.start()
  }

  async toolsList(): Promise<McpToolDefinition[]> {
    const result = await this.call("tools/list")
    const tools = (result as { tools?: McpToolDefinition[] })?.tools
    return Array.isArray(tools) ? tools : []
  }

  async callTool(
    name: string,
    args?: Record<string, unknown>,
    opts?: { signal?: AbortSignal },
  ): Promise<McpCallToolResult> {
    return (await this.call(
      "tools/call",
      { name, arguments: args ?? {} },
      REQUEST_TIMEOUT_MS,
      opts?.signal,
    )) as McpCallToolResult
  }

  // Resource contents are cached until the server signals a change via
  // resources/updated — the warm path pays one stdio round-trip only.
  async readResource(uri: string): Promise<string | undefined> {
    const cached = this.resourceCache.get(uri)
    if (cached !== undefined) return cached
    const result = (await this.call("resources/read", { uri })) as McpReadResourceResult
    const text = result?.contents?.find((c) => typeof c.text === "string")?.text
    if (typeof text === "string") this.resourceCache.set(uri, text)
    return text
  }

  readProjectRules(): Promise<string | undefined> {
    return this.readResource(PROJECT_RULES_URI)
  }

  // Fresh read, deliberately bypassing the resource cache: users.db is
  // written by other processes (CLI current-user switch, another session's
  // recordings), so no resources/updated notification can ever fire for it.
  async readCurrentUser(): Promise<string | undefined> {
    const result = (await this.call("resources/read", {
      uri: CURRENT_USER_URI,
    })) as McpReadResourceResult
    return result?.contents?.find((c) => typeof c.text === "string")?.text
  }

  readMemoryRules(): Promise<string | undefined> {
    return this.readResource(MEMORY_RULES_URI)
  }

  killSync(): void {
    this.closed = true
    try {
      this.proc?.stdin?.end()
    } catch {}
    try {
      this.proc?.kill()
    } catch {}
    this.rejectPending(new Error("wpm mcp client torn down"))
  }

  async teardown(): Promise<void> {
    if (!this.proc || this.closed) return
    this.killSync()
    await Promise.race([
      this.proc.exited,
      new Promise((resolve) => setTimeout(resolve, TEARDOWN_KILL_GRACE_MS)),
    ])
    try {
      this.proc.kill(9)
    } catch {}
  }

  private isAlive(): boolean {
    return !!this.proc && this.exitedAt === undefined && !this.closed
  }

  private async initialize(): Promise<boolean> {
    this.spawnProcess()
    await this.rawCall(
      "initialize",
      {
        protocolVersion: PROTOCOL_VERSION,
        capabilities: {},
        clientInfo: CLIENT_INFO,
      },
      INIT_TIMEOUT_MS,
    )
    this.send({ jsonrpc: "2.0", method: "notifications/initialized" })
    this.initialized = true
    this.subscribe(PROJECT_RULES_URI)
    return true
  }

  // Spec-correct subscription; FastMCP broadcasts resources/updated either
  // way, but subscribing costs nothing and keeps us honest with the spec.
  private subscribe(uri: string): void {
    this.rawCall("resources/subscribe", { uri }, REQUEST_TIMEOUT_MS).catch(() => {})
  }

  private respawnDelayMs(): number {
    return Math.min(this.backoffMs * 2 ** this.quickDeathStreak, RESPAWN_MAX_DELAY_MS)
  }

  private spawnProcess(): void {
    if (this.closed) throw new Error("wpm mcp client torn down")
    if (this.exitedAt !== undefined) {
      const sinceDeath = Date.now() - this.exitedAt
      const delay = this.respawnDelayMs()
      if (sinceDeath < delay) {
        throw new Error(`wpm mcp server restarting (backoff ${Math.ceil(delay - sinceDeath)}ms)`)
      }
    }
    if (this.proc) {
      // Orphaned process from a failed handshake: terminate before replacing.
      try {
        this.proc.stdin?.end()
        this.proc.kill()
      } catch {}
      this.proc = undefined
    }
    this.spawnedAt = Date.now()
    this.exitedAt = undefined
    const proc = spawn({
      cmd: this.command ?? [resolvePythonPath(), "-m", "wpm_mcp_server"],
      env: { ...process.env, WPM_CONFIG_PATH: this.configPath, ...this.extraEnv },
      stdin: "pipe",
      stdout: "pipe",
      stderr: "pipe",
    })
    this.proc = proc
    this.readStdout(proc)
    void this.drainStderr(proc)
    void proc.exited.then(() => this.handleExit())
  }

  private handleExit(): void {
    this.exitedAt = Date.now()
    this.initialized = false
    this.starting = undefined
    this.resourceCache.clear()
    const lifetime = this.spawnedAt ? this.exitedAt - this.spawnedAt : Infinity
    this.quickDeathStreak = lifetime < STABLE_AFTER_MS ? this.quickDeathStreak + 1 : 0
    this.rejectPending(new Error("wpm mcp server exited"))
  }

  private rejectPending(error: Error): void {
    for (const [id, pending] of this.pending) {
      pending.dispose()
      pending.reject(error)
      this.pending.delete(id)
    }
  }

  // The line buffer is local to each reader loop: a dying process's tail
  // decode can never leak into the next spawn's stream.
  private readStdout(proc: Subprocess<"pipe", "pipe", "pipe">): void {
    void (async () => {
      const decoder = new TextDecoder()
      let buffer = ""
      try {
        for await (const chunk of proc.stdout) {
          buffer += decoder.decode(chunk, { stream: true })
          let newline = buffer.indexOf("\n")
          while (newline >= 0) {
            const line = buffer.slice(0, newline).trim()
            buffer = buffer.slice(newline + 1)
            if (!line) {
              newline = buffer.indexOf("\n")
              continue
            }
            this.handleLine(line)
            newline = buffer.indexOf("\n")
          }
        }
      } catch {}
    })()
  }

  private async drainStderr(proc: Subprocess<"pipe", "pipe", "pipe">): Promise<void> {
    try {
      for await (const _chunk of proc.stderr) {
        // Drained to prevent pipe backpressure from stalling the server;
        // the embedding loader detours its own stderr while loading anyway.
      }
    } catch {}
  }

  private handleLine(line: string): void {
    let message: JsonRpcMessage
    try {
      message = JSON.parse(line)
    } catch {
      return
    }
    if (isResponse(message)) {
      const pending = this.pending.get(message.id as number)
      if (!pending) return
      pending.dispose()
      this.pending.delete(message.id as number)
      if (message.error) {
        pending.reject(new Error(`MCP error ${message.error.code}: ${message.error.message}`))
      } else {
        pending.resolve(message.result)
      }
      return
    }
    if ("method" in message && typeof message.method === "string") {
      if (message.method === "notifications/resources/updated") {
        this.resourceCache.delete(PROJECT_RULES_URI)
        this.onResourcesUpdated?.()
        return
      }
      if (message.method === "ping" && "id" in message) {
        this.send({ jsonrpc: "2.0", id: message.id as number, result: {} })
      }
    }
  }

  private send(message: Record<string, unknown>): void {
    const stdin = this.proc?.stdin
    if (!stdin) throw new Error("wpm mcp server not running")
    stdin.write(`${JSON.stringify(message)}\n`)
  }

  private async call(
    method: string,
    params?: Record<string, unknown>,
    timeoutMs = REQUEST_TIMEOUT_MS,
    signal?: AbortSignal,
  ): Promise<unknown> {
    if (this.closed) throw new Error("wpm mcp client torn down")
    if (!this.isAlive() || !this.initialized) {
      // Delegating to start() keeps failure bookkeeping (lastFailureAt for
      // ready()'s fail-fast) identical on every re-init path.
      const ok = await this.start()
      if (!ok) throw new Error("wpm mcp server unavailable")
    }
    return this.rawCall(method, params, timeoutMs, signal)
  }

  private rawCall(
    method: string,
    params: unknown,
    timeoutMs: number,
    signal?: AbortSignal,
  ): Promise<unknown> {
    const id = this.nextId++
    let onAbort: (() => void) | undefined
    const promise = new Promise<unknown>((resolve, reject) => {
      const dispose = () => {
        clearTimeout(timer)
        signal?.removeEventListener("abort", onAbort as EventListener)
      }
      const timer = setTimeout(() => {
        const pending = this.pending.get(id)
        if (!pending) return
        pending.dispose()
        this.pending.delete(id)
        reject(new Error(`wpm mcp request timed out after ${timeoutMs}ms: ${method}`))
      }, timeoutMs)
      onAbort = () => {
        const pending = this.pending.get(id)
        if (!pending) return
        pending.dispose()
        this.pending.delete(id)
        reject(new Error(`wpm mcp request aborted: ${method}`))
        // Spec-correct cancellation; the server is free to ignore it.
        try {
          this.send({
            jsonrpc: "2.0",
            method: "notifications/cancelled",
            params: { requestId: id },
          })
        } catch {}
      }
      this.pending.set(id, { resolve, reject, timer, dispose })
      if (signal?.aborted) {
        onAbort?.()
      } else {
        signal?.addEventListener("abort", onAbort as EventListener, { once: true })
      }
    })
    try {
      this.send({ jsonrpc: "2.0", id, method, ...(params ? { params } : {}) })
    } catch (error) {
      const pending = this.pending.get(id)
      if (pending) {
        pending.dispose()
        this.pending.delete(id)
        pending.reject(error as Error)
      }
    }
    return promise
  }
}
