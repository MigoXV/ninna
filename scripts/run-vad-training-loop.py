"""真实 MCP/Docker AVA 训练闭环：固定数据、配方与可恢复请求身份。"""

from __future__ import annotations
import asyncio
import hashlib
import json
import math
import os
import sys
from pathlib import Path
import time
import httpx
import typer
import yaml
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
app = typer.Typer(pretty_exceptions_enable=False)


async def exercise(api, evidence_path, framework_source, publish, version):
    state = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    recipes = ROOT / "examples/vad-human"
    files = [
        "integrations/ninna/prepare.py",
        "integrations/ninna/prepare_ava.py",
        "integrations/ninna/callbacks.py",
        ".agents/skills/preludio2-training/SKILL.md",
        "src/preludio2/datasets/vad.py",
    ]
    identity = {
        "api": api,
        "version": version,
        "framework_manifest_sha256": hashlib.sha256(
            (framework_source / "ninna-framework.yaml").read_bytes()
        ).hexdigest(),
        "recipes": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in recipes.glob("*.yaml")
        },
        "bridge": {
            p: hashlib.sha256((framework_source / p).read_bytes()).hexdigest() for p in files
        },
    }
    if state.get("identity", identity) != identity:
        raise ValueError("恢复时配置或代码已变；新实验需新证据和请求身份")
    state["identity"] = identity

    def save():
        temporary = evidence_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        temporary.replace(evidence_path)

    save()
    async with streamable_http_client(api + "/mcp/") as (reader, writer, _):
        async with ClientSession(reader, writer) as s:
            await s.initialize()
            await s.read_resource("ninna://guide")

            async def call(name, **args):
                r = await s.call_tool(name, args)
                if r.isError:
                    raise RuntimeError(f"{name}: {r.content}")
                return r.structuredContent

            async def once(key, name, **args):
                if key not in state:
                    state[key] = await call(name, **args)
                    save()
                    print(key, state[key].get("id"), flush=True)
                return state[key]

            def req(key, **args):
                return {"request_id": "vad-human-loop-" + version + ":" + key, **args}

            async def wait_job(value):
                deadline = time.monotonic() + 7200
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

            if "source" not in state:
                await once(
                    "source",
                    "configure_source",
                    request=req(
                        "source",
                        name="Hugging Face MigoXV",
                        endpoint="https://huggingface.co",
                        token_env="HF_TOKEN",
                    ),
                )
            if "project" not in state:
                projects = (await call("list_projects"))["projects"]
                existing = next((p for p in projects if p["id"] == "vad-human-training-loop"), None)
                if existing:
                    state["project"] = existing
                    save()
                else:
                    await once(
                        "project",
                        "create_project",
                        name="vad-human-training-loop",
                        description="人工 AVA：Scratch / Full / LoRA 真实 MCP 闭环",
                    )
            if "work" not in state:
                environments = (
                    await call(
                        "list_environments", query="preludio2-ava-human-v2", published_only=True
                    )
                )["items"]
                environment = next(
                    (
                        e
                        for e in environments
                        if e.get("name") == "preludio2-ava-human-v2" and e.get("latest_revision_id")
                    ),
                    None,
                )
                if environment is None:
                    raise ValueError(
                        "缺少已发布的 preludio2-ava-human-v2 环境；请按固定环境准备流程发布后再训练"
                    )
                await once(
                    "work",
                    "create_work_item",
                    request=req(
                        "work",
                        project_id=state["project"]["id"],
                        title="AVA 人工标注训练闭环",
                        goal="固定配方从零训练基线，再分别全量和 LoRA 微调，独立测试与重新加载推理。",
                        environment_revision_id=environment["latest_revision_id"],
                    ),
                )
            while not (await call("get_work_context", work_item_id=state["work"]["id"]))[
                "work_item"
            ]["ready"]:
                await asyncio.sleep(3)
            if "raw" not in state:
                acquisition = await once(
                    "raw_job",
                    "acquire_asset",
                    request=req(
                        "raw",
                        kind="dataset",
                        name="AVA human original FLAC",
                        source_id=state["source"]["id"],
                        repo_id="MigoXV/vad-human-ava-speech",
                        revision="ee5e35d06a268fe051d3cf8c6672c42c05e60887",
                    ),
                )
                state["raw"] = await wait_job(acquisition)
                save()

            work = state["work"]["id"]
            framework_ref = (await call("get_work_context", work_item_id=work))["work_item"][
                "framework"
            ]
            listing = await call("read_task_files", owner_id=work)
            existing_files = set(listing["files"])
            for path in files:
                if "edit:" + path in state:
                    continue
                if path not in existing_files:
                    current = {}
                else:
                    current = await call("read_task_files", owner_id=work, relative_path=path)
                content = (framework_source / path).read_text()
                if current.get("sha256") == hashlib.sha256(content.encode()).hexdigest():
                    state["edit:" + path] = {
                        "path": path,
                        "sha256": current["sha256"],
                        "unchanged": True,
                    }
                    save()
                    continue
                await once(
                    "edit:" + path,
                    "edit_task_file",
                    owner_id=work,
                    request=req(
                        "edit:" + path,
                        path=path,
                        content=content,
                        expected_sha256=current.get("sha256"),
                    ),
                )
            await once(
                "raw_binding",
                "bind_asset",
                asset_id=state["raw"]["id"],
                request=req(
                    "raw-bind",
                    metadata={"train_split": {"name": "train"}, "test_split": {"name": "test"}},
                ),
            )

            async def recipe(mode, operation):
                asset = {
                    "name": "vad-human-" + mode,
                    "version": version,
                    "framework": framework_ref,
                    "task": "attetion-vad",
                    "operation": operation,
                    "config": yaml.safe_load((recipes / (mode + ".yaml")).read_text()),
                    "metadata": {"label_quality": "human", "training_method": mode},
                }
                await once("recipe:" + mode, "register_asset", kind="recipe", asset=asset)
                return {"name": asset["name"], "version": asset["version"]}

            async def run(label, mode, operation, inputs, source=None, cpu=False):
                if state.get(label + ":run", {}).get("status") == "SUCCESS":
                    recorded = await call("get_run", run_id=state[label + ":run"]["id"])
                    assert recorded["status"] == "SUCCESS"
                    return recorded
                ref = await recipe(mode, operation)
                params = {
                    "work_item_id": work,
                    "task": "attetion-vad",
                    "operation": operation,
                    "inputs": inputs,
                    "recipe": ref,
                    "resources": {"device": "cpu", "cpu_threads": 4, "memory_mb": 16384}
                    if cpu
                    else {
                        "device": "cuda",
                        "gpu_count": 1,
                        "gpu_ids": [state["gpu_uuid"]],
                        "cpu_threads": 4,
                        "memory_mb": 32768,
                    },
                }
                if source:
                    params.update(
                        source_run_id=source[0], source_path=source[1], parent_run_id=source[0]
                    )
                elif label == "prepare" and state.get("failed_prepare_run"):
                    params["parent_run_id"] = state["failed_prepare_run"]
                elif label == "scratch" and state.get("failed_scratch_run"):
                    params["parent_run_id"] = state["failed_scratch_run"]
                j = await once(label + ":job", "start_run", request=req(label, **params))
                started = await wait_job(j)
                if label + ":run_id" not in state:
                    state[label + ":run_id"] = started["run_id"]
                    save()
                    print(label, "Run", started["run_id"], flush=True)
                # Repeating a successful request must return the same persistent Job.
                replay = await call("start_run", request=req(label, **params))
                assert replay["id"] == j["id"]
                last = time.monotonic()
                deadline = last + 14400
                while time.monotonic() < deadline:
                    r = await call("get_run", run_id=started["run_id"])
                    if time.monotonic() - last > 25:
                        print(label, r["status"], r.get("metrics"), flush=True)
                        last = time.monotonic()
                    if r["status"] in ["SUCCESS", "FAILED", "CANCELLED"]:
                        state[label + ":run"] = r
                        save()
                        if r["status"] != "SUCCESS":
                            state[label + ":diagnostic"] = await call(
                                "get_run_diagnostic_context", run_id=r["id"]
                            )
                            save()
                            raise RuntimeError(f"{label} failed: {r.get('failure_reason')}")
                        break
                    await asyncio.sleep(4)
                else:
                    raise TimeoutError(started["run_id"])
                artifact_list = (await call("list_run_artifacts", run_id=r["id"]))["items"]
                small = {}
                async with httpx.AsyncClient(base_url=api, timeout=120) as http:
                    for item in artifact_list:
                        if item["name"] in [
                            "evidence.json",
                            "metrics.json",
                            "parameter_updates.json",
                            "training/run/resolved.yaml",
                        ]:
                            response = await http.get(item["download_path"])
                            response.raise_for_status()
                            path = evidence_path.parent / label / item["name"]
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_bytes(response.content)
                            if item["name"].endswith(".json"):
                                small[item["name"]] = response.json()
                state[label + ":artifacts"] = artifact_list
                state[label + ":evidence"] = small
                save()
                if operation == "train":
                    e = small["evidence.json"]
                    assert (
                        e["optimizer_steps"] > 0
                        and e["initial_trainable_hash"] != e["final_trainable_hash"]
                    )
                    assert e["frozen_changed_parameter_tensors"] == 0
                    if mode == "lora":
                        assert 0 < e["trainable_parameter_count"] < e["parameter_count"]
                    else:
                        assert e["trainable_parameter_count"] == e["parameter_count"]
                return r

            async def promote(label, r, kind):
                key = label + ":asset"
                if key in state:
                    return state[key]
                asset_version = "ava-human-" + label + "-" + version
                local = (
                    await call("list_asset_revisions", kind=kind, query="preludio2-attetion-vad")
                )["items"]
                found = next(
                    (
                        a
                        for a in local
                        if a.get("legacy_ref")
                        == {"name": "preludio2-attetion-vad", "version": asset_version}
                    ),
                    None,
                )
                if not found:
                    result = await call(
                        "promote_" + kind,
                        run_id=r["id"],
                        version=asset_version,
                        artifact_path="dataset" if kind == "dataset" else "model",
                    )
                    local = (
                        await call("list_asset_revisions", kind=kind, query="preludio2-attetion-vad")
                    )["items"]
                    found = next(
                        a
                        for a in local
                        if a.get("legacy_ref")
                        == {"name": result["name"], "version": result["version"]}
                    )
                assert found.get("source_run_id") == r["id"]
                state[key] = found
                save()
                print(key, found["id"], flush=True)
                return found

            if "gpu_uuid" not in state:
                g = (await call("list_gpus"))["result"]
                gpu = min(g, key=lambda x: x["memory_used_mb"])
                assert gpu["memory_used_mb"] < 1024
                state["gpu_uuid"] = gpu["uuid"]
                save()
            prepared = await run(
                "prepare", "prepare", "prepare", {"dataset": state["raw"]["id"]}, cpu=True
            )
            data = await promote("training-data", prepared, "dataset")
            await once(
                "data_binding",
                "bind_asset",
                asset_id=data["id"],
                request=req(
                    "data-bind",
                    metadata={
                        "train_split": {"name": "train"},
                        "validation_split": {"name": "validation"},
                        "test_split": {"name": "test"},
                        "label_quality": "human",
                    },
                ),
            )
            if publish:
                job = await once(
                    "publish:data:job",
                    "publish_asset_revision",
                    asset_id=data["id"],
                    request=req(
                        "publish-data",
                        source_id=state["source"]["id"],
                        repo_id="MigoXV/vad-human-ava-speech-training",
                        private=False,
                    ),
                )
                state["publish:data"] = await wait_job(job)
                save()
                print("dataset published", state["publish:data"], flush=True)
            model_dir = ROOT / "model-bin/attention-ava-config" / version
            model_dir.mkdir(parents=True, exist_ok=True)
            config = json.loads((recipes / "model-config.json").read_text())
            content = json.dumps(config, indent=2)
            if (
                "config:asset" in state
                and state["config:asset"]["files"]["config.json"]
                != hashlib.sha256(content.encode()).hexdigest()
            ):
                raise ValueError("Scratch 配置与已封存资产不同，请使用新实验")
            (model_dir / "config.json").write_text(content)
            (model_dir / "README.md").write_text(
                "# AVA 从零训练配置\n\n无预训练权重，attention_vad 128 维、3 层，dropout 0.1。\n"
            )
            if "config:asset" not in state:
                # 使用既有流式上传 CLI，客户端无需与 Ninna 共享文件系统。
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "ninna.commands.app",
                    "upload",
                    "--path",
                    str(model_dir),
                    "--kind",
                    "model",
                    "--name",
                    "AVA scratch config",
                    "--request-id",
                    req("config-upload")["request_id"],
                    "--url",
                    api,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()
                if process.returncode:
                    raise RuntimeError("Scratch config upload failed: " + stderr.decode()[-1000:])
                uploaded = json.loads(stdout)
                state["config:asset"] = await call(
                    "inspect_asset_revision",
                    asset_id=uploaded.get("asset_id", uploaded["id"]),
                    verify=True,
                )
                save()
            await once(
                "config:binding",
                "bind_asset",
                asset_id=state["config:asset"]["id"],
                request=req(
                    "config-bind",
                    metadata={
                        "architecture": {"model_type": "attention_vad"},
                        "initialization": {"strategy": "scratch"},
                        "parameter_count": None,
                    },
                ),
            )
            baseline = await run(
                "scratch",
                "scratch",
                "train",
                {"dataset": data["id"], "model": state["config:asset"]["id"]},
            )
            history = await call("get_run_metrics", run_id=baseline["id"])
            validation = [e for e in history["events"] if e["split"] == "validation"]
            best = max(validation, key=lambda e: e["metrics"]["val_f1"])
            metrics = best["metrics"]
            positive = metrics["val_positive_ratio"]
            constant_f1 = 2 * positive / (1 + positive)
            if (
                not 0 < metrics["val_predicted_positive_ratio"] < 1
                or metrics["val_f1"] <= constant_f1
            ):
                raise RuntimeError("基线未超过验证集全语音参照；不能将它作为已验收预训练权重")
            state["baseline_quality"] = {
                "validation_history": validation,
                "selected": best,
                "all_positive_f1": constant_f1,
                "passed": True,
            }
            save()

            async def checkpoint(r):
                items = state[
                    next(
                        k for k in state if k.endswith(":run") and state[k].get("id") == r["id"]
                    ).removesuffix(":run")
                    + ":artifacts"
                ]
                return next(
                    a["name"]
                    for a in items
                    if a["name"].startswith("checkpoints/best-") and a["name"].endswith(".ckpt")
                )

            export = await run(
                "scratch-export",
                "export",
                "export",
                {"model": state["config:asset"]["id"]},
                source=(baseline["id"], await checkpoint(baseline)),
                cpu=True,
            )
            base = await promote("baseline", export, "model")
            for mode in ["full", "lora"]:
                trained = await run(
                    mode, mode, "train", {"dataset": data["id"], "model": base["id"]}
                )
                exported = await run(
                    mode + "-export",
                    "export",
                    "export",
                    {"model": base["id"]},
                    source=(trained["id"], await checkpoint(trained)),
                    cpu=True,
                )
                await promote(mode, exported, "model")
            # All training and checkpoint selection finish before any test evaluation.
            for mode, asset in [
                ("scratch", base),
                ("full", state["full:asset"]),
                ("lora", state["lora:asset"]),
            ]:
                r = await run(
                    mode + "-test",
                    "evaluate",
                    "evaluate",
                    {"dataset": data["id"], "model": asset["id"]},
                )
                m = r["metrics"]
                assert all(math.isfinite(v) for v in m.values() if isinstance(v, (int, float)))
                await run(
                    mode + "-infer",
                    "infer",
                    "infer",
                    {"dataset": data["id"], "model": asset["id"]},
                    cpu=True,
                )
            context = await call("get_work_context", work_item_id=work)
            owner = context["work_item"]
            if owner["status"] != "COMPLETED":
                await once(
                    "completion",
                    "update_work_item",
                    work_item_id=work,
                    request=req(
                        "complete",
                        expected_version=owner["version"],
                        status="COMPLETED",
                        summary=(
                            "人工 AVA 固定配方验收完成；Scratch、Full、LoRA 均有优化步与参数变化，"
                            "LoRA 冻结底座不变。三份 HF 导出模型通过独立 test 与重新加载推理。"
                            "Run 与资产身份见本工作任务上下文和客户端 evidence。"
                        ),
                        next_step="新实验创建新 WorkItem，复用固定环境、训练数据和配方。",
                    ),
                )
            state["complete"] = True
            save()
            print("COMPLETE", flush=True)


@app.command()
def main(
    api: str = "http://127.0.0.1:8021",
    evidence: Path = ROOT / "outputs/vad-training-loop/state.json",
    framework_source: Path = Path("/workspace/opus/preludio2"),
    publish: bool = False,
    version: str = "v5",
):
    """复用已发布的 AVA 环境，首次创建状态或恢复运行；--publish 显式发布数据。"""
    if os.environ.get("NINNA_INTEGRATION") != "1":
        raise typer.BadParameter("真实 Docker 验收需 NINNA_INTEGRATION=1")
    try:
        asyncio.run(exercise(api.rstrip("/"), evidence, framework_source, publish, version))
    except Exception as exc:
        pending = [exc]
        while pending:
            error = pending.pop()
            if getattr(error, "exceptions", None):
                pending.extend(error.exceptions)
            else:
                typer.echo(f"{type(error).__name__}: {error}", err=True)
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
