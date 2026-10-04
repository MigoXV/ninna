"""Current workflow acceptance: official HTTP/stdio MCP clients and real Docker."""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def test_codex_workflow_and_stdio_reconnection():
    api = os.environ.get("NINNA_API_URL", "http://127.0.0.1:8021")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate-work-v2.py")],
        cwd=ROOT,
        env={**os.environ, "NINNA_API_URL": api},
        check=True,
        timeout=1200,
    )
    evidence = json.loads((ROOT / "outputs/work-v2-validation/evidence.json").read_text())

    async def reconnect():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "ninna.commands.app", "mcp", "--url", api]
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_work_context", {"work_item_id": evidence["work_item_id"]}
                )
                assert not result.isError
                assert len(result.structuredContent["runs"]) == 3
                assert {r["status"] for r in result.structuredContent["runs"]} == {
                    "SUCCESS",
                    "FAILED",
                }

    asyncio.run(reconnect())
