"""Project-rules resource content: query, budget and Markdown rendering."""

PROJECT_RULES_QUERY = (
    "What are the project rules and conventions: commit message format, "
    "dependency and package management, coding style, testing strategy, "
    "architecture decisions and documentation standards?"
)

PROJECT_RULES_TOKEN_BUDGET = 800

MAX_PROJECT_RULES_CHARS = 6000


def format_project_rules(result: dict) -> str:
    """Render query_context results as a structured Markdown project-rules block.

    Direct matches are rendered as project rules and related context as
    supporting context. Empty memory yields an empty block.
    """
    lines: list[str] = []

    direct_matches = result.get("direct_matches", [])
    related_context = result.get("related_context", [])

    if direct_matches:
        lines.extend(
            [
                "## Rules",
                "",
            ]
        )

        for entry in direct_matches:
            content = entry.get("content", "").strip()
            if content:
                lines.append(
                    f"  - [{entry.get('type')}] {content} (confidence {entry.get('confidence')})"
                )

    if related_context:
        if lines:
            lines.append("")

        lines.extend(
            [
                "## Supporting context",
                "",
            ]
        )

        for entry in related_context:
            content = entry.get("content", "").strip()
            if content:
                lines.append(
                    f"  - [{entry.get('type')}] {content} "
                    f"(supporting, confidence {entry.get('confidence')})"
                )

    if not lines:
        return ""

    text = "\n".join(lines)
    return text[:MAX_PROJECT_RULES_CHARS]


def build_project_rules_block(text: str) -> str:
    if not text or not text.strip():
        return ""

    return f"<project-rules>\n{text}\n</project-rules>"
