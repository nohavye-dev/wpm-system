import asyncio
import os
import sys
sys.path.insert(0, "src")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "wpm_mcp_server"],
        env={"WPM_DB_PATH": ".stdio_test.db", "PYTHONPATH": "src"},
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                print("TOOLS:", [t.name for t in tools.tools])

                store_result = await session.call_tool(
                    "store_entry",
                    {
                        "type": "convention",
                        "content": "Use camelCase for JS private fields prefixed with underscore",
                        "source": "official_doc",
                    },
                )
                print("STORE:", store_result.content[0].text)

                query_result = await session.call_tool(
                    "query_context", {"query": "javascript naming convention private fields"}
                )
                print("QUERY:", query_result.content[0].text[:300])
    finally:
        if os.path.exists(".stdio_test.db"):
            os.remove(".stdio_test.db")


asyncio.run(main())
