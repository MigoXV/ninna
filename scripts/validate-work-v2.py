"""Opt-in real Docker/MCP acceptance in a separate state directory."""

from __future__ import annotations
import asyncio
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
API = os.environ.get("NINNA_API_URL", "http://127.0.0.1:8021")


def seed():
    from ninna.config import Settings
    from ninna.services.platform import Platform

    state = ROOT / "outputs/work-v2-validation/platform"
    p = Platform(Settings(ROOT, Path(os.environ["NINNA_HOST_ROOT"]), state))
    source = sqlite3.connect(f"file:{ROOT}/outputs/platform/ninna.sqlite3?mode=ro", uri=True)
    for kind, body in source.execute("SELECT kind,body FROM assets"):
        value = json.loads(body)
        p.repo.register(kind, value)
    source.close()
    p.work.migrate(True)
    p.close()
    print(json.dumps({"state": str(state)}))


async def exercise():
    evidence = {}
    invocation = str(time.time_ns())
    async with httpx.AsyncClient(base_url=API, timeout=120) as http:
        await http.post(
            "/api/projects", json={"name": "work-v2-acceptance", "description": "独立 v2 验收"}
        )
    async with streamable_http_client(API + "/mcp/") as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()

            async def call(name, **kwargs):
                if "request" in kwargs and "request_id" in kwargs["request"]:
                    kwargs["request"] = {
                        **kwargs["request"],
                        "request_id": invocation + ":" + kwargs["request"]["request_id"],
                    }
                result = await session.call_tool(name, kwargs)
                if result.isError:
                    raise RuntimeError(str(result.content))
                return result.structuredContent

            async def wait_job(job_id, expected="SUCCESS"):
                deadline = time.monotonic() + 600
                while time.monotonic() < deadline:
                    value = await call("get_job", job_id=job_id)
                    if value["status"] in {"SUCCESS", "FAILED", "CANCELLED"}:
                        assert value["status"] == expected, value
                        return value["result"]
                    await asyncio.sleep(1)
                raise TimeoutError(job_id)

            envs = (await call("list_environments"))["items"]
            env = next(e for e in envs if e.get("workspace_name") == "demo-mnist-main-v3")
            await wait_job(
                (
                    await call(
                        "prepare_environment",
                        environment_id=env["id"],
                        request={"request_id": "acceptance:prepare"},
                    )
                )["id"]
            )
            command = await call(
                "execute_task_command",
                owner_id=env["id"],
                request={
                    "request_id": "acceptance:command",
                    "argv": ["python", "-c", "import torch; print(torch.__version__)"],
                },
            )
            await wait_job(command["id"])
            evidence["preparation_log"] = await call("read_job_logs", job_id=command["id"])
            revision = await wait_job(
                (
                    await call(
                        "publish_environment",
                        environment_id=env["id"],
                        request={"request_id": "acceptance:publish"},
                    )
                )["id"]
            )
            evidence["environment_revision"] = revision
            work = await call(
                "create_work_item",
                request={
                    "request_id": "acceptance:work",
                    "project_id": "work-v2-acceptance",
                    "title": "Codex 远端训练闭环",
                    "goal": "准备环境，运行小规模图像分类训练，保留证据",
                    "environment_revision_id": revision["id"],
                },
            )
            evidence["work_item_id"] = work["id"]
            for _ in range(180):
                context = await call("get_work_context", work_item_id=work["id"])
                if context["work_item"]["ready"]:
                    break
                await asyncio.sleep(1)
            assert context["work_item"]["ready"], context
            for label, argv, timeout in (
                ("failure", ["python", "-c", "raise RuntimeError('acceptance failure')"], 30),
                ("timeout", ["python", "-c", "import time; time.sleep(30)"], 1),
            ):
                failed = await call(
                    "execute_task_command",
                    owner_id=work["id"],
                    request={
                        "request_id": "acceptance:" + label,
                        "argv": argv,
                        "timeout_seconds": timeout,
                    },
                )
                evidence[label] = await wait_job(failed["id"], "FAILED")
            cancel = await call(
                "execute_task_command",
                owner_id=work["id"],
                request={
                    "request_id": "acceptance:cancel-command",
                    "argv": [
                        "python",
                        "-c",
                        "import time; print('started',flush=True); time.sleep(120)",
                    ],
                },
            )
            for _ in range(60):
                log = await call("read_job_logs", job_id=cancel["id"])
                if "started" in log["content"]:
                    break
                await asyncio.sleep(1)
            await call(
                "cancel_job", job_id=cancel["id"], request={"request_id": "acceptance:cancel"}
            )
            evidence["cancel"] = await wait_job(cancel["id"], "CANCELLED")
            command = await call(
                "execute_task_command",
                owner_id=work["id"],
                request={
                    "request_id": "acceptance:task-command",
                    "argv": [
                        "python",
                        "-c",
                        "from pathlib import Path; Path('acceptance.txt').write_text('workspace preserved'); print('prepared')",
                    ],
                },
            )
            await wait_job(command["id"])
            files = await call(
                "read_task_files", owner_id=work["id"], relative_path="acceptance.txt"
            )
            assert files["content"] == "workspace preserved"
            await call(
                "edit_task_file",
                owner_id=work["id"],
                request={
                    "request_id": "acceptance:edit",
                    "path": "acceptance.txt",
                    "content": "remote edit preserved",
                    "expected_sha256": files["sha256"],
                },
            )
            assets = (await call("list_asset_revisions"))["items"]
            dataset = next(
                a for a in assets if a.get("legacy_ref") == {"name": "mnist", "version": "smoke-v1"}
            )
            model = next(
                a
                for a in assets
                if a.get("legacy_ref") == {"name": "mnist-config", "version": "smoke-v1"}
            )
            spec = {
                "request_id": "acceptance:plan",
                "work_item_id": work["id"],
                "task": "classification",
                "operation": "train",
                "inputs": {"dataset": dataset["id"], "model": model["id"]},
                "recipe": {
                    "name": "demo-mnist-classification-scratch-train",
                    "version": "ninna-v3",
                },
                "resources": {"device": "cpu", "cpu_threads": 2, "memory_mb": 4096},
            }
            runner = await call(
                "read_task_files", owner_id=work["id"], relative_path=revision["entrypoint"]
            )
            for index in range(3):
                if index in {1, 2}:
                    current = await call(
                        "read_task_files", owner_id=work["id"], relative_path=revision["entrypoint"]
                    )
                    await call(
                        "edit_task_file",
                        owner_id=work["id"],
                        request={
                            "request_id": f"acceptance:runner:{index}",
                            "path": revision["entrypoint"],
                            "expected_sha256": current["sha256"],
                            "content": "raise RuntimeError('acceptance injected failure')\n"
                            if index == 1
                            else runner["content"],
                        },
                    )
                if index == 2:
                    spec["parent_run_id"] = evidence["run_1"]["id"]
                plan = await call(
                    "prepare_run_plan", request={**spec, "request_id": f"acceptance:plan:{index}"}
                )
                for _ in range(180):
                    plan = await call("read_run_plan", plan_id=plan["id"])
                    if plan["status"] in {"READY", "BLOCKED"}:
                        break
                    await asyncio.sleep(1)
                assert plan["status"] == "READY", plan
                request = {"request_id": f"acceptance:submit:{index}", "plan_id": plan["id"]}
                first = await call("submit_run", request=request)
                second = await call("submit_run", request=request)
                assert first["id"] == second["id"]
                submitted = await wait_job(first["id"])
                run_id = submitted["run_id"]
                for _ in range(300):
                    run = await call("get_run", run_id=run_id)
                    if run["status"] in {"SUCCESS", "FAILED", "CANCELLED"}:
                        break
                    await asyncio.sleep(1)
                assert run["status"] == ("FAILED" if index == 1 else "SUCCESS"), run.get(
                    "failure_reason"
                )
                evidence[f"run_{index}"] = {
                    k: run[k]
                    for k in (
                        "id",
                        "container_id",
                        "status",
                        "exit_code",
                        "metrics",
                        "metadata",
                        "artifacts",
                    )
                }
                print(json.dumps({"run_id": run_id, "status": run["status"]}), flush=True)
            # New tasks clone the published baseline, never another task's mutable code.
            sibling = await call(
                "create_work_item",
                request={
                    "request_id": "acceptance:isolated",
                    "project_id": work["project_id"],
                    "title": "独立工作区验证",
                    "goal": "验证任务间文件隔离",
                    "environment_revision_id": revision["id"],
                },
            )
            for _ in range(180):
                if (await call("get_work_context", work_item_id=sibling["id"]))["work_item"][
                    "ready"
                ]:
                    break
                await asyncio.sleep(1)
            sibling_files = await call("read_task_files", owner_id=sibling["id"])
            assert "acceptance.txt" not in sibling_files["files"]
            evidence["isolated_work_item"] = sibling["id"]
            await call(
                "set_workspace_state",
                owner_id=sibling["id"],
                action="stop",
                request={"request_id": "acceptance:stop-sibling"},
            )
            await call(
                "set_workspace_state",
                owner_id=work["id"],
                action="stop",
                request={"request_id": "acceptance:stop"},
            )
            await call(
                "set_workspace_state",
                owner_id=work["id"],
                action="start",
                request={"request_id": "acceptance:start"},
            )
            assert (
                await call("read_task_files", owner_id=work["id"], relative_path="acceptance.txt")
            )["content"] == "remote edit preserved"
    # A new MCP connection recovers the same context without sharing files with the server.
    async with streamable_http_client(API + "/mcp/") as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_work_context", {"work_item_id": evidence["work_item_id"]}
            )
            assert len(result.structuredContent["runs"]) == 3
            evidence["reconnected"] = True
    target = ROOT / "outputs/work-v2-validation/evidence.json"
    target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    print(str(target))


if __name__ == "__main__":
    if os.environ.get("NINNA_INTEGRATION") != "1":
        raise SystemExit("Set NINNA_INTEGRATION=1 for real Docker acceptance")
    if "--seed" in sys.argv:
        seed()
    else:
        asyncio.run(exercise())
