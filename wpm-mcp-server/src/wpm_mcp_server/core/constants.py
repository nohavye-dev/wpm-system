"""Fixed deployment-time constants."""

# Not exposed via JSON config: changing it requires re-embedding every
# existing entry (a stored vector's dimension can't change in place), so
# it's a deployment-time decision, not a runtime tuning knob.
EMBEDDING_DIM = 384

# Response-language autocomplete for `wpm new-user`: the ~50 languages the
# multilingual embedding model covers, as English tokens (lowercase) so the
# resolved language interpolates cleanly into the English prompt clauses
# ("MUST be written in french"). Alphabetized; approximate coverage — the
# autocomplete is a UX aid, the value is free-form beyond this list.
SUPPORTED_LANGUAGES = (
    "afrikaans",
    "arabic",
    "armenian",
    "basque",
    "bengali",
    "bosnian",
    "bulgarian",
    "catalan",
    "chinese (simplified)",
    "chinese (traditional)",
    "croatian",
    "czech",
    "danish",
    "dutch",
    "english",
    "estonian",
    "filipino",
    "finnish",
    "french",
    "galician",
    "georgian",
    "german",
    "greek",
    "gujarati",
    "hebrew",
    "hindi",
    "hungarian",
    "indonesian",
    "italian",
    "japanese",
    "kannada",
    "kazakh",
    "korean",
    "latvian",
    "lithuanian",
    "macedonian",
    "malay",
    "marathi",
    "nepali",
    "norwegian",
    "persian",
    "polish",
    "portuguese",
    "romanian",
    "russian",
    "serbian",
    "sinhala",
    "slovak",
    "slovenian",
    "spanish",
    "swahili",
    "swedish",
    "tagalog",
    "tamil",
    "telugu",
    "thai",
    "turkish",
    "ukrainian",
    "urdu",
    "uzbek",
    "vietnamese",
    "welsh",
    "zulu",
)


def match_languages(query: str, limit: int = 8) -> list[str]:
    """Case-insensitive prefix match over SUPPORTED_LANGUAGES (pure, testable)."""
    q = query.strip().lower()
    if not q:
        return []
    return [lang for lang in SUPPORTED_LANGUAGES if lang.lower().startswith(q)][:limit]


# Closed taxonomy for behavioral observations (record_user_observation):
# the model must pick exactly one value, no free-form 'other' — keeps
# users.db structured and the injected block groupable. The tuple order is
# also the display priority (habit first) in <current-user> and in
# 'wpm user-observations'.
OBSERVATION_CATEGORIES = (
    "habit",
    "workflow",
    "knowledge",
    "context",
    "communication",
    "personal",
)

# Where an observation comes from: declared = the human stated it
# (authoritative, always injected, never decays); inferred = the agent
# noticed a pattern (recurrence-gated, softly decaying).
OBSERVATION_SOURCES = (
    "inferred",
    "declared",
)
