import { tool } from "@opencode-ai/plugin"
import type { McpJsonSchema, McpJsonSchemaProperty } from "./entities"

// The zod re-export shipped by the plugin SDK — never import "zod" directly,
// its presence in node_modules is incidental.
const z = tool.schema

export type ToolArgsShape = Parameters<typeof tool>[0]["args"]

// Minimal JSON Schema → ZodRawShape conversion for the dynamic tool bridge.
// The wpm schemas are simple (strings, numbers, booleans, string enums,
// nullable anyOf); anything exotic falls back to a permissive unknown.
// Validators are typed loosely at this boundary — the runtime contract is
// what opencode duck-types.
export function jsonSchemaToZodRawShape(schema: McpJsonSchema | undefined): ToolArgsShape {
  const shape: Record<string, any> = {}
  const properties = schema?.properties ?? {}
  const required = new Set(schema?.required ?? [])
  for (const [name, property] of Object.entries(properties)) {
    let validator: any = propertyValidator(property)
    if (!required.has(name)) {
      validator = validator.optional()
    }
    shape[name] = validator
  }
  return shape as ToolArgsShape
}

function propertyValidator(property: McpJsonSchemaProperty): any {
  const anyOf = Array.isArray(property.anyOf) ? property.anyOf : undefined
  if (anyOf) {
    const nonNull = anyOf.find((variant) => variant.type !== "null")
    let base: any = nonNull ? scalarValidator(nonNull.type, property) : z.unknown()
    if (anyOf.some((variant) => variant.type === "null")) {
      base = base.nullable()
    }
    return base
  }
  return scalarValidator(property.type, property)
}

function scalarValidator(type: string | undefined, property: McpJsonSchemaProperty): any {
  const enumValues = Array.isArray(property.enum) ? property.enum : []
  if (enumValues.length > 0 && enumValues.every((value) => typeof value === "string")) {
    return z.enum(enumValues as [string, ...string[]])
  }
  switch (type) {
    case "string":
      return z.string()
    case "integer":
    case "number":
      return z.number()
    case "boolean":
      return z.boolean()
    default:
      return z.unknown()
  }
}
