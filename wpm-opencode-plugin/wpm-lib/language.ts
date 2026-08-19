import { readFileSync } from "node:fs"
import { join } from "node:path"

// Mirrors the MCP server's response-language system (settings.py
// resolve_response_language + behavior.py _response_clause /
// build_language_note). Only the agent's conversational output language is
// governed — stored memory content and the instructions stay English on
// purpose (embedding consistency).

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

export function expectedResponseLanguage(language: string | undefined): string {
  if (language) {
    return (
      "your conversational responses, summaries, and reports MUST be " +
      `written in ${language}, regardless of the language used in memory ` +
      "or in these instructions"
    )
  }
  return (
    "your conversational responses, summaries, and reports MUST use the " +
    "same language as the user asking questions — do not switch to English " +
    "for output"
  )
}

export function languageNote(language: string | undefined): string {
  const target = language ? language : "the user's language"
  return (
    `All user-facing output MUST be written in ${target}. ` +
    `This includes explanations, summaries, reports, titles, headings, ` +
    `labels, and other presentation text. ` +
    `Data being stored or processed must retain its required format or ` +
    `language and must not be translated unless explicitly instructed.`
  )
}
