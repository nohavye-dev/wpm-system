import { homedir } from "node:os"
import { join } from "node:path"

// Resolve the wpm server venv Python the same way install.sh lays it out
// (DATA_DIR = $XDG_DATA_HOME/wpm-system, default ~/.local/share/wpm-system).
export function resolvePythonPath(): string {
  const dataHome = process.env.XDG_DATA_HOME ?? join(homedir(), ".local", "share")
  return join(dataHome, "wpm-system", "venv", "bin", "python")
}
