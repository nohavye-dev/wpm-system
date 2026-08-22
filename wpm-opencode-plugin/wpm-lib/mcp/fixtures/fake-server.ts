// Fake stdio MCP server used by client.test.ts: enough of the protocol to
// exercise the handshake, tools/list, tools/call, resources/read, the
// resources/updated notification and process death.

type Message = {
  jsonrpc: "2.0"
  id?: number
  method?: string
  params?: Record<string, unknown>
}

const decoder = new TextDecoder()
let buffer = ""

function send(message: Record<string, unknown>): void {
  process.stdout.write(JSON.stringify(message) + "\n")
}

function handle(message: Message): void {
  if (message.id === undefined || message.id === null) {
    return
  }
  switch (message.method) {
    case "initialize":
      send({
        jsonrpc: "2.0",
        id: message.id,
        result: {
          protocolVersion: "2025-06-18",
          capabilities: { tools: {}, resources: { subscribe: true } },
          serverInfo: { name: "fake-wpm", version: "0.0.0" },
        },
      })
      break
    case "tools/list":
      send({
        jsonrpc: "2.0",
        id: message.id,
        result: {
          tools: [
            {
              name: "echo",
              description: "Echoes the text argument.",
              inputSchema: {
                type: "object",
                properties: { text: { type: "string", title: "Text" } },
                required: ["text"],
              },
            },
            {
              name: "die",
              description: "Exits the process.",
              inputSchema: { type: "object", properties: {} },
            },
            {
              name: "slow",
              description: "Responds after five seconds.",
              inputSchema: { type: "object", properties: {} },
            },
            {
              name: "invalidate_rules",
              description: "Sends resources/updated.",
              inputSchema: { type: "object", properties: {} },
            },
          ],
        },
      })
      break
    case "tools/call": {
      const args = (message.params?.arguments ?? {}) as Record<string, unknown>
      if (message.params?.name === "die") {
        process.exit(1)
      }
      if (message.params?.name === "slow") {
        // Stays pending long enough for an abort test to cancel it.
        setTimeout(() => {
          send({ jsonrpc: "2.0", id: message.id, result: { content: [{ type: "text", text: "finally" }] } })
        }, 5_000)
        break
      }
      if (message.params?.name === "invalidate_rules") {
        send({
          jsonrpc: "2.0",
          method: "notifications/resources/updated",
          params: { uri: "wpm://project-rules" },
        })
        send({ jsonrpc: "2.0", id: message.id, result: { content: [{ type: "text", text: "invalidated" }] } })
        break
      }
      send({
        jsonrpc: "2.0",
        id: message.id,
        result: { content: [{ type: "text", text: `echo:${String(args.text ?? "")}` }] },
      })
      break
    }
    case "resources/read":
      send({
        jsonrpc: "2.0",
        id: message.id,
        result: {
          contents: [{ uri: String(message.params?.uri), text: `body:${String(message.params?.uri)}` }],
        },
      })
      break
    case "resources/subscribe":
      send({ jsonrpc: "2.0", id: message.id, result: {} })
      break
    case "ping":
      send({ jsonrpc: "2.0", id: message.id, result: {} })
      break
    default:
      send({
        jsonrpc: "2.0",
        id: message.id,
        error: { code: -32601, message: `method not found: ${message.method}` },
      })
  }
}

process.stdin.on("data", (chunk: Uint8Array) => {
  buffer += decoder.decode(chunk, { stream: true })
  let newline = buffer.indexOf("\n")
  while (newline >= 0) {
    const line = buffer.slice(0, newline).trim()
    buffer = buffer.slice(newline + 1)
    if (line) {
      try {
        handle(JSON.parse(line) as Message)
      } catch {}
    }
    newline = buffer.indexOf("\n")
  }
})

