// Minimal JSON-RPC 2.0 / MCP protocol types. Only what our hand-rolled
// client needs (see docs/internals/architecture-plugin-hote-mcp.md):
// initialize handshake, tools/list, tools/call, resources/read and the
// resources/updated notification.

export interface JsonRpcError {
  code: number
  message: string
  data?: unknown
}

export interface JsonRpcRequest {
  jsonrpc: "2.0"
  id: number
  method: string
  params?: Record<string, unknown>
}

export interface JsonRpcNotification {
  jsonrpc: "2.0"
  method: string
  params?: Record<string, unknown>
}

export interface JsonRpcResponse {
  jsonrpc: "2.0"
  id: number | string | null
  result?: unknown
  error?: JsonRpcError
}

export type JsonRpcMessage = JsonRpcRequest | JsonRpcNotification | JsonRpcResponse

export function isResponse(message: JsonRpcMessage): message is JsonRpcResponse {
  return (
    !("method" in message) &&
    "id" in message &&
    message.id !== undefined &&
    message.id !== null &&
    ("result" in message || "error" in message)
  )
}

export interface McpJsonSchemaProperty {
  type?: string
  enum?: string[]
  anyOf?: Array<{ type?: string }>
  [key: string]: unknown
}

export interface McpJsonSchema {
  type?: string
  properties?: Record<string, McpJsonSchemaProperty>
  required?: string[]
  [key: string]: unknown
}

export interface McpToolDefinition {
  name: string
  description?: string
  inputSchema: McpJsonSchema
}

export interface McpResourceContent {
  uri: string
  mimeType?: string
  text?: string
}

export interface McpContentBlock {
  type: string
  text?: string
}

export interface McpCallToolResult {
  content?: McpContentBlock[]
  structuredContent?: unknown
  isError?: boolean
}

export interface McpReadResourceResult {
  contents?: McpResourceContent[]
}
