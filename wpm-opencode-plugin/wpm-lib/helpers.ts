import { existsSync, readFileSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"

export function isEnabled(directory: string): boolean {
  return existsSync(join(directory, "wpm.config.json"))
}

// Resolve the wpm server venv Python the same way install.sh lays it out
// (DATA_DIR = $XDG_DATA_HOME/wpm-system, default ~/.local/share/wpm-system).
export function resolvePythonPath(): string {
  const dataHome = process.env.XDG_DATA_HOME ?? join(homedir(), ".local", "share")
  return join(dataHome, "wpm-system", "venv", "bin", "python")
}

// Reads a primitive parameter from the project's top-level `wpm.config.json`.
export function readConfigParam(
  directory: string,
  param: string,
): string | number | boolean | undefined {
  try {
    const config = JSON.parse(
      readFileSync(join(directory, "wpm.config.json"), "utf8"),
    )
    return config[param] ?? undefined
  } catch {
    return undefined
  }
}
