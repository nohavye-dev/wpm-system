import { describe, expect, test } from "bun:test"
import { createHooks, type HookDeps } from "./hooks"

function makeDeps(overrides: Partial<HookDeps> = {}): HookDeps {
  return {
    client: {
      session: { prompt: async () => ({}) },
      app: { log: async () => true },
    } as never,
    directory: "/tmp/project",
    nudge: "NUDGE",
    persistReminder: "PERSIST",
    nudged: new Set<string>(),
    queriedRecently: new Map<string, boolean>(),
    confidenceFloor: 0.5,
    ragSimilarityThreshold: 0.45,
    ragMaxItems: 3,
    ...overrides,
  }
}

describe("config hook", () => {
  test("does not register an MCP server entry (plugin owns the server)", async () => {
    const hooks = createHooks(
      makeDeps({
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

  test("grants wpm_* permission and plan exception", async () => {
    const hooks = createHooks(makeDeps())
    const config: any = {}
    await hooks.config!(config)
    expect(config.permission["wpm_*"]).toBe("allow")
    expect(config.agent.plan.permission["wpm_*"]).toBe("allow")
    expect(config.agent.plan.prompt).toContain("wpm_*")
  })
})

describe("system transform", () => {
  test("without mcp instance falls back to nudge alone", async () => {
    const hooks = createHooks(makeDeps())
    const output = { system: [] as string[] }
    await hooks["experimental.chat.system.transform"]!({ sessionID: "s", model: {} as never }, output as never)
    expect(output.system).toEqual(["NUDGE"])
  })

  test("degraded server still pushes golden rules + nudge", async () => {
    const hooks = createHooks(
      makeDeps({
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

  test("no tool bridge is exposed when server failed", () => {
    const hooks = createHooks(makeDeps())
    expect(hooks.tool).toBeUndefined()
  })
})

describe("record_execution", () => {
  test("degraded server is no-op (no fallback)", async () => {
    let calls = 0
    const hooks = createHooks(
      makeDeps({
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
    await hooks["tool.execute.after"]!(
      { tool: "bash", sessionID: "s", callID: "c", args: { command: "npm test" } },
      { title: "", output: "", metadata: { exit: 0 } } as never,
    )
    expect(calls).toBe(0)
  })

  test("warm server receives the call", async () => {
    let calls = 0
    const hooks = createHooks(
      makeDeps({
        mcp: {
          ready: async () => true,
          readResource: async () => undefined,
          callTool: async () => {
            calls++
            return {}
          },
        } as never,
      }),
    )
    await hooks["tool.execute.after"]!(
      { tool: "bash", sessionID: "s", callID: "c", args: { command: "npm test" } },
      { title: "", output: "", metadata: { exit: 0 } } as never,
    )
    expect(calls).toBe(1)
  })

  test("warm server failure is swallowed (no throw, no fallback)", async () => {
    const hooks = createHooks(
      makeDeps({
        mcp: {
          ready: async () => true,
          readResource: async () => undefined,
          callTool: async () => {
            throw new Error("boom")
          },
        } as never,
      }),
    )
    await expect(
      hooks["tool.execute.after"]!(
        { tool: "bash", sessionID: "s", callID: "c", args: { command: "npm test" } },
        { title: "", output: "", metadata: { exit: 0 } } as never,
      ),
    ).resolves.toBeUndefined()
  })
})

describe("agent-aware injections", () => {
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
      nudged: new Set<string>(),
    })
    const hooks = createHooks(deps)

    await (hooks as any).event({ event: { type: "session.idle", properties: { sessionID: "s1" } } })
    await (hooks as any)["tool.execute.before"]!({ tool: "read", sessionID: "s2", callID: "c" }, {} as never)

    expect(prompted.length).toBe(2)
    for (const p of prompted as Array<{ agent?: string; noReply?: boolean }>) {
      expect(p.agent).toBe("build")
    }
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
