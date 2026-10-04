"""通过正在运行的 Ninna API 验证真实镜像。必须显式 NINNA_INTEGRATION=1。"""

import argparse
import json
import os
from pathlib import Path
import time

import httpx
from ninna.services.assets import manifest, manifest_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("framework")
    parser.add_argument("task")
    parser.add_argument("recipe")
    parser.add_argument("--dataset")
    parser.add_argument("--model")
    parser.add_argument("--operation", default="train")
    parser.add_argument("--source-run")
    parser.add_argument("--source-path", default="checkpoints/last.ckpt")
    parser.add_argument("--gpu")
    parser.add_argument("--runtime-version", default="ninna-v1")
    parser.add_argument("--recipe-version", default="ninna-v1")
    parser.add_argument("--workspace-name", help="Use an explicitly registered workspace")
    parser.add_argument("--memory", type=int, default=16384)
    parser.add_argument("--api", default="http://127.0.0.1:8011")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument(
        "--input-root", type=Path, default=Path("outputs/framework-integration/inputs")
    )
    args = parser.parse_args()
    if os.environ.get("NINNA_INTEGRATION") != "1":
        raise SystemExit("Real Docker tests require NINNA_INTEGRATION=1")
    with httpx.Client(base_url=args.api + "/api", timeout=300) as client:

        def call(path, body=None):
            response = client.get(path) if body is None else client.post(path, json=body)
            if response.is_error:
                raise ValueError(f"{path}: {response.text}")
            return response.json()

        projects = call("/projects")
        project = next((p for p in projects if p["name"] == "framework-integration"), None)
        if not project:
            project = call(
                "/projects",
                {"name": "framework-integration", "description": "六框架真实容器接入验证"},
            )
        inputs = {}
        for kind, name in (("dataset", args.dataset), ("model", args.model)):
            if not name:
                continue
            identity = {"name": name, "version": "smoke-v1"}
            existing = client.get(f"/assets/{kind}/{name}/smoke-v1")
            if existing.status_code != 200:
                path = (args.input_root / name).resolve()
                files = manifest(path)
                if not files:
                    raise ValueError(f"Missing staged asset: {path}")
                value = {
                    **identity,
                    "path": str(path),
                    "files": files,
                    "checksum": manifest_hash(files),
                    "metadata": {"purpose": "smoke"},
                }
                if kind == "dataset":
                    value.update(train_split={"name": "train"}, test_split={"name": "test"})
                else:
                    value.update(
                        architecture={"framework": args.framework},
                        initialization={"source": "local"},
                        parameter_count=None,
                    )
                call(f"/assets/{kind}", value)
            inputs[kind] = {"kind": kind, "ref": identity}
        request = {
            "protocol_version": 1,
            "project_id": project["id"],
            "framework": {"name": args.framework, "version": "ninna-v1"},
            "task": args.task,
            "operation": args.operation,
            "inputs": inputs,
            "recipe": {"name": args.recipe, "version": args.recipe_version},
            "execution_spec": {
                "runtime": {"name": args.framework, "version": args.runtime_version},
                "workspace": {
                    "name": args.workspace_name or args.framework + "-" + args.runtime_version
                },
                "resources": {
                    "device": "cuda" if args.gpu else "cpu",
                    "gpu_count": 1 if args.gpu else 0,
                    "gpu_ids": [args.gpu] if args.gpu else [],
                    "cpu_threads": 4,
                    "memory_mb": args.memory,
                },
            },
        }
        if args.source_run:
            request["source"] = {"run_id": args.source_run, "path": args.source_path}
        call("/tasks/preflight", request)
        run = call("/tasks", request)
        print(json.dumps({"run_id": run["id"], "operation": args.operation}), flush=True)
        deadline = time.monotonic() + args.timeout
        previous = None
        while time.monotonic() < deadline:
            run = call("/runs/" + run["id"])
            if run["status"] != previous:
                print(run["id"], run["status"], flush=True)
                previous = run["status"]
            if run["status"] in {"SUCCESS", "FAILED", "CANCELLED"}:
                print(
                    json.dumps(
                        {
                            k: run.get(k)
                            for k in (
                                "id",
                                "status",
                                "container_id",
                                "failure_reason",
                                "metrics",
                                "metadata",
                            )
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                if run["status"] != "SUCCESS":
                    raise SystemExit(1)
                return
            time.sleep(2)
        raise TimeoutError(f"Run {run['id']} still active; inspect it before resubmitting")


if __name__ == "__main__":
    main()
