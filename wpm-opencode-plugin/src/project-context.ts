/**
 * Pure, testable helpers shared by the plugin's deterministic hooks:
 * - project rules injected into the system prompt (system.transform)
 * - contextual compaction query derived from the session's recent user
 *   messages (session.compacting)
 *
 * Queries are kept in English on purpose: stored content must be English
 * (embedding consistency).
 */

export const DEFAULT_COMPACTION_QUERY = "current task relevant decisions and conventions"

export const PROJECT_RULES_QUERY =
  "What are the project rules and conventions: commit message format, dependency and package management, coding style, testing strategy, architecture decisions and documentation standards?"

/** Injected rules block is capped to keep the system prompt from bloating. */
export const MAX_RULES_CHARS = 6000

/** Compaction query is capped so the embedding stays focused on the topic. */
export const COMPACTION_QUERY_MAX_CHARS = 300

/** Number of recent user messages tried before falling back to generic. */
export const COMPACTION_WIDE_WINDOW = 5

/**
 * A text carries topical signal if it contains enough non-whitespace
 * characters — language-agnostic proxy that filters out one-liners like
 * "ok", "continue" or "yes" without a stopword list.
 */
export const MIN_SIGNAL_CHARS = 20

export function buildProjectRulesBlock(text: string | null): string {
  if (!text || text.trim().length === 0) return ""
  return `<project-rules>\n${text}\n</project-rules>`
}

/**
 * Extract the text parts of the last `lastN` user-role messages, in
 * chronological order (oldest first within the window).
 */
export function extractUserTexts(
  messages: { info: { role?: string }; parts: { type: string; text?: string }[] }[] | undefined,
  lastN: number,
): string[] {
  if (!Array.isArray(messages)) return []
  const texts = messages
    .filter((m) => m.info?.role === "user")
    .flatMap((m) =>
      m.parts
        .filter((p) => p.type === "text" && typeof p.text === "string" && p.text.length > 0)
        .map((p) => p.text as string),
    )
  return texts.slice(-lastN)
}

export function hasTopicSignal(text: string | null): boolean {
  if (!text) return false
  return text.replace(/\s+/g, "").length >= MIN_SIGNAL_CHARS
}

/**
 * Choose the compaction query from the session's recent user text.
 * Narrow (last 2 messages) wins if it carries a topic signal; otherwise
 * widen to `wide` (last 5); otherwise fall back to the generic query.
 */
export function deriveCompactionQuery(narrow: string[], wide: string[], maxChars: number): string {
  const candidates = [narrow.join(" "), wide.join(" ")]
  const chosen = candidates.find(hasTopicSignal)
  if (chosen === undefined) return DEFAULT_COMPACTION_QUERY
  return truncate(chosen, maxChars)
}

function truncate(text: string, maxChars: number): string {
  if (text.length <= maxChars) return text
  return text.slice(0, maxChars)
}
