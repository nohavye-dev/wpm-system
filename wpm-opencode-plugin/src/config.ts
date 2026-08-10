import { readFileSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"
import type { MemoryServerConfig } from "./mcp-client.js"

const DEFAULT_CONFIDENCE_THRESHOLD = 0.5

const dataHome = process.env.XDG_DATA_HOME ?? join(homedir(), ".local", "share")

const VENV_PYTHON = join(dataHome, "wpm-system", "venv", "bin", "python")

export function loadMemoryServerConfig(directory: string): MemoryServerConfig {
  const command = process.env.WPM_MCP_COMMAND ?? VENV_PYTHON
  const args = ["-m", "wpm_mcp_server"]
  const cwd = directory

  return { command, args, cwd }
}

export function getConfidenceThreshold(directory: string): number {
  const envRaw = process.env.WPM_CONFIDENCE_THRESHOLD
  if (envRaw) {
    const parsed = Number.parseFloat(envRaw)
    if (Number.isFinite(parsed)) return parsed
  }

  try {
    const config = JSON.parse(
      readFileSync(join(directory, "wpm.config.json"), "utf-8"),
    ) as { confidence_threshold?: unknown }
    if (
      typeof config.confidence_threshold === "number" &&
      Number.isFinite(config.confidence_threshold)
    ) {
      return config.confidence_threshold
    }
  } catch {
    // The Python server validates the file strictly at startup; the plugin
    // must never crash on a bad file — fall back to the default.
  }

  return DEFAULT_CONFIDENCE_THRESHOLD
}
