import { describe, expect, test } from "bun:test"
import { createHooks, type HookDeps } from "./hooks"

function makeDeps(overrides: Partial<HookDeps> = {}): HookDeps {
  return {
    client: {
      session: { prompt: async () => ({}) },
      app: { log: async () => true },
    } as never,
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
    await hooks.config?.(config)
    expect(config.mcp?.wpm).toBeUndefined()
  })

  test("grants wpm_* permission and plan exception", async () => {
    const hooks = createHooks(makeDeps())
    const config: any = {}
    await hooks.config?.(config)
    expect(config.permission["wpm_*"]).toBe("allow")
    expect(config.agent.plan.permission["wpm_*"]).toBe("allow")
    expect(config.agent.plan.prompt).toContain("wpm_*")
  })

  test("registers wpm-* slash commands and is idempotent", async () => {
    const hooks = createHooks(makeDeps())
    const config: any = {
      command: { "wpm-persist": { template: "existing", description: "keep", agent: "plan" } },
    }
    await hooks.config?.(config)
    // Existing command is kept
    expect(config.command["wpm-persist"].template).toBe("existing")
    // Other wpm commands are added
    expect(config.command["wpm-audit"]).toBeDefined()
    expect(config.command["wpm-learn"]).toBeDefined()
    expect(config.command["wpm-audit"].agent).toBe("plan")
  })
})

describe("system transform", () => {
  test("without mcp instance falls back to nudge alone", async () => {
    const hooks = createHooks(makeDeps())
    const output = { system: [] as string[] }
    await hooks["experimental.chat.system.transform"]?.(
      { sessionID: "s", model: {} as never },
      output as never,
    )
    expect(output.system).toEqual(["NUDGE"])
  })

  test("without mcp but with goldenRules pushes both", async () => {
    const hooks = createHooks(makeDeps({ goldenRules: "GOLDEN" }))
    const output = { system: [] as string[] }
    await hooks["experimental.chat.system.transform"]?.(
      { sessionID: "s", model: {} as never },
      output as never,
    )
    expect(output.system).toEqual(["GOLDEN", "NUDGE"])
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
    await hooks["experimental.chat.system.transform"]?.(
      { sessionID: "s", model: {} as never },
      output as never,
    )
    expect(output.system).toEqual(["GOLDEN", "NUDGE"])
  })

  test("warm server pushes golden + current-user + rules + RAG + nudge", async () => {
    const mcp = {
      ready: async () => true,
      readResource: async (uri: string) =>
        uri === "wpm://project-rules" ? "<project-rules> RULES </project-rules>" : undefined,
      readCurrentUser: async () => "<current-user> USER </current-user>",
      callTool: async () => ({
        content: [
          {
            type: "text",
            text: JSON.stringify({ direct_matches: [], related_context: [], conflicts: [] }),
          },
        ],
        structuredContent: { direct_matches: [], related_context: [], conflicts: [] },
      }),
    } as never
    const _hooks = createHooks(makeDeps({ goldenRules: "GOLDEN", mcp }))
    const clientStub = {
      session: { messages: async () => ({ data: [] }) },
      app: { log: async () => true },
    }
    // Inject client for lastUserMessageText
    const deps = makeDeps({ goldenRules: "GOLDEN", mcp, client: clientStub as never })
    const hooks2 = createHooks(deps)
    const output = { system: [] as string[] }
    await hooks2["experimental.chat.system.transform"]?.(
      { sessionID: "s", model: {} as never },
      output as never,
    )
    // Order: golden, current-user, project-rules, nudge (no RAG because no user message)
    expect(output.system[0]).toBe("GOLDEN")
    expect(output.system[output.system.length - 1]).toBe("NUDGE")
    expect(output.system.join("\n")).toContain("USER")
    expect(output.system.join("\n")).toContain("RULES")
  })

  test("no tool bridge is exposed when server failed", () => {
    const hooks = createHooks(makeDeps())
    expect(hooks.tool).toBeUndefined()
  })
})

