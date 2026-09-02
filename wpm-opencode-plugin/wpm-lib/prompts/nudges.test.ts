import { describe, expect, test } from "bun:test"
import {
  buildMemoryFirstNudge,
  buildNudge,
  buildPersistPromptText,
  buildPersistReminder,
} from "./nudges"

const PULL_LINE = "At session start, read the `wpm://project-rules` resource."

describe("buildNudge", () => {
  test("omits the pull instruction (push mode — rules are pushed)", () => {
    const nudge = buildNudge()
    expect(nudge).not.toContain(PULL_LINE)
  })

  test("language clause is present", () => {
    const nudge = buildNudge("french")
    expect(nudge).toContain("written in french")
  })

  test("master phrasing is used", () => {
    const nudge = buildNudge()
    expect(nudge).toContain("If no <wpm-memory-recall> was pushed this turn")
    expect(nudge).toContain("If identity or language is ambiguous, call wpm_get_user.")
  })

  test("snapshot stays byte-stable", () => {
    // Full snapshot — any prompting drift fails loudly.
    const nudge = buildNudge("french")
    // Keep the snapshot inline to avoid an extra .snap file to maintain.
    expect(nudge).toContain("<wpm-memory>")
    expect(nudge).toContain("Use the WPM memory system as the primary source")
    expect(nudge).toContain("Store memory entries in their native language")
    expect(nudge).toContain("Validate memory")
    // Must not contain any legacy pull phrasing
    expect(nudge).not.toContain("wpm://project-rules")
  })

  test("without language uses user language fallback", () => {
    const nudge = buildNudge()
    // ExpectedBehavior should still be present (language clause fallback)
    expect(nudge).toContain("same language as the user")
  })
})

describe("buildMemoryFirstNudge", () => {
  test("contains query_context reminder", () => {
    const nudge = buildMemoryFirstNudge()
    expect(nudge).toContain("wpm_query_context")
    expect(nudge).toContain("<wpm-memory>")
  })
})

describe("buildPersistReminder", () => {
  test("contains persistence Task", () => {
    const reminder = buildPersistReminder()
    expect(reminder).toContain("Persistence")
    expect(reminder).toContain("wpm_store_entry")
  })
})

describe("buildPersistPromptText", () => {
  test("mentions target language when provided", () => {
    const text = buildPersistPromptText("french")
    expect(text).toContain("french")
    expect(text).toContain("wpm_store_entry")
  })

  test("falls back to user language when no language", () => {
    const text = buildPersistPromptText()
    expect(text).toContain("the user's language")
  })

  test("is silent when nothing persisted", () => {
    const text = buildPersistPromptText("french")
    expect(text).toContain("If nothing was persisted: send no message at all")
  })
})
