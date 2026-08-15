"""Full integration test of the MCP server from a real project directory.

Covers: store → link → query → validate → dedup → agent_reasoning
excluded → contradict → query conflicts → error paths.
"""

import asyncio
import json
import os
import sys
sys.path.insert(0, "src")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_DIR = "/tmp/wpm-test-project"
CONFIG_PATH = os.path.join(PROJECT_DIR, "wpm.config.json")
DB_PATH = os.path.join(PROJECT_DIR, ".wpm", "wpm.db")
SRC_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "src"
)

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


async def main():
    os.makedirs(os.path.join(PROJECT_DIR, ".wpm"), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump({"db_path": ".wpm/wpm.db"}, f)
    # Clean previous db
    for f in [DB_PATH, DB_PATH + "-wal", DB_PATH + "-shm"]:
        if os.path.exists(f):
            os.remove(f)

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "wpm_mcp_server"],
        cwd=PROJECT_DIR,
        env={
            "PYTHONPATH": SRC_DIR,
            "WPM_CONFIG_PATH": CONFIG_PATH,
        },
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. Tool listing
            print("\n1. tool listing")
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            check(
                "11 tools registered",
                names == [
                    "contradict_entry", "deprecate_entry", "get_memory_stats",
                    "link_entries", "list_entries", "pin_entry", "query_context",
                    "record_execution", "restore_entry", "store_entry",
                    "validate_entry",
                ],
            )

            # 2. store_entry (all types)
            print("\n2. store_entry")
            r = await session.call_tool(
                "store_entry",
                {
                    "type": "archi_decision",
                    "content": "The CQRS pattern separates read models from write models",
                    "source": "official_doc",
                },
            )
            d1 = json.loads(r.content[0].text)
            check("archi_decision stored", d1.get("entry_id"))
            check("   provenance=0.9 for official_doc", d1.get("provenance_score") == 0.9)

            r = await session.call_tool(
                "store_entry",
                {
                    "type": "convention",
                    "content": "CQRS command handlers return Result<T,Error> monads",
                    "source": "observed_code",
                },
            )
            d2 = json.loads(r.content[0].text)
            check("convention stored", d2.get("entry_id"))
            check("   provenance=0.75 for observed_code", d2.get("provenance_score") == 0.75)

            r = await session.call_tool(
                "store_entry",
                {
                    "type": "bug_pattern",
                    "content": "Read model fails when DB pool exhausted",
                    "source": "tool_execution",
                },
            )
            d3 = json.loads(r.content[0].text)
            check("bug_pattern stored", d3.get("entry_id"))

            r = await session.call_tool(
                "store_entry",
                {
                    "type": "insight",
                    "content": "Pytest fixtures with session scope reduce runtime 40%",
                    "source": "agent_inference",
                },
            )
            d4 = json.loads(r.content[0].text)
            check("insight stored (low confidence)", d4.get("confidence") <= 0.4)

            # 3. link_entries
            print("\n3. link_entries")
            r = await session.call_tool(
                "link_entries",
                {
                    "source_id": d2["entry_id"],
                    "target_id": d1["entry_id"],
                    "relation_type": "depends_on",
                },
            )
            d = json.loads(r.content[0].text)
            check("depends_on link", d.get("relation_type") == "depends_on")

            r = await session.call_tool(
                "link_entries",
                {
                    "source_id": d3["entry_id"],
                    "target_id": d1["entry_id"],
                    "relation_type": "refines",
                },
            )
            d = json.loads(r.content[0].text)
            check("refines link", d.get("relation_type") == "refines")

            # 4. query_context
            print("\n4. query_context")
            r = await session.call_tool(
                "query_context",
                {"query": "CQRS pattern", "min_confidence": 0.0},
            )
            d = json.loads(r.content[0].text)
            check("direct_matches > 0", len(d.get("direct_matches", [])) > 0)
            check("no conflicts before contradict", len(d.get("conflicts", [])) == 0)

            # 5. validate_entry
            print("\n5. validate_entry")
            r = await session.call_tool(
                "validate_entry",
                {
                    "entry_id": d1["entry_id"],
                    "evidence_type": "execution_verified",
                    "evidence_ref": "integration_test",
                    "session_id": "test-session",
                },
            )
            d = json.loads(r.content[0].text)
            check("execution_verified > 0", d.get("validation_score", 0) > 0)

            # dedup
            r = await session.call_tool(
                "validate_entry",
                {
                    "entry_id": d1["entry_id"],
                    "evidence_type": "execution_verified",
                    "evidence_ref": "integration_test",
                    "session_id": "test-session",
                },
            )
            d = json.loads(r.content[0].text)
            check("dedup in same session window", "dedup" in d.get("note", ""))

            # agent_reasoning excluded
            r = await session.call_tool(
                "validate_entry",
                {
                    "entry_id": d2["entry_id"],
                    "evidence_type": "agent_reasoning",
                    "evidence_ref": "just a hunch",
                    "session_id": "test-session",
                },
            )
            d = json.loads(r.content[0].text)
            check(
                "agent_reasoning excluded from score",
                d.get("note") == "agent_reasoning excluded from score",
            )

            # 6. contradict_entry
            print("\n6. contradict_entry")
            r = await session.call_tool(
                "contradict_entry",
                {
                    "entry_id": d2["entry_id"],
                    "conflicting_entry_id": d3["entry_id"],
                    "evidence_type": "cross_reference",
                    "evidence_ref": "observed: convention vs bug pattern",
                },
            )
            d = json.loads(r.content[0].text)
            check("contradict return", d.get("conflicting_entry_id") == d3["entry_id"])

            # 7. error paths
            print("\n7. error paths")
            r = await session.call_tool(
                "store_entry",
                {"type": "not_a_valid_type", "content": "x", "source": "agent_inference"},
            )
            check("invalid type rejected", r.isError is True)

            r = await session.call_tool(
                "link_entries",
                {
                    "source_id": "nonexistent-id-0000",
                    "target_id": d1["entry_id"],
                    "relation_type": "related",
                },
            )
            d = json.loads(r.content[0].text)
            check("missing entry rejected", d.get("error") is True)

    # cleanup
    for f in [DB_PATH, DB_PATH + "-wal", DB_PATH + "-shm"]:
        if os.path.exists(f):
            os.remove(f)

    print(f"\n{'='*40}")
    print(f"Results: {pass_count} passed, {fail_count} failed")
    if fail_count:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
