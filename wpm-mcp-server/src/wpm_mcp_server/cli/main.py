"""wpm CLI entry point (Lot 2B: thin dispatcher)."""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="wpm")
    sub = parser.add_subparsers(dest="subcommand")

    p = sub.add_parser("enable", help="Activate wpm in this project (writes wpm.config.json)")
    p.add_argument("db_dir", nargs="?", default=None)
    p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    sub.add_parser("disable", help="Remove wpm.config.json (keeps the database)")
    u = sub.add_parser("uninstall", help="Fully remove wpm from the system")
    u.add_argument("--force", "-f", action="store_true", help="Skip confirmation")

    p = sub.add_parser("search", help="Search the project's persistent memory")
    p.add_argument("query", help="Search query (any language — multilingual embedding model)")
    p.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    p.add_argument("--min-confidence", "-c", type=float, default=None, help="Minimum confidence threshold (default: no filter)")

    ex = sub.add_parser("export", help="Export the database to JSON (without embeddings)")
    ex.add_argument("-o", "--output", default=None, help="Output file path (default: stdout)")

    sub.add_parser("reembed", help="Re-embed all stored entries with the active embedding model (required after an embedding model change)")

    g = sub.add_parser("generate", help="Generate a new database from a JSON export (regenerates embeddings)")
    g.add_argument("input", help="Path to the JSON export file")
    g.add_argument("--output", required=True, help="Path for the new database file")

    sub.add_parser("new-user", help="Create (or update) a user profile interactively and make it the current user")

    p = sub.add_parser("current-user", help="Show the current user (no argument), print its language (--language), or switch to <name>")
    p.add_argument("name", nargs="?", default=None, help="Profile name to make current, or 'none' to deactivate")
    p.add_argument("--language", action="store_true", help="Print only the current user's language token")

    sub.add_parser("list-users", help="List saved user profiles ('*' marks the current one)")

    p = sub.add_parser("remove-user", help="Delete a user profile")
    p.add_argument("name", help="Profile name to delete")
    p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")

    uo = sub.add_parser("user-observations", help="Show behavioral observations and capture status (no argument) or turn capture on/off")
    uo.add_argument("state", nargs="?", default=None, help="'on' or 'off'")

    ruo = sub.add_parser("remove-user-observation", help="Delete one recorded observation by id")
    ruo.add_argument("id", type=int, help="Observation id (see 'wpm user-observations')")

    args = parser.parse_args()

    if args.subcommand == "enable":
        from wpm_mcp_server.cli.commands.enable import cmd_enable

        cmd_enable(args.db_dir, args.yes)
    elif args.subcommand == "disable":
        from wpm_mcp_server.cli.commands.disable import cmd_disable

        cmd_disable()
    elif args.subcommand == "uninstall":
        from wpm_mcp_server.cli.commands.uninstall import cmd_uninstall

        cmd_uninstall(args.force)
    elif args.subcommand == "search":
        from wpm_mcp_server.cli.commands.search import cmd_search

        cmd_search(args)
    elif args.subcommand == "export":
        from wpm_mcp_server.cli.commands.export import cmd_export

        cmd_export(args)
    elif args.subcommand == "reembed":
        from wpm_mcp_server.cli.commands.reembed import cmd_reembed

        cmd_reembed()
    elif args.subcommand == "generate":
        from wpm_mcp_server.cli.commands.generate import cmd_generate

        cmd_generate(args)
    elif args.subcommand == "current-user":
        from wpm_mcp_server.cli.commands.users import cmd_current_user

        cmd_current_user(args.name, getattr(args, "language", False))
    elif args.subcommand == "new-user":
        from wpm_mcp_server.cli.commands.users import cmd_new_user

        cmd_new_user()
    elif args.subcommand == "list-users":
        from wpm_mcp_server.cli.commands.users import cmd_list_users

        cmd_list_users()
    elif args.subcommand == "remove-user":
        from wpm_mcp_server.cli.commands.users import cmd_remove_user

        cmd_remove_user(args.name, args.yes)
    elif args.subcommand == "user-observations":
        from wpm_mcp_server.cli.commands.observations import cmd_user_observations

        cmd_user_observations(args.state)
    elif args.subcommand == "remove-user-observation":
        from wpm_mcp_server.cli.commands.observations import cmd_remove_user_observation

        cmd_remove_user_observation(args.id)
    else:
        parser.print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
