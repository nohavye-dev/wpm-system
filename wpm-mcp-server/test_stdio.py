import asyncio
import json
import os
import sys

sys.path.insert(0, "src")

# Absolute so the stdio subprocess resolves the package regardless of the
# pytest invocation directory (repo root vs this directory).
_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pass_count = 0
fail_count = 0


def check(label, cond, detail=""):
    global pass_count, fail_count
    if cond:
        pass_count += 1
        print(f"  OK  {label}")
    else:
        fail_count += 1
        print(f"  FAIL {label}" + (f": {detail}" if detail else ""))


async def main_language():
    global pass_count, fail_count
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "wpm_mcp_server"],
        env={
            "WPM_DB_PATH": ".stdio_test_lang.db",
            "WPM_USERS_DB_PATH": ".stdio_test_users_lang.db",
            "WPM_RESPONSE_LANGUAGE": "french",
            "PYTHONPATH": _SRC,
        },
    )
    try:
        async with stdio_client(params) as (read, write):  # noqa: SIM117
            async with ClientSession(read, write) as session:
                init = await session.initialize()

                inst = getattr(init, "instructions", "") or ""
                check(
                    "initialize.instructions reflect configured language",
                    "MUST be written in french" in inst,
                    f"len={len(inst)}",
                )

                tools = await session.list_tools()
                store_desc = ""
                for t in tools.tools:
                    if t.name == "store_entry":
                        store_desc = t.description or ""
                check(
                    "store_entry description present and compact",
                    "Store exactly one durable memory entry" in store_desc
                    and len(store_desc) < 1600,
                    f"len={len(store_desc)}",
                )

                rules_resource = await session.read_resource("wpm://memory-rules")  # pyright: ignore[reportArgumentType]
                rules_text = rules_resource.contents[0].text  # pyright: ignore[reportAttributeAccessIssue]
                check(
                    "memory-rules resource reflects configured language",
                    "MUST be written in french" in rules_text,
                )
    finally:
        for f in [
            ".stdio_test_lang.db",
            ".stdio_test_lang.db-wal",
            ".stdio_test_lang.db-shm",
            ".stdio_test_users_lang.db",
            ".stdio_test_users_lang.db-wal",
            ".stdio_test_users_lang.db-shm",
        ]:
            if os.path.exists(f):
                os.remove(f)

    print(f"\n{pass_count} passed, {fail_count} failed")
    if fail_count > 0:
        sys.exit(1)


async def main_observation_disabled():
    """Capture toggled off in users.db before the server starts: inferred
    recordings must refuse cleanly while declared statements and reads
    still work.
    """
    global pass_count, fail_count
    from wpm_mcp_server.storage.users import (
        UserRepository,
        connect_users_db,
    )

    seed = connect_users_db(".stdio_test_users_off.db")
    repo = UserRepository(seed)
    repo.save_user("Noha", language="french")
    repo.set_observations_enabled(False)
    seed.close()

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "wpm_mcp_server"],
        env={"WPM_USERS_DB_PATH": ".stdio_test_users_off.db", "PYTHONPATH": _SRC},
    )
    try:
        async with stdio_client(params) as (read, write):  # noqa: SIM117
            async with ClientSession(read, write) as session:
                await session.initialize()

                rec = json.loads(
                    (
                        await session.call_tool(
                            "record_user_observation",
                            {"content": "anything"},
                        )
                    )
                    .content[0]
                    .text  # pyright: ignore[reportAttributeAccessIssue]
                )
                check(
                    "disabled capture rejects inferred recording",
                    rec.get("error") is True
                    and rec.get("disabled") is True
                    and "user-observations on" in rec.get("message", ""),
                    f"got {rec}",
                )

                lst = json.loads(
                    (await session.call_tool("get_user_observations", {})).content[0].text  # pyright: ignore[reportAttributeAccessIssue]
                )
                check(
                    "listing still available with capture off",
                    lst.get("error") is None and lst.get("total") == 0,
                    f"got {lst}",
                )

                dec = json.loads(
                    (
                        await session.call_tool(
                            "record_user_observation",
                            {"content": "always answer in french", "source": "declared"},
                        )
                    )
                    .content[0]
                    .text  # pyright: ignore[reportAttributeAccessIssue]
                )
                check(
                    "declared recording unaffected by capture flag",
                    dec.get("created") is True and dec["observation"]["source"] == "declared",
                    f"got {dec}",
                )

                cur = json.loads(
                    (await session.call_tool("get_user", {})).content[0].text  # pyright: ignore[reportAttributeAccessIssue]
                )
                check(
                    "profile tools unaffected by capture flag",
                    cur.get("current") is True and cur["profile"]["name"] == "Noha",
                    f"got {cur}",
                )

                resource = await session.read_resource("wpm://current-user")  # pyright: ignore[reportArgumentType]
                text = resource.contents[0].text  # pyright: ignore[reportAttributeAccessIssue]
                check(
                    "resource renders profile + declared with capture off",
                    "<current-user>" in text
                    and "## User preferences" in text
                    and "always answer in french" in text
                    and "Observed" not in text,
                    f"got {text[:200]}",
                )
    finally:
        for f in [
            ".stdio_test_users_off.db",
            ".stdio_test_users_off.db-wal",
            ".stdio_test_users_off.db-shm",
        ]:
            if os.path.exists(f):
                os.remove(f)

    print(f"\n{pass_count} passed, {fail_count} failed")
    if fail_count > 0:
        sys.exit(1)


