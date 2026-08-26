"""Current-user resource content: Markdown rendering + tagged block.

Mirrors project_rules.py: the server renders the tagged block once and
every consumer pushes or reads those exact bytes — the legacy pull path
(agent reads the resource) and the plugin_master push path (InjectionBlock
setBody, no tag) stay byte-identical by construction.
"""

from wpm_mcp_server.core.constants import OBSERVATION_CATEGORIES

# Budget for the inferred part of the block only. Declared preferences are
# always rendered in full before it — they can never be truncated away.
MAX_CURRENT_USER_CHARS = 2000

# Only inferred patterns reinforced at least this many times surface in
# the injected block; singletons stay visible to the model via the
# get_user_observations tool until they recur.
RECURRENCE_THRESHOLD = 2

# Soft decay: an inferred observation stops being injected once it has not
# been reinforced for this many days (its count is preserved in users.db;
# a new reinforce brings it back). Keeps stale patterns from polluting
# every turn's context without any explicit cleanup.
OBSERVATION_STALENESS_DAYS = 30

OBSERVED_SECTION_TITLE = "Observed recurring patterns"


def format_current_user(
    profile: dict | None,
    declared: list[dict] | None = None,
    observations: list[dict] | None = None,
) -> str:
    """Render a user profile as a structured Markdown block.

    `declared` rows (source='declared', human-stated preferences) are
    rendered in full, without budget. `observations` receives only the
    already-filtered recurring inferred entries; they fill the remaining
    MAX_CURRENT_USER_CHARS budget, grouped by category in taxonomy order.
    Rendering stays pure, filtering lives with the caller. No profile (or
    nothing to show) yields an empty string.
    """
    if not profile:
        return ""

    lines: list[str] = []

    identity = []
    if profile.get("name"):
        identity.append(f"name: {profile['name']}")
    if profile.get("language"):
        identity.append(f"respond in: {profile['language']}")
    if profile.get("introduction"):
        identity.append(f"about: {profile['introduction']}")
    if identity:
        lines.extend(["## Identity", ""])
        lines.extend(f"  - {item}" for item in identity)

    stated = [p for p in (declared or []) if p.get("content")]
    if stated:
        if lines:
            lines.append("")
        lines.extend(["## User preferences", ""])
        lines.extend(f"  - {p['content']}" for p in stated)

    recurring = [o for o in (observations or []) if o.get("content")]
    if recurring:
        tail: list[str] = [
            f"## {OBSERVED_SECTION_TITLE}",
            "",
            "  (inferred from interaction, not stated by the user — the",
            "   preferences above remain authoritative; verify before relying",
            "   on these)",
            "",
        ]
        for category in OBSERVATION_CATEGORIES:
            group = sorted(
                (o for o in recurring if o.get("category", "unknown") == category),
                key=lambda o: (-int(o.get("count", 1)), str(o.get("updated_at", ""))),
            )
            if not group:
                continue
            candidate = [f"### {category.capitalize()}", ""]
            candidate.extend(
                f"  - {observation['content']} "
                f"(seen x{observation.get('count', 1)}, last {str(observation.get('updated_at', ''))[:10]})"
                for observation in group
            )
            candidate.append("")
            if len("\n".join(tail + candidate)) > MAX_CURRENT_USER_CHARS:
                break
            tail.extend(candidate)

        trimmed = "\n".join(tail).rstrip()
        if trimmed:
            lines.append("")
            lines.append(trimmed)

    while lines and lines[-1] == "":
        lines.pop()

    if not lines:
        return ""

    return "\n".join(lines)


def build_current_user_block(text: str) -> str:
    if not text or not text.strip():
        return ""
    return f"<current-user>\n{text}\n</current-user>"
