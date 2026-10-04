"""通过 Ninna MCP 运行五分钟 VAD 数据验收；证据与请求身份可恢复。"""

from __future__ import annotations
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import time

import httpx
import typer
import yaml
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

app = typer.Typer(pretty_exceptions_enable=False)
ROOT = Path(__file__).resolve().parents[1]


async def exercise(api, data, evidence_path, request_prefix="vad-ava-5min-v1"):
    state = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    identity = {
        "api": api.rstrip("/"),
        "data": str(data.resolve()),
        "request_prefix": request_prefix,
        "recipes": {
            name: hashlib.sha256((ROOT / "examples/vad" / name).read_bytes()).hexdigest()
            for name in ["train.yaml", "evaluate-test.yaml"]
        },
    }
    if state.get("identity", identity) != identity:
        raise ValueError("恢复参数或配方已改变；新实验请更换 --request-prefix 和 --evidence")
    state["identity"] = identity
    evidence_path.parent.mkdir(parents=True, exist_ok=True)

    def save():
        evidence_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    async with streamable_http_client(api.rstrip("/") + "/mcp/") as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            await session.read_resource("ninna://guide")

            async def call(tool_name, **params):
                r = await session.call_tool(tool_name, params)
                if r.isError:
                    raise RuntimeError(f"{tool_name}: {r.content}")
                return r.structuredContent or json.loads(r.content[0].text)

            async def once(key, name, **params):
                if key not in state:
                    state[key] = await call(name, **params)
                    save()
                return state[key]

            def mutation(key, **params):
                return dict(request_id=request_prefix + ":" + key, **params)

            async def job(value):
                deadline = time.monotonic() + 1800
                while time.monotonic() < deadline:
                    j = await call("get_job", job_id=value["id"])
                    if j["status"] in ["SUCCESS", "FAILED", "CANCELLED"]:
                        if j["status"] != "SUCCESS":
                            state["failed_job"] = j
                            save()
                            raise RuntimeError(j)
                        return j["result"]
                    await asyncio.sleep(3)
                raise TimeoutError(value["id"])

            state["capabilities"] = await call("get_capabilities")
            if "project" not in state:
                projects = (await call("list_projects"))["projects"]
                state["project"] = next((p for p in projects if p["id"] == "vad-ava-energy"), None)
                if not state["project"]:
                    state["project"] = await call(
                        "create_project",
                        name="vad-ava-energy",
                        description="AVA 10h/2h 五分钟切片、能量粗标注与真实容器运行",
                    )
                save()
            await call("list_work_items", project_id=state["project"]["id"])
            envs = (await call("list_environments"))["items"]
            env = next(
                e
                for e in envs
                if e.get("workspace_name") == "preludio2-main-v4" and e.get("latest_revision_id")
            )
            state["environment_revision_id"] = env["latest_revision_id"]
            work = await once(
                "work",
                "create_work_item",
                request=mutation(
                    "work",
                    project_id=state["project"]["id"],
                    title="AVA 五分钟音频：AudioFolder/Parquet 训练验证",
                    goal="完整训练 2h 子集的一轮训练 split，验证两种格式和独立 test split，记录真实参数更新与产物。",
                    constraints="每条 300 秒；能量粗标注不是人工真值；CPU；固定 split；不限制样本数。",
                    environment_revision_id=env["latest_revision_id"],
                ),
            )
            for _ in range(120):
                context = await call("get_work_context", work_item_id=work["id"])
                if context["work_item"]["ready"]:
                    break
                await asyncio.sleep(3)
            else:
                raise TimeoutError("workspace not ready")
            for form in ["2h", "2h-parquet"]:
                acquired = await once(
                    form + ":job",
                    "acquire_asset",
                    request=mutation(
                        form + ":acquire",
                        kind="dataset",
                        name="vad-ava-energy-v1-" + form,
                        local_path=str((data / form).resolve()),
                    ),
                )
                asset = await job(acquired)
                state[form + ":asset"] = asset
                save()
                asset_id = asset.get("asset_id", asset.get("id"))
                await once(
                    form + ":binding",
                    "bind_asset",
                    asset_id=asset_id,
                    request=mutation(
                        form + ":bind",
                        metadata={
                            "train_split": {"name": "train"},
                            "test_split": {"name": "test"},
                            "validation_split": {"name": "validation"},
                            "annotation_status": "unreviewed",
                            "clip_seconds": 300,
                        },
                    ),
                )
                inspected = await call("inspect_asset_revision", asset_id=asset_id, verify=True)
                state[form + ":inspection"] = inspected
                save()
            assets = (await call("list_asset_revisions", kind="model"))["items"]
            model = next(
                a
                for a in assets
                if a.get("legacy_ref") == {"name": "attetion-config", "version": "smoke-v1"}
            )
            state["model_asset_id"] = model["id"]
            # Validate standard HF loader and exact decode length inside managed image.
            paths = [state[f + ":inspection"]["command_path"] for f in ["2h", "2h-parquet"]]
            code = (
                "import datasets,json; from datasets import load_dataset; print('datasets',datasets.__version__); paths="
                + repr(paths)
                + ";\nfor p in paths:\n for s,n in [('train',20),('validation',2),('test',2)]:\n  d=load_dataset(p,split=s); assert len(d)==n; a=d[0]['audio']; v=a.get_all_samples() if hasattr(a,'get_all_samples') else None; count=v.data.shape[-1] if v is not None else len(a['array']); assert count==4800000; print(json.dumps({'path':p,'split':s,'rows':len(d),'samples':count}))"
            )
            cmd = await once(
                "loader_job",
                "execute_task_command",
                owner_id=work["id"],
                request=mutation("loader", argv=["python", "-c", code]),
            )
            await job(cmd)
            state["loader_log"] = await call("read_job_logs", job_id=cmd["id"])
            save()
            for operation in ["train", "evaluate"]:
                config = yaml.safe_load(
                    (
                        ROOT
                        / "examples/vad"
                        / ("train.yaml" if operation == "train" else "evaluate-test.yaml")
                    ).read_text()
                )
                recipe = {
                    "name": "vad-ava-energy-" + operation,
                    "version": "v2",
                    "framework": {"name": "preludio2", "version": "ninna-v1"},
                    "task": "attetion-vad",
                    "operation": operation,
                    "config": config,
                    "metadata": {"label_quality": "energy-unreviewed", "clip_seconds": 300},
                }
                await once(
                    operation + ":v2:recipe",
                    "register_asset",
                    kind="recipe",
                    asset=recipe,
                )
            for label, form, operation in [
                ("audiofolder-train-locked", "2h", "train"),
                ("parquet-train-locked", "2h-parquet", "train"),
                ("test-evaluate-final", "2h-parquet", "evaluate"),
            ]:
                asset = state[form + ":asset"]
                params = dict(
                    work_item_id=work["id"],
                    task="attetion-vad",
                    operation=operation,
                    inputs={
                        "dataset": asset.get("asset_id", asset.get("id")),
                        "model": model["id"],
                    },
                    recipe={
                        "name": "vad-ava-energy-" + operation,
                        "version": "v2",
                    },
                    resources={"device": "cpu", "cpu_threads": 4, "memory_mb": 16384},
                )
                if operation == "evaluate":
                    params.update(
                        source_run_id=state["parquet-train-locked:submission"]["run_id"],
                        source_path="checkpoints/last.ckpt",
                    )
                plan = await once(
                    label + ":plan", "prepare_run_plan", request=mutation(label + ":plan", **params)
                )
                for _ in range(120):
                    p = await call("read_run_plan", plan_id=plan["id"])
                    if p["status"] in ["READY", "BLOCKED"]:
                        break
                    await asyncio.sleep(3)
                if p["status"] != "READY":
                    raise RuntimeError(p)
                submitted = await once(
                    label + ":submit_job",
                    "submit_run",
                    request=mutation(label + ":submit", plan_id=p["id"]),
                )
                state[label + ":submission"] = await job(submitted)
                save()
                run_id = state[label + ":submission"]["run_id"]
                print(label, run_id, flush=True)
                deadline = time.monotonic() + 3600
                while time.monotonic() < deadline:
                    run = await call("get_run", run_id=run_id)
                    if run["status"] in ["SUCCESS", "FAILED", "CANCELLED"]:
                        break
                    await asyncio.sleep(5)
                state[label + ":run"] = run
                state[label + ":artifacts"] = await call("list_run_artifacts", run_id=run_id)
                save()
                if run["status"] != "SUCCESS":
                    raise RuntimeError(run)
                assert run["container_id"] and run["exit_code"] == 0
                assert all(
                    math.isfinite(v) for v in run["metrics"].values() if isinstance(v, (int, float))
                )
                artifact = next(
                    a
                    for a in state[label + ":artifacts"]["items"]
                    if a["name"].endswith("resolved.yaml")
                )
                async with httpx.AsyncClient(timeout=120) as http:
                    response = await http.get(api.rstrip("/") + artifact["download_path"])
                    response.raise_for_status()
                resolved = yaml.safe_load(response.text)
                assert resolved["model"]["init_args"]["threshold"] == 0.5
                assert resolved["model"]["init_args"]["threshold_sweep"] == [0.5]
                if operation == "evaluate":
                    assert resolved["data"]["init_args"]["validation_split"] == "test"
                state[label + ":resolved"] = resolved
                save()
                result = run["metadata"]["result"]
                if operation == "train":
                    proof = result["evidence"]
                    assert proof["optimizer_steps"] == proof["global_step"] == 20
                    assert proof["initial_trainable_hash"] != proof["final_trainable_hash"]
                    paths = {a["path"] for a in result["artifacts"]}
                    assert "checkpoints/last.ckpt" in paths
                    assert any(p.endswith("resolved.yaml") for p in paths)
                else:
                    assert run["metrics"]["val_best_threshold"] == 0.5
                    assert run["metrics"]["val_best_f1"] == run["metrics"]["val_f1"]
                print(label, run["status"], run.get("metrics"), flush=True)
            context = await call("get_work_context", work_item_id=work["id"])
            state["completion"] = await once(
                "completion-final",
                "update_work_item",
                work_item_id=work["id"],
                request=mutation(
                    "complete-final",
                    expected_version=context["work_item"]["version"],
                    status="COMPLETED",
                    summary="10h/2h 数据严格 300 秒；AudioFolder 与内嵌 WAV Parquet 一致。两种格式完成一轮全量训练 split，并独立评估 test。指标仅相对能量粗标注。",
                    next_step="人工修标创建新数据版本，再进行正式质量评估。",
                ),
            )
            save()


@app.command()
def main(
    api: str = typer.Option("http://127.0.0.1:8021", envvar="NINNA_API_URL"),
    data: Path = typer.Option(ROOT / "data-bin/vad-ava-energy-v1"),
    evidence: Path = typer.Option(ROOT / "outputs/vad-ava-energy-v1/evidence.json"),
    request_prefix: str = typer.Option("vad-ava-5min-v1", help="新实验须更换请求前缀及证据文件"),
):
    if os.environ.get("NINNA_INTEGRATION") != "1":
        raise typer.BadParameter("Set NINNA_INTEGRATION=1 for real Docker execution")
    try:
        asyncio.run(exercise(api, data, evidence, request_prefix))
    except Exception as exc:
        # Python 3.10's default traceback hides MCP task-group leaf errors.
        pending = [exc]
        while pending:
            error = pending.pop()
            children = getattr(error, "exceptions", ())
            if children:
                pending.extend(reversed(children))
            else:
                typer.echo(f"{type(error).__name__}: {error}", err=True)
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
