import { tool } from "@opencode-ai/plugin"
import type { ToolDefinition } from "@opencode-ai/plugin"
import type { McpCallToolResult, McpToolDefinition } from "./entities"
import { jsonSchemaToZodRawShape } from "./schema"
import { SERVER_NAME } from "../core/constants"
import type { WpmMcpClient } from "./client"

// Dynamic bridge: every tool of the warm MCP server is re-exposed as a
// plugin tool named `wpm_<tool>` (the name identity the permission rules,
// the plan-mode exception and the query_context detection rely on).
// Descriptions are reused verbatim — single source stays server-side.
export async function buildBridgedTools(
  client: WpmMcpClient,
): Promise<Record<string, ToolDefinition>> {
  const definitions = await client.toolsList()
  const bridged: Record<string, ToolDefinition> = {}
  for (const definition of definitions) {
    bridged[`${SERVER_NAME}_${definition.name}`] = toPluginTool(client, definition)
  }
  return bridged
}

function toPluginTool(client: WpmMcpClient, definition: McpToolDefinition): ToolDefinition {
  return tool({
    description: definition.description ?? "",
    args: jsonSchemaToZodRawShape(definition.inputSchema),
    execute: async (args, context) =>
      serializeResult(await client.callTool(definition.name, args as Record<string, unknown>, { signal: context.abort })),
  })
}

function serializeResult(result: McpCallToolResult | undefined): { output: string } {
  if (!result) return { output: "" }
  if (result.isError) {
    throw new Error(textOf(result) || "wpm tool returned an error")
  }
  const text = textOf(result)
  if (text) return { output: text }
  if (result.structuredContent != null) {
    return { output: JSON.stringify(result.structuredContent) }
  }
  return { output: "" }
}

function textOf(result: McpCallToolResult): string {
  return (result.content ?? [])
    .filter((block) => block.type === "text" && typeof block.text === "string" && block.text.trim())
    .map((block) => block.text)
    .join("\n\n")
}
