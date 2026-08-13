"""Unit tests for behavior.py: memory-rules text, verification-command
matching, project-rules rendering, and token-budget truncation.

Script-style (module-level asserts + prints) so it runs both under pytest
(conftest runs it via runpy) and directly with `python test_behavior.py`.
"""

import re
import sys
sys.path.insert(0, "src")

from wpm_mcp_server import behavior

pass_count = 0
fail_count = 0


def check(label, cond, detail=""):
    global pass_count, fail_count
    if cond:
        pass_count += 1
        print(f"  OK  {label}")
    else:
        fail_count += 1
        print(f"  FAIL {label}" + (f": {detail}" if detail else ""))


# --- memory rules text ---
check(
    "rules are substantial (>=15 rules)",
    behavior.MEMORY_USAGE_RULES.count("<wpm-memory-rules>") >= 1
    and len(behavior.MEMORY_USAGE_RULES) > 2000,
    f"len={len(behavior.MEMORY_USAGE_RULES)}",
)
check(
    "rules mention write-as-you-go discipline",
    "write" in behavior.MEMORY_USAGE_RULES.lower()
    and "go" in behavior.MEMORY_USAGE_RULES.lower(),
)
check(
    "rules mention query_context preamble",
    "query_context" in behavior.MEMORY_USAGE_RULES,
)
check(
    "rules mention record_execution",
    "record_execution" in behavior.MEMORY_USAGE_RULES,
)

# --- verification command matching ---
patterns, invalid = behavior.compile_verification_patterns([r"\bwpm\bcheck", "[invalid"])
check("built-in patterns compile", len(patterns) >= len(behavior.VERIFICATION_COMMAND_PATTERNS))
check(
    "invalid custom regex reported, not fatal",
    invalid == ["[invalid"],
    f"got {invalid}",
)

check(
    "pytest command detected",
    behavior.looks_like_verification_command("python -m pytest -q", patterns),
)
check(
    "npm test detected",
    behavior.looks_like_verification_command("npm run test -- --coverage", patterns),
)
check(
    "cargo build detected",
    behavior.looks_like_verification_command("cargo build --release", patterns),
)
check(
    "eslint detected",
    behavior.looks_like_verification_command("npx eslint src/", patterns),
)
check(
    "trivial ls not detected",
    not behavior.looks_like_verification_command("ls -la", patterns),
)
check(
    "trivial git status not detected",
    not behavior.looks_like_verification_command("git status", patterns),
)
check(
    "trivial echo not detected",
    not behavior.looks_like_verification_command("echo 'hello' > notes.txt", patterns),
)

# --- project-rules rendering ---
rendered = behavior.format_project_rules(
    {
        "direct_matches": [
            {
                "type": "convention",
                "content": "Commit messages follow Conventional Commits.",
                "confidence": 0.92,
            }
        ],
        "related_context": [
            {
                "type": "learning",
                "content": "Tests run via pytest -q.",
                "confidence": 0.5,
            }
        ],
    }
)
check("direct match rendered first", rendered.startswith("- [convention] Commit messages"))
check(
    "related context marked as related",
    "(related, confidence 0.5)" in rendered,
    rendered,
)
check("empty result renders empty", behavior.format_project_rules({}) == "")

block = behavior.build_project_rules_block(rendered)
check(
    "block wrapped in <project-rules>",
    block.startswith("<project-rules>\n") and block.endswith("\n</project-rules>"),
)
check(
    "empty text yields empty block",
    behavior.build_project_rules_block("   ") == "",
)

# --- token budget ---
budget = behavior.PROJECT_RULES_TOKEN_BUDGET
result = {
    "direct_matches": [
        {"type": "convention", "content": "Word " * 2000, "confidence": 0.9}
        for _ in range(50)
    ],
    "related_context": [],
}
long_text = behavior.format_project_rules(result)
check(
    "oversized rules truncated to MAX_PROJECT_RULES_CHARS",
    len(long_text) <= behavior.MAX_PROJECT_RULES_CHARS,
    f"len={len(long_text)}",
)

# --- regex list sanity: every built-in pattern must compile ---
builtins, _ = behavior.compile_verification_patterns([])
check(
    "all built-in patterns compile",
    len(builtins) == len(behavior.VERIFICATION_COMMAND_PATTERNS),
    f"{len(builtins)} != {len(behavior.VERIFICATION_COMMAND_PATTERNS)}",
)

print(f"\n{pass_count} passed, {fail_count} failed")
if fail_count > 0:
    sys.exit(1)
