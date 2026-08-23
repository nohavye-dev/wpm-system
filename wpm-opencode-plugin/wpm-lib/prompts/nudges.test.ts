import { describe, expect, test } from "bun:test"
import { buildNudge } from "./nudges"

const PULL_LINE = "At session start, read the `wpm://project-rules` resource."

describe("buildNudge per-mode fidelity", () => {
    test("legacy (default) keeps the pull instruction — historical bytes", () => {
        const nudge = buildNudge()
        expect(nudge).toContain(PULL_LINE)
    })

    test("pluginMaster omits exactly the pull line, nothing else changes", () => {
        const legacy = buildNudge("french")
        const master = buildNudge("french", true)

        expect(master).not.toContain(PULL_LINE)
        // Every legacy line except the pull line survives verbatim.
        const legacyLines = legacy.split("\n").filter((line) => line !== `  - ${PULL_LINE}`)
        expect(master.split("\n")).toEqual(legacyLines)
    })

    test("language clause survives in both modes", () => {
        for (const nudge of [buildNudge("french"), buildNudge("french", true)]) {
            expect(nudge).toContain("written in french")
        }
    })
})
