"""Memory server (FastMCP): tools, resources, instructions.

One of two complementary layers. OpenCode is the single target host, so
wpm splits its behavior between:

- this MCP layer (declarative, read by the model): a reduced set of usage
  rules in initialize.instructions (3 golden rules + a handful of standing
  policies, re-readable via the wpm://memory-rules resource), tool
  descriptions, JSON schemas, and targeted `tool_result` reminders;
- the wpm-opencode-plugin layer (event-driven, triggered by the host):
  `experimental.chat.system.transform`, `experimental.session.compacting`,
  `tool.execute.before/after`, and `event` (`session.idle`).

Project rules/conventions are exposed as the wpm://project-rules resource,
recomputed from memory and invalidated (with a resources/updated
notification) on every mutation. record_execution remains a tool, but rule
16 is primarily enforced deterministically by the plugin's
tool.execute.after hook (which shells out to `wpm record-execution`), so it
no longer depends on the model remembering to call this tool.

Host-agnostic activation: the server is active when it can resolve a database
path — from wpm.config.json (relative to its own location, not the host's
cwd) or WPM_DB_PATH. Without one it stays inert: it starts and lists its
tools, but every tool returns a clear "not activated" error.

Package layout:
- state.py: import-time bootstrap (config resolution, DB_PATH) and
  process-wide runtime state; also builds the FastMCP instance.
- prompts.py: every agent-facing text (tool/resource descriptions,
  reminders).
- tools.py / resources.py: the handlers, registered on import.
"""

from wpm_mcp_server.server.state import (  # noqa: F401
    CONFIG_DIR,
    DB_PATH,
    SERVER_INSTRUCTIONS,
    SESSION_ID,
    SETTINGS,
    VERIFICATION_PATTERNS,
    mcp,
)
from wpm_mcp_server.server import tools  # noqa: F401  (registers the tools)
from wpm_mcp_server.server import resources  # noqa: F401  (registers the resources)


def main() -> None:
    mcp.run(transport="stdio")
