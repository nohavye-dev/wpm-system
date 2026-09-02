import { describe, expect, test } from "bun:test"
import { InjectionBlock, PromptContext, PromptTask } from "./entities"

describe("before option on add* methods", () => {
  test("PromptTask.addInstruction({before:true}) prepends", () => {
    const task = new PromptTask("t")
      .addInstruction("second")
      .addInstruction({ before: true }, "first")
    expect(task.instructions).toEqual(["first", "second"])
    // plain string still appends
    const appended = task.clone().addInstruction("third")
    expect(appended.instructions).toEqual(["first", "second", "third"])
  })

  test("null first argument never throws", () => {
    const task = new PromptTask("t")
    expect(() => task.addInstruction(null as never)).not.toThrow()
    const block = new InjectionBlock("t")
    expect(() => block.addItem(null as never)).not.toThrow()
  })

  test("PromptContext addPurpose/addExpectedBehavior honor before", () => {
    const ctx = new PromptContext()
      .addPurpose("p2")
      .addPurpose({ before: true }, "p1")
      .addExpectedBehavior("e1")
      .addExpectedBehavior({ before: true }, "e0")
    expect(ctx.purpose).toEqual(["p1", "p2"])
    expect(ctx.expectedBehavior).toEqual(["e0", "e1"])
  })

  test("InjectionBlock addItem/addNote honor before and clone deep-copies", () => {
    const block = new InjectionBlock("tag")
      .addItem("i2")
      .addItem({ before: true }, "i1")
      .addNote("n1")
    expect(block.items).toEqual(["i1", "i2"])

    const copy = block.clone()
    copy.addItem("i3")
    copy.addNote({ before: true }, "n0")
    expect(block.items).toEqual(["i1", "i2"])
    expect(block.notes).toEqual(["n1"])
    expect(copy.items).toEqual(["i1", "i2", "i3"])
    expect(copy.notes).toEqual(["n0", "n1"])
  })
})
