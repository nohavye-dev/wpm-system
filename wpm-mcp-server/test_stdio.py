import asyncio
import json
import os
import sys
sys.path.insert(0, "src")

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
            "WPM_RESPONSE_LANGUAGE": "french",
            "PYTHONPATH": "src",
        },
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()

                inst = getattr(init, "instructions", "") or ""
                check(
                    "initialize.instructions reflect configured language",
                    "written in french" in inst,
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

                rules_resource = await session.read_resource("wpm://memory-rules")
                rules_text = rules_resource.contents[0].text
                check(
                    "memory-rules resource reflects configured language",
                    "written in french" in rules_text,
                )
    finally:
        for f in [".stdio_test_lang.db", ".stdio_test_lang.db-wal", ".stdio_test_lang.db-shm"]:
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
        env={"WPM_DB_PATH": ".stdio_test.db", "PYTHONPATH": "src"},
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()

                # --- tool listing ---
                tools = await session.list_tools()
                names = [t.name for t in tools.tools]
                check("11 tools registered", len(names) == 11, f"got {len(names)}: {names}")
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
                rules_resource = await session.read_resource("wpm://memory-rules")
                rules_text = rules_resource.contents[0].text
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
                rec = json.loads(rec_raw.content[0].text)
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
                        ).content[0].text
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
                triv = json.loads(triv_raw.content[0].text)
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
                store = json.loads(store_raw.content[0].text)
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
                query = json.loads(query_raw.content[0].text)
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
                    check(
                        "top match is our entry", top["entry_id"] == entry_id
                    )
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
                validate = json.loads(validate_raw.content[0].text)
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
                store2 = json.loads(store2_raw.content[0].text)
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
                contradict = json.loads(contradict_raw.content[0].text)
                check(
                    "contradict returns conflicting_entry_id",
                    contradict.get("conflicting_entry_id") == second_id,
                )

                # re-query: conflict should appear
                query2_raw = await session.call_tool(
                    "query_context", {"query": "javascript naming convention"}
                )
                query2 = json.loads(query2_raw.content[0].text)
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
                link = json.loads(link_raw.content[0].text)
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
                    f"got {err_raw.content[0].text if err_raw.content else ''}",
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
                err2 = json.loads(err2_raw.content[0].text)
                check(
                    "nonexistent link returns error",
                    err2.get("error") is True,
                    f"got {err2}",
                )

                # --- read-only tools are silent (no reminder) ---
                stats_raw = await session.call_tool("get_memory_stats", {})
                stats = json.loads(stats_raw.content[0].text)
                check("get_memory_stats has no reminder", "reminder" not in stats)

                list_raw = await session.call_tool("list_entries", {"limit": 5})
                listing = json.loads(list_raw.content[0].text)
                check("list_entries has no reminder", "reminder" not in listing)

    finally:
        for f in [".stdio_test.db", ".stdio_test.db-wal", ".stdio_test.db-shm"]:
            if os.path.exists(f):
                os.remove(f)

    print(f"\n{pass_count} passed, {fail_count} failed")
    if fail_count > 0:
        sys.exit(1)


asyncio.run(main())
asyncio.run(main_language())
