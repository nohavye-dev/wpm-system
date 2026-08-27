from __future__ import annotations

import sys

from wpm_mcp_server.cli.confirm import confirm
from wpm_mcp_server.cli.tui.language_prompt import prompt_language


def _users_repo():
    from wpm_mcp_server.core.errors import WpmError
    from wpm_mcp_server.storage.users import UserRepository, connect_users_db, resolve_users_db_path

    return UserRepository(connect_users_db(resolve_users_db_path())), WpmError


def cmd_new_user() -> None:
    repo, _ = _users_repo()

    while True:
        try:
            name = input("Enter your first name: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nwpm: aborted")
            sys.exit(0)
        if not name:
            print("wpm: a first name is required")
            continue
        if name.strip().lower() == "none":
            print("wpm: the name 'none' is reserved (it clears the active user)")
            continue
        break

    language = prompt_language()

    try:
        introduction = input("Introduce yourself (optional, Enter to skip): ").strip() or None
    except (EOFError, KeyboardInterrupt):
        introduction = None

    try:
        existing = repo.get_user(name)
    except ValueError:
        existing = None
    mode = "updated" if existing else "created"

    print("---")
    print(f"  name:         {name}")
    print(f"  language:     {language}")
    print(f"  introduction: {introduction or '(none)'}")
    print(f"  action:       {mode} + set as current user")
    if not confirm("Save? [Y/n] ", default=True):
        print("wpm: aborted")
        sys.exit(0)

    try:
        result = repo.save_user(name=name, language=language, introduction=introduction)
    except ValueError as exc:
        print(f"wpm: {exc}")
        sys.exit(1)
    print(f"wpm: profile '{result['profile']['name']}' {mode} and set as current user")


def cmd_current_user(name: str | None, language_only: bool = False) -> None:
    repo, WpmError = _users_repo()
    if name is not None and name.strip().lower() == "none":
        repo.clear_current_user()
        print("wpm: no current user — profile usage inactive")
        print("     'wpm new-user' or 'wpm current-user <name>' to reactivate")
        return
    profile = repo.get_current_user()
    if language_only:
        print((profile or {}).get("language") or "", end="")
        return
    if profile is None:
        print("wpm: no current user")
        print("     run 'wpm new-user' to create one, or 'wpm current-user <name>'")
        return
    if name is None:
        print(f"current user: {profile['name']}")
        if profile.get("language"):
            print(f"  language: {profile['language']}")
        if profile.get("introduction"):
            print(f"  introduction: {profile['introduction']}")
        return
    try:
        profile = repo.set_current_user(name)
    except WpmError as exc:
        print(f"wpm: {exc}")
        known = ", ".join(u["name"] for u in repo.get_users()) or "(none)"
        print(f"wpm: known users: {known}")
        sys.exit(1)
    print(f"wpm: current user set to '{profile['name']}'")


def cmd_list_users() -> None:
    repo, _ = _users_repo()
    users = repo.get_users()
    if not users:
        print("wpm: no user profiles yet — run 'wpm new-user'")
        return
    current = repo.get_current_user()
    current_name = current["name"] if current else None
    for user in users:
        marker = "*" if user["name"] == current_name else " "
        print(f"{marker} {user['name']}  updated {user['updated_at']}")
    if current_name is None:
        print("(no current user — 'wpm current-user <name>' to activate one)")


def cmd_remove_user(name: str, yes: bool) -> None:
    repo, WpmError = _users_repo()
    existing = repo.get_user(name)
    if existing is None:
        print(f"wpm: no user profile matching '{name}'")
        sys.exit(1)
    display = existing["name"]
    if not yes:
        if not confirm(f"Delete user profile '{display}'? [y/N] "):
            print("wpm: aborted")
            return
    result = repo.remove_user(existing["name"])
    suffix = " (was the current user)" if result.get("was_current") else ""
    print(f"wpm: removed user '{existing['name']}'{suffix}")
