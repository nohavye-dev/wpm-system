import { describe, expect, test } from "bun:test"
import { createHooks, type HookDeps } from "./hooks"

function makeDeps(overrides: Partial<HookDeps> = {}): HookDeps {
  return {
    client: {
      session: { prompt: async () => ({}) },
      app: { log: async () => true },
    } as never,
    directory: "/tmp/legacy-project",
    nudge: "NUDGE",
    persistReminder: "PERSIST",
    nudged: new Set<string>(),
    queriedRecently: new Map<string, boolean>(),
    pluginMaster: false,
    confidenceFloor: 0.5,
    ragSimilarityThreshold: 0.45,
    ragMaxItems: 3,
    ...overrides,
  }
}

describe("legacy mode (plugin_master absent/false)", () => {
  test("config hook registers the wpm MCP server for opencode to host", async () => {
    const hooks = createHooks(makeDeps())
    const config: any = {}
    await hooks.config!(config)
    expect(config.mcp?.["wpm"]).toEqual({
      type: "local",
      command: [expect.stringContaining("python"), "-m", "wpm_mcp_server"],
      environment: { WPM_CONFIG_PATH: "/tmp/legacy-project/wpm.config.json" },
      enabled: true,
    })
  })

  test("transform pushes the nudge alone — no golden rules, no RAG", async () => {
    const hooks = createHooks(makeDeps({ goldenRules: "GOLDEN" }))
    const output = { system: [] as string[] }
    await hooks["experimental.chat.system.transform"]!({ sessionID: "s", model: {} as never }, output as never)
    expect(output.system).toEqual(["NUDGE"])
  })

  test("no tool bridge is exposed", () => {
    const hooks = createHooks(makeDeps())
    expect(hooks.tool).toBeUndefined()
  })
})

describe("plugin_master mode guards", () => {
  test("config hook does not register an MCP server entry", async () => {
    const hooks = createHooks(
      makeDeps({
        pluginMaster: true,
        mcp: {
          ready: async () => false,
          readResource: async () => undefined,
          callTool: async () => ({}),
        } as never,
      }),
    )
    const config: any = {}
    await hooks.config!(config)
    expect(config.mcp?.["wpm"]).toBeUndefined()
  })

  test("degraded server still pushes golden rules + nudge", async () => {
    const hooks = createHooks(
      makeDeps({
        pluginMaster: true,
        goldenRules: "GOLDEN",
        mcp: {
          ready: async () => false,
          readResource: async () => undefined,
          callTool: async () => ({}),
        } as never,
      }),
    )
    const output = { system: [] as string[] }
    await hooks["experimental.chat.system.transform"]!({ sessionID: "s", model: {} as never }, output as never)
    expect(output.system).toEqual(["GOLDEN", "NUDGE"])
  })

  test("master without mcp instance falls back to nudge alone", async () => {
    const hooks = createHooks(makeDeps({ pluginMaster: true }))
    const output = { system: [] as string[] }
    await hooks["experimental.chat.system.transform"]!({ sessionID: "s", model: {} as never }, output as never)
    expect(output.system).toEqual(["NUDGE"])
  })

  test("record_execution: degraded server never receives the call (CLI net takes over)", async () => {
    let calls = 0
    const hooks = createHooks(
      makeDeps({
        pluginMaster: true,
        mcp: {
          ready: async () => false,
          readResource: async () => undefined,
          callTool: async () => {
            calls++
            return {}
          },
        } as never,
      }),
    )
    // The bash branch falls through to the standalone CLI net; what matters
    // here is that the warm path is not attempted and nothing throws.
    await hooks["tool.execute.after"]!(
      { tool: "bash", sessionID: "s", callID: "c", args: { command: "npm test" } },
      { title: "", output: "", metadata: { exit: 0 } } as never,
    )
    expect(calls).toBe(0)
  })

  test("injected prompts carry the session's live agent, never a hardcoded one", async () => {
    const prompted: Array<{ agent?: string; noReply?: boolean }> = []
    const clientStub = {
      session: {
        get: async () => ({ data: { agent: "build" } }),
        prompt: async ({ body }: { body: { agent?: string; noReply?: boolean } }) => {
          prompted.push({ agent: body.agent, noReply: body.noReply })
          return {}
        },
        messages: async () => ({ data: [] }),
      },
      app: { log: async () => true },
    }
    const deps = makeDeps({
      client: clientStub as never,
      pluginMaster: true,
      nudged: new Set<string>(),
    })
    const hooks = createHooks(deps)

    // idle net
    await (hooks as any).event({ event: { type: "session.idle", properties: { sessionID: "s1" } } })
    // memory-first nudge (read without prior query)
    await (hooks as any)["tool.execute.before"]!({ tool: "read", sessionID: "s2", callID: "c" }, {} as never)

    expect(prompted.length).toBe(2)
    for (const p of prompted as Array<{ agent?: string; noReply?: boolean }>) {
      expect(p.agent).toBe("build")
    }
    // first injection is the persist pass (expects a reply), second the noReply nudge
    expect(prompted[0]!.noReply).toBe(false)
    expect(prompted[1]!.noReply).toBe(true)
  })

  test("session.get failure degrades to agent-less injection", async () => {
    const prompted: Array<{ agent?: string }> = []
    const clientStub = {
      session: {
        get: async () => {
          throw new Error("boom")
        },
        prompt: async ({ body }: { body: { agent?: string } }) => {
          prompted.push({ agent: body.agent })
          return {}
        },
        messages: async () => ({ data: [] }),
      },
      app: { log: async () => true },
    }
    const hooks = createHooks(makeDeps({ client: clientStub as never }))
    await (hooks as any).event({ event: { type: "session.idle", properties: { sessionID: "s1" } } })
    expect(prompted.length).toBe(1)
    expect(prompted[0]!.agent).toBeUndefined()
  })
})
