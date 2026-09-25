"""Official MCP clients -> live platform -> real Docker training, without mocks."""

import asyncio
import copy
import os
import sys
import time
import uuid

import docker
import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from ninna.services.certification import default_request

pytestmark = pytest.mark.integration
API = os.environ.get("NINNA_API_URL", "http://127.0.0.1:8000").rstrip("/")


async def invoke(session, name, **arguments):
    result = await session.call_tool(name, arguments)
    assert not result.isError, result
    assert result.structuredContent is not None, result
    return result.structuredContent


async def wait(session, run_id):
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        run = await invoke(session, "get_run", run_id=run_id)
        if run["status"] in {"SUCCESS", "FAILED", "CANCELLED"}:
            return run
        await asyncio.sleep(2)
    pytest.fail(f"Run did not finish: {run_id}")


def test_http_create_stdio_observe_and_real_docker_artifacts():
    async def exercise():
        async with streamable_http_client(API + "/mcp/") as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                assets = await invoke(session, "list_assets", kind="dataset")
                assert any(a["name"] == "mnist" and a["version"] == "v2" for a in assets["items"])
                model = await invoke(
                    session,
                    "describe_asset",
                    kind="model",
                    ref={"name": "mnist-cnn", "version": "v2"},
                )
                assert "Safetensors" in model["documentation"]
                run = await invoke(session, "create_run", **default_request(version="quick-v1"))
        # The creator has disconnected. A separate stdio process observes the same run.
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "ninna.commands.app", "mcp", "--url", API]
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                completed = await wait(session, run["id"])
                assert completed["status"] == "SUCCESS", completed["failure_reason"]
                assert completed["exit_code"] == 0
                meta = completed["metadata"]
                assert meta["initial_model_hash"] != meta["trained_model_hash"]
                metrics = await invoke(session, "get_run_metrics", run_id=run["id"])
                assert metrics["final"]["test_accuracy"] > 0.95
                assert metrics["final"]["final_loss"] < metrics["final"]["initial_loss"]
                logs = await invoke(session, "read_run_logs", run_id=run["id"])
                assert logs["content"] and logs["offset"] > 0
                artifacts = await invoke(session, "list_run_artifacts", run_id=run["id"])
                checkpoint = next(a for a in artifacts["items"] if a["name"] == "checkpoint.pt")
                async with httpx.AsyncClient(base_url=API) as client:
                    response = await client.get(checkpoint["download_path"])
                    assert response.status_code == 200 and len(response.content) > 10000
                container = docker.from_env().containers.get(completed["container_id"])
                assert container.attrs["Config"]["Labels"]["ninna.run_id"] == run["id"]
                mounts = {m["Destination"]: m for m in container.attrs["Mounts"]}
                assert not mounts["/dataset"]["RW"] and not mounts["/workspace"]["RW"]
                assert mounts["/output"]["RW"]
                print(
                    f"MCP SUCCESS {run['id']} {completed['container_id']} accuracy={metrics['final']['test_accuracy']}"
                )

    asyncio.run(exercise())


def test_mcp_failure_diagnostic_and_new_run_retry():
    async def exercise():
        async with streamable_http_client(API + "/mcp/") as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                recipe = (
                    await invoke(
                        session,
                        "describe_asset",
                        kind="recipe",
                        ref={"name": "mnist-adam", "version": "quick-v1"},
                    )
                )["asset"]
                bad = {
                    **recipe,
                    "name": "mcp-bad-" + uuid.uuid4().hex[:8],
                    "optimizer": {"name": "Adam", "params": {"lr": -1}},
                }
                bad.pop("id")
                await invoke(session, "register_asset", kind="recipe", asset=bad)
                spec = default_request(version="quick-v1")
                spec["training_spec"]["recipe"] = {"name": bad["name"], "version": bad["version"]}
                failed = await wait(session, (await invoke(session, "create_run", **spec))["id"])
                assert failed["status"] == "FAILED" and failed["exit_code"] != 0
                context = await invoke(session, "get_run_diagnostic_context", run_id=failed["id"])
                assert "Invalid learning rate" in context["stderr"]
                assert context["container_id"] and context["assets"]["workspace"]["snapshot"]
                request = default_request(version="quick-v1")
                request["execution_spec"] = copy.deepcopy(failed["execution_spec"])
                request["parent_run_id"] = failed["id"]
                retried = await wait(
                    session, (await invoke(session, "create_run", **request))["id"]
                )
                assert retried["status"] == "SUCCESS", retried["failure_reason"]
                assert retried["parent_run_id"] == failed["id"]
                assert (await invoke(session, "get_run", run_id=failed["id"])) == failed
                print(f"MCP FAILED {failed['id']} -> new SUCCESS {retried['id']}")

    asyncio.run(exercise())
