"""Persistence layer: repository, read-side queries, lifecycle operations.

Public API re-exported here so callers can simply
`from wpm_mcp_server.storage import Repository`.
"""

from wpm_mcp_server.core.errors import WpmError
from wpm_mcp_server.storage.lifecycle import export_db, generate_db, reembed_all
from wpm_mcp_server.storage.model_guard import ensure_embedding_model
from wpm_mcp_server.storage.repository import Repository

__all__ = [
    "Repository",
    "WpmError",
    "ensure_embedding_model",
    "export_db",
    "generate_db",
    "reembed_all",
]
