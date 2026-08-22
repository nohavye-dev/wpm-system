// Prefix under which the plugin re-exposes the MCP server's tools
// (wpm_store_entry, ...). The names are the identity the permission rules,
// the plan-mode exception and the query_context detection rely on — they
// must stay stable across the dynamic tool bridge.
export const SERVER_NAME = "wpm"
