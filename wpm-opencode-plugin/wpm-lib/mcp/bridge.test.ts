import { describe, expect, test } from "bun:test"
import { buildBridgedTools } from "./bridge"
import type { WpmMcpClient } from "./client"

function fakeClient(queryResult?: object): WpmMcpClient {
  return {
    toolsList: async () => [
      {
        name: "query_context",
        description: "Query.",
        inputSchema: {
          type: "object",
          properties: { query: { type: "string", title: "Query" } },
          required: ["query"],
        },
      },
      {
        name: "store_entry",
        description: "Store.",
        inputSchema: {
          type: "object",
          properties: { content: { type: "string", title: "Content" } },
          required: ["content"],
        },
      },
    ],
    callTool: async () => ({
      content: [{ type: "text", text: queryResult ? JSON.stringify(queryResult) : "ok" }],
    }),
  } as never
}

const CTX = (sessionID: string) =>
  ({
    sessionID,
    messageID: "m",
    agent: "build",
    directory: "/tmp",
    worktree: "/tmp",
    abort: new AbortController().signal,
    metadata: () => {},
    ask: async () => {},
  }) as never

describe("bridge query_context detection", () => {
  test("onQueryContext fires with the executing session id after query_context only", async () => {
    const seen: string[] = []
    const tools = await buildBridgedTools(fakeClient(), {
      onQueryContext: (sessionID) => seen.push(sessionID),
    })

    await tools["wpm_query_context"]!.execute({ query: "x" }, CTX("ses_a"))
    expect(seen).toEqual(["ses_a"])

    await tools["wpm_store_entry"]!.execute({ content: "y" }, CTX("ses_b"))
    expect(seen).toEqual(["ses_a"])
  })

  test("no callback registered: execution unaffected", async () => {
    const tools = await buildBridgedTools(fakeClient())
    const result = (await tools["wpm_query_context"]!.execute({ query: "x" }, CTX("ses_c"))) as { output: string }
    expect(result.output).toBe("ok")
  })
})
