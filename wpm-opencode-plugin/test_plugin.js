import { test } from "node:test"
import assert from "node:assert/strict"
import { mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { tmpdir } from "node:os"

import { IDLE_NUDGE_TEXT, MEMORY_USAGE_RULES } from "./dist/rules.js"
import { getIdleNudgeEnabled, getVerificationCommandPatterns } from "./dist/config.js"

function withTempDir(fn) {
  const dir = mkdtempSync(join(tmpdir(), "wpm-plugin-test-"))
  try {
    fn(dir)
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

function writeConfig(dir, config) {
  writeFileSync(join(dir, "wpm.config.json"), JSON.stringify(config))
}

function withEnv(value, fn) {
  const previous = process.env.WPM_IDLE_NUDGE
  process.env.WPM_IDLE_NUDGE = value
  try {
    fn()
  } finally {
    if (previous === undefined) delete process.env.WPM_IDLE_NUDGE
    else process.env.WPM_IDLE_NUDGE = previous
  }
}

test("MEMORY_USAGE_RULES: non-empty rules block", () => {
  assert.equal(typeof MEMORY_USAGE_RULES, "string")
  assert.ok(MEMORY_USAGE_RULES.trim().length > 0)
  assert.match(MEMORY_USAGE_RULES, /<wpm-memory-rules>/)
  assert.match(MEMORY_USAGE_RULES, /<\/wpm-memory-rules>/)
  for (const expected of [
    "store_entry",
    "validate_entry",
    "contradict_entry",
    "query_context",
    "link_entries",
    "/wpm-doc",
    "/wpm-code",
  ]) {
    assert.ok(MEMORY_USAGE_RULES.includes(expected), `missing: ${expected}`)
  }
})

test("IDLE_NUDGE_TEXT: non-empty string", () => {
  assert.equal(typeof IDLE_NUDGE_TEXT, "string")
  assert.ok(IDLE_NUDGE_TEXT.trim().length > 0)
})

test("getIdleNudgeEnabled: default false without file or env", () => {
  withTempDir((dir) => {
    withEnv(undefined, () => {
      assert.equal(getIdleNudgeEnabled(dir), false)
    })
  })
})

test("getIdleNudgeEnabled: reads true from wpm.config.json", () => {
  withTempDir((dir) => {
    writeConfig(dir, { idle_nudge: true })
    withEnv(undefined, () => {
      assert.equal(getIdleNudgeEnabled(dir), true)
    })
  })
})

test("getIdleNudgeEnabled: reads false from wpm.config.json", () => {
  withTempDir((dir) => {
    writeConfig(dir, { idle_nudge: false })
    withEnv(undefined, () => {
      assert.equal(getIdleNudgeEnabled(dir), false)
    })
  })
})

test("getIdleNudgeEnabled: env true wins over file false", () => {
  withTempDir((dir) => {
    writeConfig(dir, { idle_nudge: false })
    withEnv("true", () => {
      assert.equal(getIdleNudgeEnabled(dir), true)
    })
  })
})

test("getIdleNudgeEnabled: env false wins over file true", () => {
  withTempDir((dir) => {
    writeConfig(dir, { idle_nudge: true })
    withEnv("false", () => {
      assert.equal(getIdleNudgeEnabled(dir), false)
    })
  })
})

test("getIdleNudgeEnabled: env '1' and 'yes' parse as true", () => {
  withTempDir((dir) => {
    for (const value of ["1", "yes", "YES"]) {
      withEnv(value, () => {
        assert.equal(getIdleNudgeEnabled(dir), true)
      })
    }
  })
})

test("getIdleNudgeEnabled: env '0' and 'no' parse as false", () => {
  withTempDir((dir) => {
    writeConfig(dir, { idle_nudge: true })
    for (const value of ["0", "no", "NO"]) {
      withEnv(value, () => {
        assert.equal(getIdleNudgeEnabled(dir), false)
      })
    }
  })
})

test("getIdleNudgeEnabled: invalid env falls back to file", () => {
  withTempDir((dir) => {
    writeConfig(dir, { idle_nudge: true })
    withEnv("banana", () => {
      assert.equal(getIdleNudgeEnabled(dir), true)
    })
  })
})

test("getIdleNudgeEnabled: missing file falls back to default false", () => {
  withTempDir((dir) => {
    withEnv("false", () => {
      assert.equal(getIdleNudgeEnabled(dir), false)
    })
  })
})

test("getIdleNudgeEnabled: invalid config file never throws", () => {
  withTempDir((dir) => {
    writeConfig(dir, "not json")
    withEnv(undefined, () => {
      assert.equal(getIdleNudgeEnabled(dir), false)
    })
  })
})

test("getIdleNudgeEnabled: non-boolean file value falls back to default", () => {
  withTempDir((dir) => {
    writeConfig(dir, { idle_nudge: "yes" })
    withEnv(undefined, () => {
      assert.equal(getIdleNudgeEnabled(dir), false)
    })
  })
})

test("getVerificationCommandPatterns: empty without file", () => {
  withTempDir((dir) => {
    assert.deepEqual(getVerificationCommandPatterns(dir), [])
  })
})

test("getVerificationCommandPatterns: reads additions from wpm.config.json", () => {
  withTempDir((dir) => {
    writeConfig(dir, { verification_command_patterns: ["\\bmy-runner\\b", "\\bpytest\\b"] })
    assert.deepEqual(getVerificationCommandPatterns(dir), [
      "\\bmy-runner\\b",
      "\\bpytest\\b",
    ])
  })
})

test("getVerificationCommandPatterns: empty list adds nothing", () => {
  withTempDir((dir) => {
    writeConfig(dir, { verification_command_patterns: [] })
    assert.deepEqual(getVerificationCommandPatterns(dir), [])
  })
})

test("getVerificationCommandPatterns: invalid config never throws", () => {
  withTempDir((dir) => {
    writeConfig(dir, "not json")
    assert.deepEqual(getVerificationCommandPatterns(dir), [])
  })
})

test("getVerificationCommandPatterns: non-list file value falls back to empty", () => {
  withTempDir((dir) => {
    writeConfig(dir, { verification_command_patterns: "\\bpytest\\b" })
    assert.deepEqual(getVerificationCommandPatterns(dir), [])
  })
})

test("getVerificationCommandPatterns: invalid elements fall back to empty", () => {
  withTempDir((dir) => {
    writeConfig(dir, { verification_command_patterns: ["\\bpytest\\b", 3, ""] })
    assert.deepEqual(getVerificationCommandPatterns(dir), [])
  })
})
