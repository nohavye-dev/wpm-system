import { describe, expect, test } from "bun:test"
import { tool } from "@opencode-ai/plugin"
import { jsonSchemaToZodRawShape } from "./schema"

describe("jsonSchemaToZodRawShape", () => {
  test("store_entry-like schema: enum required fields", () => {
    const shape = jsonSchemaToZodRawShape({
      type: "object",
      properties: {
        type: { enum: ["doc", "insight"], title: "Type", type: "string" },
        content: { title: "Content", type: "string" },
        source: { enum: ["official_doc", "observed_code"], title: "Source", type: "string" },
      },
      required: ["type", "content", "source"],
    }) as Record<string, any>
    expect(shape.type?.parse("doc")).toBe("doc")
    expect(() => shape.type?.parse("nope")).toThrow()
    expect(shape.content?.parse("x")).toBe("x")
    expect(shape.source?.safeParse("observed_code").success).toBe(true)
  })

  test("list_entries-like schema: nullable optionals with defaults omitted", () => {
    const shape = jsonSchemaToZodRawShape({
      type: "object",
      properties: {
        status: { anyOf: [{ type: "string" }, { type: "null" }], default: null, title: "Status" },
        limit: { default: 50, title: "Limit", type: "integer" },
        offset: { default: 0, title: "Offset", type: "integer" },
      },
    }) as Record<string, any>
    expect(shape.status?.safeParse(undefined).success).toBe(true)
    expect(shape.status?.safeParse(null).success).toBe(true)
    expect(shape.status?.safeParse("active").success).toBe(true)
    expect(shape.limit?.parse(10)).toBe(10)
  })

  test("record_execution-like schema: boolean required", () => {
    const shape = jsonSchemaToZodRawShape({
      type: "object",
      properties: {
        command: { title: "Command", type: "string" },
        succeeded: { title: "Succeeded", type: "boolean" },
      },
      required: ["command", "succeeded"],
    }) as Record<string, any>
    expect(shape.succeeded?.parse(true)).toBe(true)
    expect(() => shape.succeeded?.parse("yes")).toThrow()
  })

  test("empty and exotic schemas degrade permissively", () => {
    const empty = jsonSchemaToZodRawShape({ type: "object", properties: {} })
    expect(Object.keys(empty)).toEqual([])
    const exotic = jsonSchemaToZodRawShape({
      type: "object",
      properties: { weird: { type: "array", items: { type: "number" } } },
      required: ["weird"],
    }) as Record<string, any>
    expect(exotic.weird.safeParse([1, 2]).success).toBe(true)

    const definition = tool({
      description: "",
      args: exotic as never,
      execute: async () => ({ output: "ok" }),
    })
    expect(definition.execute({ weird: [1] } as never, {} as never)).resolves.toEqual({
      output: "ok",
    })
  })
})
