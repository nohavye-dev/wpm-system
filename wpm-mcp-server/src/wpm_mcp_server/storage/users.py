"""Global user profiles: cross-project identity and observations.

A second, deliberately simple SQLite store next to the project memory:
no embeddings, no vec table, no scoring. The database lives under the
user's config directory so `wpm uninstall` (which removes DATA_DIR
wholesale) never touches it and profiles follow the person across
projects.

The user entity carries its identity (name, language, introduction)
plus one list-valued attribute: the unified observations table. Each
row carries a source:
  - declared: a preference the human just stated ("talk to me more
    simply") — authoritative, always injected, never decays;
  - inferred: a pattern the agent noticed (habit, workflow, knowledge,
    context, communication, personal trait) — weighted by `count`
    ("seen N times"), injected only once reinforced and refreshed,
    softly decaying out of the block after 30 idle days.
Capture of the inferred kind can be toggled off globally via meta
(wpm user-observations off); usage itself is governed by the
current-user pointer ('wpm current-user none' = inactive). Declared
statements are never blocked by that flag.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from wpm_mcp_server.core.constants import OBSERVATION_CATEGORIES, OBSERVATION_SOURCES
from wpm_mcp_server.core.errors import WpmError

CURRENT_USER_KEY = "current_user"
OBSERVATIONS_ENABLED_KEY = "observations_enabled"

# Reserved profile name: 'wpm current-user none' clears the active pointer,
# so a literal profile named "none" would be unreachable/ambiguous.
RESERVED_NAME = "none"

NO_CURRENT_USER_MESSAGE = (
    "no current user profile — run 'wpm new-user' to create one or "
    "'wpm current-user <name>' to activate one"
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    name         TEXT PRIMARY KEY COLLATE NOCASE,
    language     TEXT,
    introduction TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    id         INTEGER PRIMARY KEY,
    user       TEXT NOT NULL REFERENCES users(name) ON DELETE CASCADE,
    source     TEXT NOT NULL DEFAULT 'inferred',
    category   TEXT,
    content    TEXT NOT NULL,
    count      INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_observations_user ON observations(user);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def resolve_users_db_path() -> Path:
    """Resolve the users database path at call time (not import time).

    Priority: WPM_USERS_DB_PATH override, then $XDG_CONFIG_HOME/wpm-system,
    then ~/.config/wpm-system. The config directory is chosen over DATA_DIR
    on purpose: cmd_uninstall rmtree's DATA_DIR but never touches
    ~/.config/wpm-system, so profiles survive an uninstall.
    """
    override = os.environ.get("WPM_USERS_DB_PATH")
    if override:
        return Path(override).expanduser()
    config_home = os.environ.get(
        "XDG_CONFIG_HOME", str(Path.home() / ".config")
    )
    return Path(config_home) / "wpm-system" / "users.db"


def connect_users_db(path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) the users database with its schema."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    # Needed for the observations -> users ON DELETE CASCADE.
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def normalize_name(name: str) -> str:
    """Canonical profile key: trimmed, whitespace-collapsed.

    Case is preserved (the PK uses COLLATE NOCASE, so lookups are
    case-insensitive); only the reserved check is case-folded.
    """
    normalized = " ".join(str(name).split())
    if not normalized:
        raise ValueError("user name must not be empty")
    if normalized.lower() == RESERVED_NAME:
        raise ValueError(f"the name '{RESERVED_NAME}' is reserved (it clears the active user)")
    return normalized


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class UserRepository:
    """CRUD + current-user pointer over users / observations / meta."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ── profile ─────────────────────────────────────────────────────────

    def save_user(
        self,
        name: str,
        *,
        language: str | None = None,
        introduction: str | None = None,
    ) -> dict:
        """Upsert a profile and make it the current one.

        Omitted fields keep their previous value. Introducing yourself is
        switching: save always moves the current-user pointer.
        """
        key = normalize_name(name)
        now = _now()
        row = self.conn.execute(
            "SELECT created_at FROM users WHERE name = ?", (key,)
        ).fetchone()
        created = row is None
        if created:
            self.conn.execute(
                """
                INSERT INTO users (name, language, introduction, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (key, language, introduction, now, now),
            )
        else:
            self.conn.execute(
                """
                UPDATE users
                SET language = COALESCE(?, language),
                    introduction = COALESCE(?, introduction),
                    updated_at = ?
                WHERE name = ?
                """,
                (language, introduction, now, key),
            )
        canonical = self.conn.execute(
            "SELECT name FROM users WHERE name = ?", (key,)
        ).fetchone()["name"]
        self._set_meta(CURRENT_USER_KEY, canonical)
        self.conn.commit()
        return {"created": created, "profile": self.get_user(key)}

    def set_current_user(self, name: str) -> dict:
        """Point current_user at an existing profile (CLI-facing switch)."""
        key = normalize_name(name)
        profile = self.get_user(key)
        if profile is None:
            raise WpmError(f"unknown user '{key}'")
        self._set_meta(CURRENT_USER_KEY, profile["name"])
        self.conn.commit()
        return self.get_current_user()

    def clear_current_user(self) -> None:
        """Deactivate profile usage without deleting anything (CLI 'none')."""
        self._set_meta(CURRENT_USER_KEY, "")
        self.conn.commit()

    def remove_user(self, name: str) -> dict:
        """Delete a profile (cascades its observations); clear the pointer
        when it pointed at it."""
        key = normalize_name(name)
        profile = self.get_user(key)
        if profile is None:
            raise WpmError(f"unknown user '{key}'")
        was_current = (self.get_current_name() or "").lower() == key.lower()
        self.conn.execute("DELETE FROM users WHERE name = ?", (key,))
        if was_current:
            self._set_meta(CURRENT_USER_KEY, "")
        self.conn.commit()
        return {"removed": True, "was_current": was_current}

    # ── reads ───────────────────────────────────────────────────────────

    def get_users(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT name, updated_at FROM users ORDER BY name"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_user(self, name: str) -> dict | None:
        key = normalize_name(name)
        row = self.conn.execute(
            "SELECT * FROM users WHERE name = ?", (key,)
        ).fetchone()
        return self._row_to_profile(row) if row else None

    def get_current_user(self) -> dict | None:
        key = self.get_current_name()
        if not key:
            return None
        row = self.conn.execute(
            "SELECT * FROM users WHERE name = ?", (key,)
        ).fetchone()
        return self._row_to_profile(row) if row else None

    def get_current_name(self) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = ?", (CURRENT_USER_KEY,)
        ).fetchone()
        value = row["value"] if row else ""
        return value or None

    # ── observation capture flag (policy state, not data) ───────────────

    def observations_enabled(self) -> bool:
        """Absent meta key means enabled (capture on by default)."""
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = ?", (OBSERVATIONS_ENABLED_KEY,)
        ).fetchone()
        return (row["value"] if row else "1") != "0"

    def set_observations_enabled(self, enabled: bool) -> None:
        self._set_meta(OBSERVATIONS_ENABLED_KEY, "1" if enabled else "0")
        self.conn.commit()

    # ── unified observations (declared preferences + inferred patterns) ──

    def record_user_observation(
        self,
        content: str,
        *,
        source: str = "inferred",
        category: str | None = None,
        reinforce_id: int | None = None,
        replaces_id: int | None = None,
    ) -> dict:
        """Record one observation for the current user.

        source='inferred': a pattern the agent noticed. Requires a closed-
        taxonomy category; without reinforce_id a row is created with
        count=1; with reinforce_id the matching inferred observation's
        count is incremented and its category/content refreshed.

        source='declared': a preference the human just stated. Category is
        ignored (stored NULL); never gated by the capture flag; reinforce
        does not apply. With replaces_id, the referenced declared row is
        deleted first (hard replace by contradictory statement).
        """
        user = self.get_current_name()
        if not user:
            raise WpmError(NO_CURRENT_USER_MESSAGE)
        content = str(content).strip()
        if not content:
            raise ValueError("content must not be empty")
        if source not in OBSERVATION_SOURCES:
            raise ValueError(
                "source must be one of: " + ", ".join(OBSERVATION_SOURCES)
            )

        now = _now()
        if source == "declared":
            if reinforce_id is not None:
                raise ValueError("reinforce_id applies only to inferred observations")
            if replaces_id is not None:
                replaced = self.conn.execute(
                    "SELECT * FROM observations WHERE id = ? AND user = ?",
                    (int(replaces_id), user),
                ).fetchone()
                if replaced is None or replaced["source"] != "declared":
                    raise WpmError(
                        f"unknown declared statement {replaces_id} for current user"
                    )
                self.conn.execute(
                    "DELETE FROM observations WHERE id = ?", (int(replaces_id),)
                )
            cursor = self.conn.execute(
                """
                INSERT INTO observations
                    (user, source, category, content, count, created_at, updated_at)
                VALUES (?, 'declared', NULL, ?, 1, ?, ?)
                """,
                (user, content, now, now),
            )
            self.conn.commit()
            payload: dict = {
                "created": True,
                "observation": self._observation_row(
                    self.conn.execute(
                        "SELECT * FROM observations WHERE id = ?",
                        (cursor.lastrowid,),
                    ).fetchone()
                ),
            }
            if replaces_id is not None:
                payload["replaced"] = int(replaces_id)
            return payload

        if category is None or not str(category).strip():
            raise ValueError("inferred observations require a category")
        category = str(category).strip()
        if category not in OBSERVATION_CATEGORIES:
            raise ValueError(
                "category must be one of: " + ", ".join(OBSERVATION_CATEGORIES)
            )
        if replaces_id is not None:
            raise ValueError("replaces_id applies only to declared statements")

        if reinforce_id is not None:
            target = self.conn.execute(
                "SELECT source FROM observations WHERE id = ? AND user = ?",
                (int(reinforce_id), user),
            ).fetchone()
            if target is None:
                raise WpmError(f"unknown observation {reinforce_id} for current user")
            if target["source"] != "inferred":
                raise WpmError(
                    f"observation {reinforce_id} is a declared preference; "
                    "use replaces_id from a new declared statement to supersede it"
                )
            self.conn.execute(
                """
                UPDATE observations
                SET count = count + 1, category = ?, content = ?, updated_at = ?
                WHERE id = ?
                """,
                (category, content, now, int(reinforce_id)),
            )
            self.conn.commit()
            return {
                "created": False,
                "observation": self._observation_row(
                    self.conn.execute(
                        "SELECT * FROM observations WHERE id = ?", (int(reinforce_id),)
                    ).fetchone()
                ),
            }

        cursor = self.conn.execute(
            """
            INSERT INTO observations
                (user, source, category, content, count, created_at, updated_at)
            VALUES (?, 'inferred', ?, ?, 1, ?, ?)
            """,
            (user, category, content, now, now),
        )
        self.conn.commit()
        return {
            "created": True,
            "observation": self._observation_row(
                self.conn.execute(
                    "SELECT * FROM observations WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
            ),
        }

    def get_user_observations(self) -> list[dict]:
        """All observations of the current user, both sources.

        Unlike the injected block this includes singletons and stale
        entries: the model needs them to decide reinforce-versus-add and
        to spot contradictions before recording a declared statement.
        Declared rows come last so the recurring inferred patterns stay
        on top.
        """
        user = self.get_current_name()
        if not user:
            raise WpmError(NO_CURRENT_USER_MESSAGE)
        rows = self.conn.execute(
            """
            SELECT * FROM observations WHERE user = ?
            ORDER BY source DESC, count DESC, updated_at DESC
            """,
            (user,),
        ).fetchall()
        return [self._observation_row(row) for row in rows]

    def remove_observation(self, observation_id: int) -> dict:
        user = self.get_current_name()
        if not user:
            raise WpmError(NO_CURRENT_USER_MESSAGE)
        row = self.conn.execute(
            "SELECT id FROM observations WHERE id = ? AND user = ?",
            (int(observation_id), user),
        ).fetchone()
        if row is None:
            raise WpmError(f"unknown observation {observation_id} for current user")
        self.conn.execute("DELETE FROM observations WHERE id = ?", (int(observation_id),))
        self.conn.commit()
        return {"removed": True}

    # ── internals ───────────────────────────────────────────────────────

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> dict:
        return {
            "name": row["name"],
            "language": row["language"],
            "introduction": row["introduction"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _observation_row(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "source": row["source"],
            "category": row["category"],
            "content": row["content"],
            "count": row["count"],
            "updated_at": row["updated_at"],
        }

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
