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
    parser.add_argument("--model-version", default="smoke-v1")
    parser.add_argument("--dataset-version", default="smoke-v1")
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
            identity = {"name": name, "version": getattr(args, kind + "_version")}
            existing = client.get(f"/assets/{kind}/{name}/{identity['version']}")
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
        import uuid

        invocation = uuid.uuid4().hex

        def mutation(label, **body):
            return {"request_id": invocation + ":" + label, **body}

        def wait_job(job):
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                job = call("/v2/jobs/" + job["id"])
                if job["status"] in {"SUCCESS", "FAILED", "CANCELLED"}:
                    if job["status"] != "SUCCESS":
                        raise ValueError(job)
                    return job["result"]
                time.sleep(1)
            raise TimeoutError(job["id"])

        runtime = call(f"/assets/runtime/{args.framework}/{args.runtime_version}")["asset"]
        workspace = args.workspace_name or args.framework + "-" + args.runtime_version
        env = next(
            (
                e
                for e in call("/v2/environments")
                if e.get("workspace_name") == workspace
                and e.get("image_ref") == runtime["image_ref"]
            ),
            None,
        )
        if env is None:
            env = call(
                "/v2/environments",
                mutation(
                    "environment",
                    name=args.framework + " verification",
                    image_ref=runtime["image_ref"],
                    workspace_name=workspace,
                    framework=runtime["framework"],
                ),
            )
        if not env.get("latest_revision_id"):
            wait_job(call(f"/v2/environments/{env['id']}/prepare", mutation("prepare")))
            revision = wait_job(call(f"/v2/environments/{env['id']}/publish", mutation("publish")))
        else:
            revision = call("/v2/environment-revisions/" + env["latest_revision_id"])
        work = call(
            "/v2/work-items",
            mutation(
                "work",
                project_id=project["id"],
                title=args.framework + " · " + args.task + " · " + args.operation,
                goal="真实容器框架回归验证",
                environment_revision_id=revision["id"],
            ),
        )
        for _ in range(180):
            if call("/v2/work-items/" + work["id"])["work_item"]["ready"]:
                break
            time.sleep(1)
        # Existing immutable definitions are indexed without rewriting their records.
        call("/v2/migration", mutation("migration"))
        catalog = call("/v2/assets")
        resolved = {
            name: next(
                a["id"]
                for a in catalog
                if a["kind"] == value["kind"] and a.get("legacy_ref") == value["ref"]
            )
            for name, value in inputs.items()
        }
        plan = call(
            "/v2/run-plans",
            mutation(
                "plan",
                work_item_id=work["id"],
                task=args.task,
                operation=args.operation,
                inputs=resolved,
                recipe={"name": args.recipe, "version": args.recipe_version},
                resources={
                    "device": "cuda" if args.gpu else "cpu",
                    "gpu_count": 1 if args.gpu else 0,
                    "gpu_ids": [args.gpu] if args.gpu else [],
                    "cpu_threads": 4,
                    "memory_mb": args.memory,
                },
                source_run_id=args.source_run,
                source_path=args.source_path if args.source_run else None,
            ),
        )
        for _ in range(180):
            plan = call("/v2/run-plans/" + plan["id"])
            if plan["status"] in {"READY", "BLOCKED"}:
                break
            time.sleep(1)
        if plan["status"] != "READY":
            raise ValueError(plan)
        submitted = wait_job(call("/v2/runs", mutation("submit", plan_id=plan["id"])))
        run = call("/runs/" + submitted["run_id"])
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
