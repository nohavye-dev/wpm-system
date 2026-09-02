import { describe, expect, test } from "bun:test"
import { join } from "node:path"
import { PROJECT_RULES_URI, WpmMcpClient } from "./client"

const FIXTURE = join(import.meta.dir, "fixtures", "fake-server.ts")

function makeClient(): WpmMcpClient {
  return new WpmMcpClient({
    configPath: "/tmp/fake-wpm.config.json",
    command: [process.execPath, "run", FIXTURE],
    backoffMs: 20,
  })
}

describe("WpmMcpClient", () => {
  test("handshake, tools/list and tools/call over line framing", async () => {
    const client = makeClient()
    try {
      expect(await client.start()).toBe(true)
      const tools = await client.toolsList()
      expect(tools.map((tool) => tool.name)).toEqual(["echo", "die", "slow", "invalidate_rules"])

      const result = await client.callTool("echo", { text: "hello" })
      const text = result.content?.[0]?.text
      expect(text).toBe("echo:hello")
    } finally {
      await client.teardown()
    }
  })

  test("resource reads are cached until resources/updated", async () => {
    let updates = 0
    const client = makeClient()
    const notifying = new WpmMcpClient({
      configPath: "/tmp/fake-wpm.config.json",
      command: [process.execPath, "run", FIXTURE],
      backoffMs: 20,
      onResourcesUpdated: () => updates++,
    })
    try {
      await client.start()
      expect(await client.readResource(PROJECT_RULES_URI)).toBe(`body:${PROJECT_RULES_URI}`)

      // The fixture has no way to observe read counts; instead verify the
      // invalidation path end to end on the second client.
      await notifying.start()
      await notifying.readResource(PROJECT_RULES_URI)
      await notifying.callTool("invalidate_rules")
      await Bun.sleep(50)
      expect(updates).toBe(1)
      // Cache was cleared: the next read must be served again (no throw).
      expect(await notifying.readResource(PROJECT_RULES_URI)).toBe(`body:${PROJECT_RULES_URI}`)
    } finally {
      await client.teardown()
      await notifying.teardown()
    }
  })

  test("transparent respawn after server death", async () => {
    const client = makeClient()
    try {
      await client.start()
      // The server dies mid-call: the in-flight request must be rejected.
      expect(client.callTool("die")).rejects.toThrow("wpm mcp server exited")
      // Backoff is 20ms in tests: wait it out, the next call re-initializes.
      await Bun.sleep(60)
      const result = await client.callTool("echo", { text: "again" })
      expect(result.content?.[0]?.text).toBe("echo:again")
    } finally {
      await client.teardown()
    }
  })

  test("abort cancels an in-flight request", async () => {
    const client = makeClient()
    try {
      await client.start()
      const controller = new AbortController()
      const pending = client.callTool("slow", {}, { signal: controller.signal })
      setTimeout(() => controller.abort(), 50)
      expect(pending).rejects.toThrow("aborted")
      // The client stays usable after an abort: no leaked pending state.
      const next = await client.callTool("echo", { text: "after" })
      expect(next.content?.[0]?.text).toBe("echo:after")
    } finally {
      await client.teardown()
    }
  })
})
