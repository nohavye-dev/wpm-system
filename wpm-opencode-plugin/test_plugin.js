import { test } from "node:test"
import assert from "node:assert/strict"
import { mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { tmpdir } from "node:os"

import { IDLE_NUDGE_TEXT, MEMORY_USAGE_RULES } from "./dist/rules.js"
import {
  getIdleNudgeEnabled,
  getVerificationCommandPatterns,
  getConfidenceThreshold,
  loadMemoryServerConfig,
} from "./dist/config.js"
import {
  DEFAULT_COMPACTION_QUERY,
  buildProjectRulesBlock,
  deriveCompactionQuery,
  extractUserTexts,
  hasTopicSignal,
} from "./dist/project-context.js"
import {
  VERIFICATION_COMMAND_PATTERNS,
  WORK_TOOLS,
  MEMORY_MUTATION_TOOLS,
  looksLikeVerificationCommand,
} from "./dist/index.js"

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

function userMessage(text) {
  return { info: { role: "user" }, parts: [{ type: "text", text }] }
}

test("buildProjectRulesBlock: wraps text, empty for null/blank", () => {
  assert.equal(
    buildProjectRulesBlock("keep secrets out"),
    "<project-rules>\nkeep secrets out\n</project-rules>",
  )
  assert.equal(buildProjectRulesBlock(null), "")
  assert.equal(buildProjectRulesBlock("   "), "")
})

test("hasTopicSignal: rejects one-liners, accepts real text", () => {
  assert.equal(hasTopicSignal("ok"), false)
  assert.equal(hasTopicSignal("continue"), false)
  assert.equal(hasTopicSignal("continue with the implementation of the parser module now please"), true)
  assert.equal(hasTopicSignal(null), false)
  assert.equal(hasTopicSignal(""), false)
})

test("extractUserTexts: last N user text parts, ignores others", () => {
  const messages = [
    userMessage("old topic"),
    { info: { role: "assistant" }, parts: [{ type: "text", text: "done" }] },
    userMessage("current topic"),
    userMessage("follow-up"),
    { info: { role: "user" }, parts: [{ type: "tool", text: "ignored" }] },
  ]
  assert.deepEqual(extractUserTexts(messages, 2), ["current topic", "follow-up"])
  assert.deepEqual(extractUserTexts(messages, 5), ["old topic", "current topic", "follow-up"])
  assert.deepEqual(extractUserTexts(undefined, 2), [])
})

test("deriveCompactionQuery: narrow wins when it carries a signal", () => {
  const narrow = ["refactor the storage layer to use the new API"]
  const wide = ["old topic", "stale topic from earlier"]
  assert.equal(deriveCompactionQuery(narrow, wide, 300), narrow[0])
})

test("deriveCompactionQuery: widens to wide when narrow has no signal", () => {
  const narrow = ["continue"]
  const wide = ["ok", "implement the caching layer for the parser"]
  assert.equal(
    deriveCompactionQuery(narrow, wide, 300),
    "ok implement the caching layer for the parser",
  )
})

test("deriveCompactionQuery: falls back to generic when nothing has signal", () => {
  assert.equal(deriveCompactionQuery(["ok", "continue"], [], 300), DEFAULT_COMPACTION_QUERY)
  assert.equal(deriveCompactionQuery([], [], 300), DEFAULT_COMPACTION_QUERY)
})

test("deriveCompactionQuery: truncates to maxChars", () => {
  const long = "a".repeat(500)
  const got = deriveCompactionQuery([long], [long], 300)
  assert.equal(got.length, 300)
})

// --- config.ts: getConfidenceThreshold ---

test("getConfidenceThreshold: default without file or env", () => {
  withTempDir((dir) => {
    assert.equal(getConfidenceThreshold(dir), 0.5)
  })
})

test("getConfidenceThreshold: reads from wpm.config.json", () => {
  withTempDir((dir) => {
    writeConfig(dir, { confidence_threshold: 0.7 })
    assert.equal(getConfidenceThreshold(dir), 0.7)
  })
})

test("getConfidenceThreshold: env wins over file", () => {
  withTempDir((dir) => {
    writeConfig(dir, { confidence_threshold: 0.3 })
    const prev = process.env.WPM_CONFIDENCE_THRESHOLD
    process.env.WPM_CONFIDENCE_THRESHOLD = "0.85"
    try {
      assert.equal(getConfidenceThreshold(dir), 0.85)
    } finally {
      if (prev === undefined) delete process.env.WPM_CONFIDENCE_THRESHOLD
      else process.env.WPM_CONFIDENCE_THRESHOLD = prev
    }
  })
})

test("getConfidenceThreshold: invalid env falls back to file", () => {
  withTempDir((dir) => {
    writeConfig(dir, { confidence_threshold: 0.6 })
    const prev = process.env.WPM_CONFIDENCE_THRESHOLD
    process.env.WPM_CONFIDENCE_THRESHOLD = "banana"
    try {
      assert.equal(getConfidenceThreshold(dir), 0.6)
    } finally {
      if (prev === undefined) delete process.env.WPM_CONFIDENCE_THRESHOLD
      else process.env.WPM_CONFIDENCE_THRESHOLD = prev
    }
  })
})

test("getConfidenceThreshold: invalid config file never throws", () => {
  withTempDir((dir) => {
    writeConfig(dir, "not json")
    assert.equal(getConfidenceThreshold(dir), 0.5)
  })
})

test("getConfidenceThreshold: non-number file value falls back to default", () => {
  withTempDir((dir) => {
    writeConfig(dir, { confidence_threshold: "high" })
    assert.equal(getConfidenceThreshold(dir), 0.5)
  })
})

// --- config.ts: loadMemoryServerConfig ---

test("loadMemoryServerConfig: default python path and args", () => {
  withTempDir((dir) => {
    const cfg = loadMemoryServerConfig(dir)
    assert.ok(cfg.command.includes("python"), `got ${cfg.command}`)
    assert.deepEqual(cfg.args, ["-m", "wpm_mcp_server"])
    assert.equal(cfg.cwd, dir)
  })
})

test("loadMemoryServerConfig: env overrides command", () => {
  withTempDir((dir) => {
    const prev = process.env.WPM_MCP_COMMAND
    process.env.WPM_MCP_COMMAND = "/usr/local/bin/python3"
    try {
      const cfg = loadMemoryServerConfig(dir)
      assert.equal(cfg.command, "/usr/local/bin/python3")
      assert.deepEqual(cfg.args, ["-m", "wpm_mcp_server"])
    } finally {
      if (prev === undefined) delete process.env.WPM_MCP_COMMAND
      else process.env.WPM_MCP_COMMAND = prev
    }
  })
})

// --- looksLikeVerificationCommand ---

test("looksLikeVerificationCommand: matches pytest", () => {
  assert.equal(looksLikeVerificationCommand("pytest tests/", [/pytest/]), true)
  assert.equal(looksLikeVerificationCommand("npm test -- --coverage", [/pnpm test/]), false)
})

test("looksLikeVerificationCommand: matches null patterns gracefully", () => {
  assert.equal(looksLikeVerificationCommand("pytest", [/pytest/, null]), true)
  assert.equal(looksLikeVerificationCommand("ls", [/pytest/, null]), false)
})

test("looksLikeVerificationCommand: undefined command returns false", () => {
  assert.equal(looksLikeVerificationCommand(undefined, [/pytest/]), false)
})

test("looksLikeVerificationCommand: matches all built-in patterns against real commands", () => {
  const testCases = [
    { cmd: "pytest -v tests/test_foo.py", patternSbustr: "pytest" },
    { cmd: "npm test", patternSbustr: "npm test" },
    { cmd: "npm run build", patternSbustr: "npm run build" },
    { cmd: "pnpm test --filter=foo", patternSbustr: "pnpm test" },
    { cmd: "pnpm run build", patternSbustr: "pnpm run build" },
    { cmd: "yarn test", patternSbustr: "yarn test" },
    { cmd: "yarn build", patternSbustr: "yarn build" },
    { cmd: "bun test", patternSbustr: "bun test" },
    { cmd: "bun run build", patternSbustr: "bun run build" },
    { cmd: "dotnet test", patternSbustr: "dotnet test" },
    { cmd: "dotnet build --configuration Release", patternSbustr: "dotnet build" },
    { cmd: "cargo test", patternSbustr: "cargo test" },
    { cmd: "cargo build --release", patternSbustr: "cargo build" },
    { cmd: "go test ./...", patternSbustr: "go test" },
    { cmd: "go build -o bin/app", patternSbustr: "go build" },
    { cmd: "make test", patternSbustr: "make test" },
    { cmd: "vitest --run", patternSbustr: "vitest" },
    { cmd: "jest --coverage", patternSbustr: "jest" },
    { cmd: "tsc --noEmit", patternSbustr: "tsc --noEmit" },
    { cmd: "ruff check .", patternSbustr: "ruff check" },
    { cmd: "mypy src/", patternSbustr: "mypy" },
    { cmd: "eslint --fix .", patternSbustr: "eslint" },
    { cmd: "shellcheck script.sh", patternSbustr: "shellcheck" },
    { cmd: "tox -e py311", patternSbustr: "tox" },
    { cmd: "deno test -A", patternSbustr: "deno test" },
    { cmd: "mix test", patternSbustr: "mix test" },
  ]
  for (const { cmd } of testCases) {
    assert.ok(
      looksLikeVerificationCommand(cmd, VERIFICATION_COMMAND_PATTERNS),
      `should match: ${cmd}`,
    )
  }
})

test("looksLikeVerificationCommand: non-verification commands rejected", () => {
  const nonVerification = [
    "ls -la",
    "cat README.md",
    "echo hello",
    "grep -r foo src/",
    "git status",
    "mkdir foo",
    "rm -rf /tmp/foo",
    "node script.js",
    "pip install foo",
    "curl https://example.com",
  ]
  for (const cmd of nonVerification) {
    assert.equal(
      looksLikeVerificationCommand(cmd, VERIFICATION_COMMAND_PATTERNS),
      false,
      `should not match: ${cmd}`,
    )
  }
})

// --- VERIFICATION_COMMAND_PATTERNS ---

test("VERIFICATION_COMMAND_PATTERNS: non-empty and all valid RegExp", () => {
  assert.ok(VERIFICATION_COMMAND_PATTERNS.length > 0)
  for (const re of VERIFICATION_COMMAND_PATTERNS) {
    assert.ok(re instanceof RegExp, `not a RegExp: ${re}`)
  }
})

// --- WORK_TOOLS ---

test("WORK_TOOLS: contains mutation tools", () => {
  assert.ok(WORK_TOOLS.has("edit"))
  assert.ok(WORK_TOOLS.has("write"))
  assert.ok(WORK_TOOLS.has("apply_patch"))
  assert.ok(WORK_TOOLS.has("bash"))
  assert.ok(WORK_TOOLS.has("task"))
})

// --- MEMORY_MUTATION_TOOLS ---

test("MEMORY_MUTATION_TOOLS: contains all 5 memory tools", () => {
  assert.ok(MEMORY_MUTATION_TOOLS.has("store_entry"))
  assert.ok(MEMORY_MUTATION_TOOLS.has("validate_entry"))
  assert.ok(MEMORY_MUTATION_TOOLS.has("contradict_entry"))
  assert.ok(MEMORY_MUTATION_TOOLS.has("link_entries"))
  assert.equal(MEMORY_MUTATION_TOOLS.size, 4)
})
