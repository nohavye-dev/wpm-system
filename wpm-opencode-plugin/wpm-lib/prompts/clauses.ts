// Response-language clauses mirrored from the MCP server (behavior.py
// _response_clause).

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