async def main():
    global pass_count, fail_count
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "wpm_mcp_server"],
        env={
            "WPM_DB_PATH": ".stdio_test.db",
            "WPM_USERS_DB_PATH": ".stdio_test_users.db",
            "PYTHONPATH": _SRC,
        },
    )
    # Pre-seed the global user store: profile creation is CLI-only now, and
    # the seeded language exercises the resolveResponseLanguage override.
    from wpm_mcp_server.storage.users import UserRepository, connect_users_db

    _seed = connect_users_db(".stdio_test_users.db")
    UserRepository(_seed).save_user("Noha", language="french", introduction="dev full-stack")
    _seed.close()
    try:
        async with stdio_client(params) as (read, write):  # noqa: SIM117
            async with ClientSession(read, write) as session:
                init = await session.initialize()

                # --- tool listing ---
                tools = await session.list_tools()
                names = [t.name for t in tools.tools]
                check("14 tools registered", len(names) == 14, f"got {len(names)}: {names}")
                check("store_entry present", "store_entry" in names)
                check("query_context present", "query_context" in names)
                check("validate_entry present", "validate_entry" in names)
                check("contradict_entry present", "contradict_entry" in names)
                check("link_entries present", "link_entries" in names)
                check("get_memory_stats present", "get_memory_stats" in names)
                check("pin_entry present", "pin_entry" in names)
                check("deprecate_entry present", "deprecate_entry" in names)
                check("restore_entry present", "restore_entry" in names)
                check("list_entries present", "list_entries" in names)
                check("record_execution present", "record_execution" in names)
                check("get_user present", "get_user" in names)
                check("record_user_observation present", "record_user_observation" in names)
                check("get_user_observations present", "get_user_observations" in names)
                check("save_user absent", "save_user" not in names)
                check("add_user_preference absent (merged)", "add_user_preference" not in names)
                check("get_user_preferences absent (merged)", "get_user_preferences" not in names)

                query_desc = ""
                for t in tools.tools:
                    if t.name == "query_context":
                        query_desc = t.description or ""
                check(
                    "query_context description has BEFORE trigger",
                    "before" in query_desc.lower() and "grep" in query_desc.lower(),
                    query_desc,
                )

                # --- initialize instructions carry the behavior rules ---
                inst = getattr(init, "instructions", "") or ""
                check(
                    "initialize.instructions embed memory rules",
                    "wpm" in inst.lower() and "memory" in inst.lower(),
                    f"len={len(inst)}",
                )
                check(
                    "profile language overrides config in instructions",
                    "MUST be written in french" in inst,
                    f"got {inst[-200:]}",
                )

                # --- resources ---
                resources = await session.list_resources()
                resource_uris = [str(r.uri) for r in resources.resources]
                check(
                    "wpm://project-rules resource",
                    "wpm://project-rules" in resource_uris,
                    f"got {resource_uris}",
                )
                check(
                    "wpm://memory-rules resource",
                    "wpm://memory-rules" in resource_uris,
                    f"got {resource_uris}",
                )
                check(
                    "wpm://verification-commands resource",
                    "wpm://verification-commands" in resource_uris,
                    f"got {resource_uris}",
                )
                check(
                    "wpm://current-user resource",
                    "wpm://current-user" in resource_uris,
                    f"got {resource_uris}",
                )
                rules_resource = await session.read_resource("wpm://memory-rules")  # pyright: ignore[reportArgumentType]
                rules_text = rules_resource.contents[0].text  # pyright: ignore[reportAttributeAccessIssue]
                check(
                    "memory-rules resource non-empty",
                    len(rules_text) > 200,
                    f"len={len(rules_text)}",
                )

                # --- record_execution: non-trivial command stored as execution_result ---
                rec_raw = await session.call_tool(
                    "record_execution",
                    {
                        "command": "python -m pytest tests/test_api.py -x --cov",
                        "succeeded": True,
                        "session_id": "smoke-test-session",
                    },
                )
                rec = json.loads(rec_raw.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
                check(
                    "record_execution stores execution_result entry",
                    rec.get("type") == "execution_result",
                    f"got {rec}",
                )
                if rec.get("entry_id"):
                    vrec = json.loads(
                        (
                            await session.call_tool(
                                "validate_entry",
                                {
                                    "entry_id": rec["entry_id"],
                                    "evidence_type": "execution_verified",
                                    "evidence_ref": "pytest smoke test",
                                    "session_id": "smoke-test-session",
                                },
                            )
                        )
                        .content[0]
                        .text  # pyright: ignore[reportAttributeAccessIssue]
                    )
                    check(
                        "record_execution entry is validatable",
                        vrec.get("validation_score", 0) > 0,
                        f"got {vrec.get('validation_score')}",
                    )

                # --- record_execution: trivial command rejected ---
                triv_raw = await session.call_tool(
                    "record_execution",
                    {
                        "command": "ls -la",
                        "succeeded": True,
                        "session_id": "smoke-test-session",
                    },
                )
                triv = json.loads(triv_raw.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
                check(
                    "record_execution rejects trivial commands",
                    triv.get("error") is True,
                    f"got {triv}",
                )

                # --- store entry ---
                store_raw = await session.call_tool(
                    "store_entry",
                    {
                        "type": "convention",
                        "content": "Use camelCase for JS private fields prefixed with underscore",
                        "source": "official_doc",
                    },
                )
                store = json.loads(store_raw.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
                check("store_entry returns entry_id", "entry_id" in store)
                check("store_entry returns type", store.get("type") == "convention")
                check(
                    "store_entry provenance for official_doc",
                    store.get("provenance_score") == 0.9,
                    f"got {store.get('provenance_score')}",
                )
                check(
                    "store_entry reminder: MEMORY FIRST when no prior query",
                    "MEMORY FIRST" in store.get("reminder", ""),
                    f"got {store.get('reminder')}",
                )
                check(
                    "store_entry reminder: validate once confirmed",
                    "validate_entry" in store.get("reminder", ""),
                    f"got {store.get('reminder')}",
                )
                entry_id = store["entry_id"]

                # --- query: direct semantic match ---
                query_raw = await session.call_tool(
                    "query_context",
                    {"query": "javascript naming convention private fields"},
                )
                query = json.loads(query_raw.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
                check(
                    "query_context returns direct_matches key",
                    "direct_matches" in query,
                )
                check(
                    "query_context has at least 1 direct match",
                    len(query.get("direct_matches", [])) > 0,
                )
                if query.get("direct_matches"):
                    top = query["direct_matches"][0]
                    check("top match is our entry", top["entry_id"] == entry_id)
                    check(
                        "semantic similarity > 0.3",
                        top["similarity"] > 0.3,
                        f"got {top['similarity']}",
                    )
                    check(
                        "returned content matches stored content",
                        top["content"]
                        == "Use camelCase for JS private fields prefixed with underscore",
                    )

                # --- validate entry ---
                validate_raw = await session.call_tool(
                    "validate_entry",
                    {
                        "entry_id": entry_id,
                        "evidence_type": "execution_verified",
                        "evidence_ref": "passed lint check",
                        "session_id": "smoke-test-session",
                    },
                )
                validate = json.loads(validate_raw.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
                check(
                    "validate_entry increases validation_score",
                    validate.get("validation_score", 0) > 0.0,
                    f"got {validate.get('validation_score')}",
                )

                # --- store second entry, contradict first ---
                store2_raw = await session.call_tool(
                    "store_entry",
                    {
                        "type": "convention",
                        "content": "Use snake_case for all JavaScript fields",
                        "source": "agent_inference",
                    },
                )
                store2 = json.loads(store2_raw.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
                second_id = store2["entry_id"]
                check("second entry stored", "entry_id" in store2)
                check(
                    "store_entry after query has no MEMORY FIRST reminder",
                    "MEMORY FIRST" not in store2.get("reminder", ""),
                    f"got {store2.get('reminder')}",
                )

                contradict_raw = await session.call_tool(
                    "contradict_entry",
                    {
                        "entry_id": entry_id,
                        "conflicting_entry_id": second_id,
                        "evidence_type": "cross_reference",
                        "evidence_ref": "project style guide says snake_case",
                    },
                )
                contradict = json.loads(contradict_raw.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
                check(
                    "contradict returns conflicting_entry_id",
                    contradict.get("conflicting_entry_id") == second_id,
                )

                # re-query: conflict should appear
                query2_raw = await session.call_tool(
                    "query_context", {"query": "javascript naming convention"}
                )
                query2 = json.loads(query2_raw.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
                check(
                    "conflict surfaced in query",
                    len(query2.get("conflicts", [])) > 0,
                )
                check(
                    "query_context reminder on conflicts",
                    "conflicts" in query2.get("reminder", "").lower(),
                    f"got {query2.get('reminder')}",
                )

                # --- link entries ---
                link_raw = await session.call_tool(
                    "link_entries",
                    {
                        "source_id": entry_id,
                        "target_id": second_id,
                        "relation_type": "depends_on",
                        "weight": 0.5,
                    },
                )
                link = json.loads(link_raw.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
                check(
                    "link_entries works",
                    link.get("relation_type") == "depends_on",
                )

                # --- error: invalid type ---
                err_raw = await session.call_tool(
                    "store_entry",
                    {
                        "type": "not_a_valid_type",
                        "content": "test",
                        "source": "agent_inference",
                    },
                )
                check(
                    "invalid type returns error",
                    err_raw.isError is True,
                    f"got {err_raw.content[0].text if err_raw.content else ''}",  # pyright: ignore[reportAttributeAccessIssue]
                )

                # --- error: link nonexistent entry ---
                err2_raw = await session.call_tool(
                    "link_entries",
                    {
                        "source_id": entry_id,
                        "target_id": "nonexistent-id-12345",
                        "relation_type": "related",
                    },
                )
                err2 = json.loads(err2_raw.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
                check(
                    "nonexistent link returns error",
                    err2.get("error") is True,
                    f"got {err2}",
                )

                # --- read-only tools are silent (no reminder) ---
                stats_raw = await session.call_tool("get_memory_stats", {})
                stats = json.loads(stats_raw.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
                check("get_memory_stats has no reminder", "reminder" not in stats)

                list_raw = await session.call_tool("list_entries", {"limit": 5})
                listing = json.loads(list_raw.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
                check("list_entries has no reminder", "reminder" not in listing)

                # --- user profiles: seeded profile, reads + declarations ---
                cur = json.loads(
                    (await session.call_tool("get_user", {})).content[0].text  # pyright: ignore[reportAttributeAccessIssue]
                )
                check(
                    "get_user returns seeded profile",
                    cur.get("current") is True
                    and cur["profile"]["name"] == "Noha"
                    and cur["profile"]["language"] == "french",
                    f"got {cur}",
                )

                pref_add = json.loads(
                    (
                        await session.call_tool(
                            "record_user_observation",
                            {
                                "content": "Noha prefers that I be more concise",
                                "source": "declared",
                            },
                        )
                    )
                    .content[0]
                    .text  # pyright: ignore[reportAttributeAccessIssue]
                )
                check(
                    "declared preference recorded",
                    pref_add.get("created") is True
                    and pref_add["observation"]["source"] == "declared",
                    f"got {pref_add}",
                )

                obs_list = json.loads(
                    (await session.call_tool("get_user_observations", {})).content[0].text  # pyright: ignore[reportAttributeAccessIssue]
                )
                check(
                    "listing shows the declared statement",
                    obs_list.get("total") == 1
                    and obs_list["observations"][0]["source"] == "declared",
                    f"got {obs_list}",
                )

                user_resource = await session.read_resource("wpm://current-user")  # pyright: ignore[reportArgumentType]
                user_text = user_resource.contents[0].text  # pyright: ignore[reportAttributeAccessIssue]
                check(
                    "current-user resource renders identity + preferences",
                    user_text.startswith("<current-user>")
                    and "name: Noha" in user_text
                    and "respond in: french" in user_text
                    and "## User preferences" in user_text
                    and "more concise" in user_text,
                    f"got {user_text[:200]}",
                )

                # --- inferred observations: record, reinforce, inject ---
                obs1 = json.loads(
                    (
                        await session.call_tool(
                            "record_user_observation",
                            {
                                "source": "inferred",
                                "category": "workflow",
                                "content": "mixes up rebase and merge",
                            },
                        )
                    )
                    .content[0]
                    .text  # pyright: ignore[reportAttributeAccessIssue]
                )
                check(
                    "record_user_observation creates singleton",
                    obs1.get("created") is True and obs1["observation"]["count"] == 1,
                    f"got {obs1}",
                )

                listing = json.loads(
                    (await session.call_tool("get_user_observations", {})).content[0].text  # pyright: ignore[reportAttributeAccessIssue]
                )
                check(
                    "listing holds declared + inferred singleton",
                    listing.get("total") == 2,
                    f"got {listing}",
                )

                obs2 = json.loads(
                    (
                        await session.call_tool(
                            "record_user_observation",
                            {
                                "source": "inferred",
                                "category": "habit",
                                "content": "confuses rebase with merge semantics",
                                "reinforce_id": obs1["observation"]["id"],
                            },
                        )
                    )
                    .content[0]
                    .text  # pyright: ignore[reportAttributeAccessIssue]
                )
                check(
                    "reinforce increments count",
                    obs2.get("created") is False and obs2["observation"]["count"] == 2,
                    f"got {obs2}",
                )

                user_resource = await session.read_resource("wpm://current-user")  # pyright: ignore[reportArgumentType]
                user_text = user_resource.contents[0].text  # pyright: ignore[reportAttributeAccessIssue]
                check(
                    "recurring observation surfaces in injected block",
                    "Observed recurring patterns" in user_text and "(seen x2, last " in user_text,
                    f"got {user_text[:200]}",
                )

                gated = json.loads(
                    (await session.call_tool("get_user", {})).content[0].text  # pyright: ignore[reportAttributeAccessIssue]
                )
                check("profile still current after observations", gated.get("current") is True)

    finally:
        for f in [
            ".stdio_test.db",
            ".stdio_test.db-wal",
            ".stdio_test.db-shm",
            ".stdio_test_users.db",
            ".stdio_test_users.db-wal",
            ".stdio_test_users.db-shm",
        ]:
            if os.path.exists(f):
                os.remove(f)

    print(f"\n{pass_count} passed, {fail_count} failed")
    if fail_count > 0:
        sys.exit(1)


asyncio.run(main())
asyncio.run(main_language())
asyncio.run(main_observation_disabled())
