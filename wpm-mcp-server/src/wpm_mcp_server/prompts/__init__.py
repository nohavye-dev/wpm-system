"""Agent-facing prompt content and behavioral policy.

Holds the usage rules injected through initialize.instructions (a reduced
set — 3 golden rules + standing policies — with the full rule detail living
in tool descriptions), the verification-command patterns powering
record_execution, and the project-rules formatting used by the
wpm://project-rules resource.

Kept in English on purpose: these are agent instructions. Stored memory
content is written in its native language (the embedding model is
multilingual), so this package must stay free of import side effects so it
can be unit-tested without booting the MCP server.
"""

from wpm_mcp_server.prompts.entities import PromptContext, PromptTask
from wpm_mcp_server.prompts.memory_rules import (
    MEMORY_USAGE_RULES,
    build_memory_usage_rules,
)
from wpm_mcp_server.prompts.project_rules import (
    MAX_PROJECT_RULES_CHARS,
    PROJECT_RULES_QUERY,
    PROJECT_RULES_TOKEN_BUDGET,
    build_project_rules_block,
    format_project_rules,
)
from wpm_mcp_server.prompts.verification import (
    VERIFICATION_COMMAND_PATTERNS,
    compile_verification_patterns,
    looks_like_verification_command,
)

__all__ = [
    "MEMORY_USAGE_RULES",
    "MAX_PROJECT_RULES_CHARS",
    "PROJECT_RULES_QUERY",
    "PROJECT_RULES_TOKEN_BUDGET",
    "VERIFICATION_COMMAND_PATTERNS",
    "PromptContext",
    "PromptTask",
    "build_memory_usage_rules",
    "build_project_rules_block",
    "compile_verification_patterns",
    "format_project_rules",
    "looks_like_verification_command",
]
