import { describe, expect, test } from "bun:test"
import { InjectionBlock } from "./entities"

describe("InjectionBlock", () => {
  test("tag-less block renders the server body verbatim (project rules)", () => {
    const body =
      "<project-rules>\n## Rules\n\n  - [convention] x (confidence 0.9)\n</project-rules>"
    const block = new InjectionBlock().setBody(body)
    expect(block.isEmpty()).toBe(false)
    expect(block.toString()).toBe(body)
  })

  test("empty body yields an empty raw block (no push)", () => {
    expect(new InjectionBlock().setBody("").isEmpty()).toBe(true)
    expect(new InjectionBlock().toString()).toBe("")
  })

  test("tagged block renders purpose, items and conflict notes (RAG pop-in)", () => {
    const block = new InjectionBlock("wpm-memory-recall")
      .addPurpose("Automatically recalled durable memories relevant to this request.")
      .addItem("[insight] bun runs TS (similarity 0.82, confidence 0.90)")
      .addNote("entry abc is actively contradicted by entry def")
    const rendered = block.toString()
    expect(rendered).toContain("<wpm-memory-recall>")
    expect(rendered).toContain("## Purpose")
    expect(rendered).toContain(
      "- Automatically recalled durable memories relevant to this request.",
    )
    expect(rendered).toContain("- [insight] bun runs TS (similarity 0.82, confidence 0.90)")
    expect(rendered).toContain("## Notes")
    expect(rendered.endsWith("</wpm-memory-recall>")).toBe(true)
  })
})