describe("record_execution", () => {
  test("degraded server is no-op with warn log", async () => {
    const logs: any[] = []
    let calls = 0
    const hooks = createHooks(
      makeDeps({
        client: {
          session: { prompt: async () => ({}) },
          app: {
            log: async (arg: any) => {
              logs.push(arg)
              return true
            },
          },
        } as never,
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
    await hooks["tool.execute.after"]?.(
      { tool: "bash", sessionID: "s", callID: "c", args: { command: "npm test" } },
      { title: "", output: "", metadata: { exit: 0 } } as never,
    )
    expect(calls).toBe(0)
    expect(logs.some((l) => l.body.message.includes("degraded"))).toBe(true)
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
    await hooks["tool.execute.after"]?.(
      { tool: "bash", sessionID: "s", callID: "c", args: { command: "npm test" } },
      { title: "", output: "", metadata: { exit: 0 } } as never,
    )
    expect(calls).toBe(1)
  })

  test("warm server failure is swallowed with degraded log", async () => {
    const logs: any[] = []
    const hooks = createHooks(
      makeDeps({
        client: {
          session: { prompt: async () => ({}) },
          app: {
            log: async (arg: any) => {
              logs.push(arg)
              return true
            },
          },
        } as never,
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
      hooks["tool.execute.after"]?.(
        { tool: "bash", sessionID: "s", callID: "c", args: { command: "npm test" } },
        { title: "", output: "", metadata: { exit: 0 } } as never,
      ),
    ).resolves.toBeUndefined()
    expect(logs.some((l) => l.body.message.includes("degraded"))).toBe(true)
  })

  test("trivial command returning error is not logged as degraded", async () => {
    const logs: any[] = []
    const hooks = createHooks(
      makeDeps({
        client: {
          session: { prompt: async () => ({}) },
          app: {
            log: async (arg: any) => {
              logs.push(arg)
              return true
            },
          },
        } as never,
        mcp: {
          ready: async () => true,
          readResource: async () => undefined,
          callTool: async () => ({ error: true, message: "trivial" }),
        } as never,
      }),
    )
    await hooks["tool.execute.after"]?.(
      { tool: "bash", sessionID: "s", callID: "c", args: { command: "ls" } },
      { title: "", output: "", metadata: { exit: 0 } } as never,
    )
    expect(logs.length).toBe(0)
  })

  test("non-bash tool is ignored", async () => {
    const hooks = createHooks(
      makeDeps({
        mcp: {
          ready: async () => true,
          callTool: async () => {
            throw new Error("should not be called")
          },
        } as never,
      }),
    )
    await hooks["tool.execute.after"]?.({ tool: "read", sessionID: "s", callID: "c", args: {} }, {
      title: "",
      output: "",
      metadata: {},
    } as never)
  })

  test("query_context sets queriedRecently", async () => {
    const deps = makeDeps()
    const hooks = createHooks(deps)
    await hooks["tool.execute.after"]?.(
      { tool: "wpm_query_context", sessionID: "s", callID: "c", args: {} },
      { title: "", output: "", metadata: {} } as never,
    )
    expect(deps.queriedRecently.get("s")).toBe(true)
  })
})

describe("chat.message and command hooks", () => {
  test("chat.message re-arms nudged unless synthetic", async () => {
    const deps = makeDeps({ nudged: new Set(["s"]) })
    const hooks = createHooks(deps)
    await hooks["chat.message"]?.(
      { sessionID: "s" } as never,
      { parts: [{ type: "text", metadata: {} }] } as never,
    )
    expect(deps.nudged.has("s")).toBe(false)
    deps.nudged.add("s")
    await hooks["chat.message"]?.(
      { sessionID: "s" } as never,
      {
        parts: [{ type: "text", metadata: { wpm_no_persist_rearm: true }, synthetic: true }],
      } as never,
    )
    expect(deps.nudged.has("s")).toBe(true)
  })

  test("command.execute.before masks wpm command and suppresses persist", async () => {
    const deps = makeDeps({ nudged: new Set<string>() })
    const hooks = createHooks(deps)
    const output: any = { parts: [{ type: "text", text: "long template" }] }
    await hooks["command.execute.before"]?.(
      { command: "wpm-persist", arguments: "", sessionID: "s" } as never,
      output,
    )
    expect(deps.nudged.has("s")).toBe(true)
    expect(output.parts[0].text).toBe("/wpm-persist")
    expect(output.parts[1].synthetic).toBe(true)
  })
})

describe("tool.execute.before memory-first", () => {
  test("triggers on read without queriedRecently", async () => {
    const prompted: any[] = []
    const clientStub = {
      session: {
        get: async () => ({ data: { agent: "build" } }),
        prompt: async (arg: any) => {
          prompted.push(arg)
          return {}
        },
        messages: async () => ({ data: [] }),
      },
      app: { log: async () => true },
    }
    const deps = makeDeps({ client: clientStub as never })
    const hooks = createHooks(deps)
    await hooks["tool.execute.before"]?.(
      { tool: "read", sessionID: "s", callID: "c" } as never,
      {} as never,
    )
    expect(prompted.length).toBe(1)
  })

  test("skips when queriedRecently is set", async () => {
    const prompted: any[] = []
    const clientStub = {
      session: {
        get: async () => ({ data: { agent: "build" } }),
        prompt: async (arg: any) => {
          prompted.push(arg)
          return {}
        },
        messages: async () => ({ data: [] }),
      },
      app: { log: async () => true },
    }
    const deps = makeDeps({ client: clientStub as never, queriedRecently: new Map([["s", true]]) })
    const hooks = createHooks(deps)
    await hooks["tool.execute.before"]?.(
      { tool: "read", sessionID: "s", callID: "c" } as never,
      {} as never,
    )
    expect(prompted.length).toBe(0)
  })

  test("ignores non-read tools", async () => {
    const prompted: any[] = []
    const clientStub = {
      session: {
        get: async () => ({ data: { agent: "build" } }),
        prompt: async (arg: any) => {
          prompted.push(arg)
          return {}
        },
        messages: async () => ({ data: [] }),
      },
      app: { log: async () => true },
    }
    const deps = makeDeps({ client: clientStub as never })
    const hooks = createHooks(deps)
    await hooks["tool.execute.before"]?.(
      { tool: "bash", sessionID: "s", callID: "c" } as never,
      {} as never,
    )
    expect(prompted.length).toBe(0)
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
    await (hooks as any)["tool.execute.before"]?.(
      { tool: "read", sessionID: "s2", callID: "c" },
      {} as never,
    )

    expect(prompted.length).toBe(2)
    for (const p of prompted as Array<{ agent?: string; noReply?: boolean }>) {
      expect(p.agent).toBe("build")
    }
    expect(prompted[0]?.noReply).toBe(false)
    expect(prompted[1]?.noReply).toBe(true)
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
    expect(prompted[0]?.agent).toBeUndefined()
  })

  test("session.idle is deduped by nudged set", async () => {
    let calls = 0
    const clientStub = {
      session: {
        get: async () => ({ data: { agent: "build" } }),
        prompt: async () => {
          calls++
          return {}
        },
        messages: async () => ({ data: [] }),
      },
      app: { log: async () => true },
    }
    const deps = makeDeps({ client: clientStub as never, nudged: new Set<string>(["s1"]) })
    const hooks = createHooks(deps)
    await (hooks as any).event({ event: { type: "session.idle", properties: { sessionID: "s1" } } })
    expect(calls).toBe(0)
  })
})
