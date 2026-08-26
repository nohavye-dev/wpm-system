import { describe, expect, test } from "bun:test"
import { buildNudge } from "./nudges"

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
})
