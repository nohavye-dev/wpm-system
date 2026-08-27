from __future__ import annotations

import sys

from wpm_mcp_server.core.constants import OBSERVATION_CATEGORIES


def _users_repo():
    from wpm_mcp_server.core.errors import WpmError
    from wpm_mcp_server.storage.users import UserRepository, connect_users_db, resolve_users_db_path

    return UserRepository(connect_users_db(resolve_users_db_path())), WpmError


def cmd_user_observations(state_arg: str | None) -> None:
    repo, WpmError = _users_repo()
    if state_arg is not None and state_arg.strip().lower() in ("on", "off"):
        enabled = state_arg.strip().lower() == "on"
        repo.set_observations_enabled(enabled)
        print(f"wpm: user observation capture {'enabled' if enabled else 'disabled'}")
        return
    if state_arg is not None:
        print("wpm: usage — wpm user-observations [on|off]")
        sys.exit(1)

    status = "on" if repo.observations_enabled() else "off"
    print(f"observation capture: {status} (applies to inferred patterns only)")
    current = repo.get_current_user()
    if current is None:
        print("(no current user — observations require one; 'wpm new-user' to start)")
        return
    observations = repo.get_user_observations()
    if not observations:
        print("no recorded observations yet for", current["name"])
        return

    declared = [o for o in observations if o.get("source") == "declared"]
    inferred = [o for o in observations if o.get("source") != "declared"]

    def print_rows(rows):
        by_recency = sorted(rows, key=lambda o: str(o["updated_at"]), reverse=True)
        for obs in sorted(by_recency, key=lambda o: int(o["count"]), reverse=True):
            last_seen = str(obs["updated_at"])[:10]
            print(f"  [{obs['id']}] {obs['content']} (last {last_seen})")

    if declared:
        print("declared preferences:")
        print_rows(declared)
    if not inferred:
        return

    grouped: dict = {}
    for obs in inferred:
        grouped.setdefault(obs["category"] or "unknown", []).append(obs)
    order = {c: i for i, c in enumerate(OBSERVATION_CATEGORIES)}
    for category in sorted(grouped, key=lambda c: (order.get(c, len(order)), c)):
        print(f"{category}:")
        rows = grouped[category]
        by_recency = sorted(rows, key=lambda o: str(o["updated_at"]), reverse=True)
        for obs in sorted(by_recency, key=lambda o: int(o["count"]), reverse=True):
            last_seen = str(obs["updated_at"])[:10]
            print(f"  [{obs['id']}] x{obs['count']} {obs['content']} (last {last_seen})")


def cmd_remove_user_observation(observation_id: int) -> None:
    repo, WpmError = _users_repo()
    try:
        repo.remove_observation(observation_id)
    except (WpmError, ValueError) as exc:
        print(f"wpm: {exc}")
        sys.exit(1)
    print(f"wpm: removed observation {observation_id}")
