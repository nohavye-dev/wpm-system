import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"

export function isEnabled(directory: string): boolean {
  return existsSync(join(directory, "wpm.config.json"))
}

// Reads a primitive parameter from the project's top-level `wpm.config.json`.
export function readConfigParam(
  directory: string,
  param: string,
): string | number | boolean | undefined {
  try {
    const config = JSON.parse(
      readFileSync(join(directory, "wpm.config.json"), "utf8"),
    )
    return config[param] ?? undefined
  } catch {
    return undefined
  }
}

// Mirrors the MCP server's response-language system (settings.py
// resolve_response_language). Only the agent's conversational output
// language is governed — stored memory content stays in its native
// language (the embedding model is multilingual).
export function resolveResponseLanguage(
  configValue: string | undefined,
  envValue: string | undefined,
): string | undefined {
  const value = envValue && envValue.trim() ? envValue : configValue
  if (value == null) return undefined
  const stripped = value.trim()
  if (!stripped || stripped.toLowerCase() === "auto") return undefined
  return stripped
}
