"""Prompt-variant selection driven by the spawning host.

Legacy (default): opencode hosts the server and injects
initialize.instructions — pull instructions ("Read the wpm://… resource")
are rendered because the LLM can read resources through the host.

Push (WPM_PROMPT_MODE=push, set by the plugin when it spawns and owns the
server): rules are pushed into context every turn and no resource-read tool
exists in that mode, so pull instructions are omitted at construction time
— the text is never mutated after rendering.
"""

import os


def push_mode() -> bool:
    return os.environ.get("WPM_PROMPT_MODE", "").strip().lower() == "push"
