"""Fixed deployment-time constants."""

# Not exposed via JSON config: changing it requires re-embedding every
# existing entry (a stored vector's dimension can't change in place), so
# it's a deployment-time decision, not a runtime tuning knob.
EMBEDDING_DIM = 384
