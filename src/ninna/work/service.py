"""Codex-facing work orchestration, sharing the platform's single training executor."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from ninna.domain.schemas import CreateTask, CreateRun
from ninna.services.assets import manifest, manifest_hash
from ninna.storage.repository import now
from ninna.work.assets import Assets, http_url
from ninna.work.environments import Environments
from ninna.work.store import Store, Conflict, digest

logger = logging.getLogger(__name__)


class WorkService:
    def __init__(self, platform):
        self.platform = platform
        self.store = Store(platform.repo)
        self.root = platform.settings.state / "work-v2"
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.assets = Assets(self)
        self.environments = Environments(self)
        self.stop = threading.Event()
        self.worker = None

    def capabilities(self):
        return {
            "api_version": 2,
            "entrypoint": "Codex MCP",
            "source_protocols": ["hf", "http_download", "local_import", "stream_upload"],
            "features": [
                "work_context",
                "remote_files",
                "commands",
                "environment_revisions",
                "run_plans",
                "start_run",
                "idempotent_jobs",
                "event_wait",
            ],
            "limits": {"training_concurrency": 1, "gpu_count": 1, "wait_seconds": 30},
            "agent_hosted": False,
        }

    def migrate(self, apply=False):
        repo = self.platform.repo
        legacy = [
            (kind, item)
            for kind in ("model", "dataset")
            for item in repo.assets(kind)
            if not item["name"].startswith("asset-")
        ]
        report = {
            "schema_version": 2,
            "assets": len(legacy),
            "runs_preserved": len(repo.list("runs")),
            "applied": apply,
        }
        if not apply:
            return report
        hub = self.platform.integrations.read()["hub"]
        source = self.store.create(
            "source",
            {
                "name": "原托管平台",
                "protocol": "hf",
                "endpoint": hub["endpoint"].rstrip("/"),
                "enabled": hub["enabled"],
                "token_env": None,
                "legacy_credentials": True,
            },
            "migration:source",
            "migration",
        )
        for kind, asset in legacy:
            ref = {"name": asset["name"], "version": asset["version"]}
            if any(
                a["kind"] == kind and a.get("legacy_ref") == ref for a in self.store.list("asset")
            ):
                continue
            origin = asset.get("metadata", {}).get("hub", {})
            value = {
                "name": asset["name"],
                "kind": kind,
                "path": asset["path"],
                "files": asset["files"],
                "checksum": asset.get("checksum", manifest_hash(asset["files"])),
                "revision": origin.get("revision", asset["version"]),
                "legacy_ref": {"name": asset["name"], "version": asset["version"]},
                "source_id": source["id"]
                if origin.get("endpoint", "").rstrip("/") == source["endpoint"]
                else None,
                "repo_id": origin.get("repo_id"),
                "legacy_origin": origin,
            }
            self.store.create("asset", value, "migration:" + asset["id"], "migration")
        for runtime in repo.assets("runtime"):
            if not runtime.get("image_ref") or runtime["name"].startswith("prepared-"):
                continue
            for workspace in repo.assets("workspace"):
                if runtime.get("framework") != workspace.get("metadata", {}).get("framework"):
                    continue
                self.store.create(
                    "environment",
                    {
                        "name": runtime["name"] + " · " + workspace["name"],
                        "description": "由历史运行环境导入，需准备并验证后发布。",
                        "image_ref": runtime["image_ref"],
                        "workspace_name": workspace["name"],
                        "framework": runtime.get("framework"),
                        "status": "DRAFT",
                        "ready": False,
                    },
                    "migration:env:" + runtime["id"] + ":" + workspace["id"],
                    "migration",
                )
        return report

    def create_source(self, request):
        value = request.model_dump(exclude={"request_id"})
        value["endpoint"] = http_url(value["endpoint"])
        from urllib.parse import urlsplit

        if urlsplit(value["endpoint"]).query or urlsplit(value["endpoint"]).fragment:
            raise ValueError("托管平台地址不能包含查询参数或片段。")
        return self.store.create("source", value, request.request_id, "create_source")

    def job(self, operation, payload, request_id):
        return self.store.create(
            "job",
            {
                "operation": operation,
                "payload": payload,
                "status": "QUEUED",
                "result": None,
                "error": None,
            },
            request_id,
            operation,
        )

    def mutate(self, scope, request_id, payload, action):
        """Serialize short mutations and retain their result for response-loss retries."""
        with self.lock:
            receipt = self.store.create(
                "receipt", {"scope": scope, "payload": payload}, request_id, scope
            )
            if "result" in receipt:
                return receipt["result"]
            result = action()
            self.store.put("receipt", {**receipt, "result": result})
            return result

    def create_environment(self, request):
        if request.workspace_name and request.git_url:
            raise ValueError("代码来源只能选择已有代码空间或 Git。")
        if request.git_url:
            http_url(request.git_url)
        self.platform.repo.asset("image", request.image_ref.model_dump())
        value = self.store.create(
            "environment",
            {**request.model_dump(exclude={"request_id"}), "status": "DRAFT", "ready": False},
            request.request_id,
            "create_environment",
        )
        self.job("initialize", {"owner_id": value["id"]}, "initialize:" + value["id"])
        return value

    def create_work(self, request):
        self.platform.repo.get("projects", request.project_id)
        revision = self.store.get("environment_revision", request.environment_revision_id)
        if revision["status"] != "PUBLISHED":
            raise ValueError("选择已发布的环境版本。")
        value = self.store.create(
            "work_item",
            {
                **request.model_dump(exclude={"request_id"}),
                "status": "ACTIVE",
                "ready": False,
                "summary": "",
                "next_step": "准备工作区",
            },
            request.request_id,
            "create_work",
        )
        self.job("initialize", {"owner_id": value["id"]}, "initialize:" + value["id"])
        return value

    def context(self, key):
        work = self.store.get("work_item", key)
        links = [r for r in self.store.list("run_link") if r["work_item_id"] == key]
        runs = []
        for link in links:
            try:
                run = self.platform.repo.get("runs", link["run_id"])
                runs.append(
                    {
                        k: run.get(k)
                        for k in (
                            "id",
                            "status",
                            "metrics",
                            "failure_reason",
                            "artifacts",
                            "metadata",
                        )
                    }
                )
            except KeyError:
                pass
            else:
                runs[-1]["plan_id"] = link["plan_id"]
        jobs = [
            j
            for j in self.store.list("job")
            if j["payload"].get("owner_id") == key or j["payload"].get("work_item_id") == key
        ]
        return {
            "work_item": work,
            "runs": runs,
            "jobs": jobs[:30],
            "plans": [p for p in self.store.list("plan") if p["work_item_id"] == key],
            "summary_origin": "agent",
            "execution_origin": "platform",
        }

    def make_plan(self, request):
        value = request.model_dump(exclude={"request_id"})
        work = self.store.get("work_item", request.work_item_id)
        if not work.get("ready") or work["status"] in {"COMPLETED", "ARCHIVED"}:
            raise ValueError("工作任务尚未就绪或已结束。")
        plan = self.store.create(
            "plan", {**value, "status": "CHECKING"}, request.request_id, "make_plan"
        )
        self.job(
            "check_plan", {"plan_id": plan["id"], "owner_id": work["id"]}, "check:" + plan["id"]
        )
        return plan

    def check_plan(self, job):
        plan = self.store.get("plan", job["payload"]["plan_id"])
        work = self.store.get("work_item", plan["work_item_id"])
        inputs = {}
        for name, key in plan["inputs"].items():
            kind, ref = self.assets.resolve(key)
            inputs[name] = {"kind": kind, "ref": ref}
        prepared = self.environments.seal(work["id"])
        framework = prepared.get("framework")
        validation = (
            self.environments.validate_framework(prepared)
            if framework
            else self.platform.runtime_validator.validate(prepared)
        )
        # Private immutable execution assets bridge to the existing, proven runner.
        version = plan["id"]
        image_ref = {"name": "prepared-image", "version": version}
        self.platform.repo.register(
            "image", {**image_ref, "image_id": prepared["image_id"], "metadata": {"prepared": True}}
        )
        runtime_ref = {"name": "prepared-runtime", "version": version}
        self.platform.repo.register(
            "runtime",
            {
                **runtime_ref,
                "image_ref": image_ref,
                "framework": framework,
                "validation": validation,
                "metadata": validation["versions"],
            },
        )
        workspace_name = "prepared-" + version
        self.platform.repo.register(
            "workspace",
            {
                "name": workspace_name,
                "version": "v1",
                "path": prepared["code_path"],
                "entrypoint": prepared["entrypoint"],
                "metadata": {"framework": framework},
            },
        )
        execution = {
            "runtime": runtime_ref,
            "workspace": {"name": workspace_name, "snapshot": "current"},
            "resources": plan["resources"],
        }
        if framework:
            body = {
                "project_id": work["project_id"],
                "framework": framework,
                "task": plan["task"],
                "operation": plan["operation"],
                "inputs": inputs,
                "recipe": plan["recipe"],
                "execution_spec": execution,
                "parent_run_id": plan.get("parent_run_id"),
                "source": {"run_id": plan["source_run_id"], "path": plan["source_path"]}
                if plan.get("source_run_id")
                else None,
            }
            self.platform.frameworks.preflight(CreateTask.model_validate(body))
        else:
            if plan["operation"] != "train" or set(inputs) != {"dataset", "model"}:
                raise ValueError("历史 MNIST 环境仅支持数据集与模型的 train 操作。")
            body = {
                "project_id": work["project_id"],
                "training_spec": {
                    "dataset": inputs["dataset"]["ref"],
                    "model": inputs["model"]["ref"],
                    "recipe": plan["recipe"],
                },
                "execution_spec": execution,
                "parent_run_id": plan.get("parent_run_id"),
            }
            CreateRun.model_validate(body)
        recipe = self.platform.repo.asset("recipe", plan["recipe"])
        return self.store.put(
            "plan",
            {
                **plan,
                "status": "READY",
                "prepared": prepared,
                "request": body,
                "recipe_checksum": digest(recipe),
                "error": None,
                "environment_revision_id": work["environment_revision_id"],
            },
        )

    def start_run(self, request):
        """Queue checking and execution together, retaining the ordinary sealed plan."""
        payload = request.model_dump(exclude={"request_id"})
        with self.lock:
            if not self.store.has_request(request.request_id):
                work = self.store.get("work_item", request.work_item_id)
                if not work.get("ready") or work["status"] in {"COMPLETED", "ARCHIVED"}:
                    raise ValueError("工作任务尚未就绪或已结束。")
                if self.environments.busy(work["id"]):
                    raise Conflict("工作区正在改变，请等待命令结束。")
            return self.job("start_run", payload, request.request_id)

    def start_plan(self, job):
        return self.store.create(
            "plan",
            {**job["payload"], "status": "CHECKING"},
            "start-plan:" + job["id"],
            "start_plan",
        )

    def execute_start(self, job):
        plan = self.start_plan(job)
        execution_job = {
            **job,
            "payload": {"plan_id": plan["id"], "work_item_id": plan["work_item_id"]},
        }
        run_id = "run-" + job["id"].removeprefix("job-")
        try:
            self.platform.repo.get("runs", run_id)
        except KeyError:
            work = self.store.get("work_item", plan["work_item_id"])
            if not work.get("ready") or work["status"] in {"COMPLETED", "ARCHIVED"}:
                raise Conflict("工作任务尚未就绪或已结束。")
            if plan["status"] != "READY":
                plan = self.check_plan(execution_job)
            self.check_submission(plan)
        return {**self.execute_run(execution_job), "plan_id": plan["id"]}

    def check_submission(self, plan):
        if plan["status"] != "READY":
            raise ValueError("运行方案尚未就绪，请检查准备任务和阻断原因。")
        work = self.store.get("work_item", plan["work_item_id"])
        if work["status"] in {"COMPLETED", "ARCHIVED"}:
            raise Conflict("工作任务已结束，请先恢复工作。")
        if self.environments.busy(work["id"]):
            raise Conflict("工作区正在改变，请等待命令结束并重新检查方案。")
        if (
            work.get("workspace_generation", work["version"])
            != plan["prepared"]["workspace_version"]
        ):
            raise Conflict("工作区在检查后已改变，请重新检查方案。")

    def submit(self, request):
        if self.store.has_request(request.request_id):
            plan = self.store.get("plan", request.plan_id)
            return self.job(
                "run",
                {"plan_id": plan["id"], "work_item_id": plan["work_item_id"]},
                request.request_id,
            )
        plan = self.store.get("plan", request.plan_id)
        self.check_submission(plan)
        return self.job(
            "run", {"plan_id": plan["id"], "work_item_id": plan["work_item_id"]}, request.request_id
        )

    def execute_run(self, job):
        plan = self.store.get("plan", job["payload"]["plan_id"])
        key = "run-" + job["id"].removeprefix("job-")
        try:
            run = self.platform.repo.get("runs", key)
        except KeyError:
            if manifest(Path(plan["prepared"]["code_path"])) != plan["prepared"]["files"]:
                raise Conflict("执行代码快照已改变，请重新准备方案。")
            if (
                digest(self.platform.repo.asset("recipe", plan["recipe"]))
                != plan["recipe_checksum"]
            ):
                raise Conflict("训练配置已改变，请重新准备方案。")
            for asset_id in plan["inputs"].values():
                self.assets.resolve(asset_id)
            if plan["prepared"].get("framework"):
                run = self.platform.frameworks.create(
                    CreateTask.model_validate(plan["request"]), run_id=key
                )
            else:
                run = self.platform.create_run(
                    CreateRun.model_validate(plan["request"]), run_id=key
                )
        self.store.put(
            "run_link",
            {
                "id": key,
                "created_at": now(),
                "run_id": key,
                "work_item_id": plan["work_item_id"],
                "plan_id": plan["id"],
                "environment_revision_id": plan["environment_revision_id"],
                "status": run["status"],
            },
        )
        return {"run_id": key, "work_item_id": plan["work_item_id"], "url": "/runs/" + key}

    def start(self):
        if self.worker:
            return
        for job in self.store.list("job"):
            if job["status"] != "RUNNING":
                continue
            if job["operation"] in {"command", "run"}:
                if job["operation"] == "run":
                    self.store.put("job", {**job, "status": "QUEUED"})
            elif job["operation"] == "start_run" and any(
                r["id"] == "run-" + job["id"].removeprefix("job-")
                for r in self.platform.repo.list("runs")
            ):
                self.store.put("job", {**job, "status": "QUEUED"})
            else:
                self.store.put(
                    "job",
                    {
                        **job,
                        "status": "FAILED",
                        "error": "平台重启中断该操作，请检查结果后使用新请求重试。",
                        "finished_at": now(),
                    },
                )
        self.worker = threading.Thread(target=self.loop, daemon=True, name="ninna-work")
        self.worker.start()

    def close(self):
        self.stop.set()
        if self.worker:
            self.worker.join(timeout=5)

    def loop(self):
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("Work event reconciliation failed")
            self.stop.wait(0.5)

    def tick(self):
        for link in self.store.list("run_link"):
            run = self.platform.repo.get("runs", link["run_id"])
            if run["status"] != link["status"]:
                self.store.put("run_link", {**link, "status": run["status"]})
        for job in reversed(self.store.list("job")):
            if job["status"] == "RUNNING" and job["operation"] == "command":
                self.process(job, poll=True)
        pending = [j for j in reversed(self.store.list("job")) if j["status"] == "QUEUED"]
        if pending:
            job = pending[0]
            with self.lock:
                job = self.store.get("job", job["id"])
                if job["status"] != "QUEUED":
                    return
                job = self.store.put("job", {**job, "status": "RUNNING", "started_at": now()})
            self.process(job)

    def process(self, job, poll=False):
        operations = {
            "acquire": self.assets.acquire,
            "publish_asset": self.assets.publish,
            "initialize": self.environments.initialize,
            "publish_environment": self.environments.publish,
            "command": self.environments.start_command,
            "check_plan": self.check_plan,
            "run": self.execute_run,
            "start_run": self.execute_start,
        }
        try:
            result = (
                self.environments.poll_command(job) if poll else operations[job["operation"]](job)
            )
            if result is None:
                return
            current = self.store.get("job", job["id"])
            status = (
                "CANCELLED"
                if current.get("cancel_requested")
                else "FAILED"
                if result.get("exit_code", 0)
                else "SUCCESS"
            )
            self.store.put(
                "job", {**current, "status": status, "result": result, "finished_at": now()}
            )
        except Exception as exc:
            # HTTP and Docker errors may contain credentials; do not expose their text.
            error = (
                str(exc) if type(exc) in {ValueError, Conflict, KeyError} else type(exc).__name__
            )
            self.store.put(
                "job",
                {
                    **self.store.get("job", job["id"]),
                    "status": "FAILED",
                    "error": error[:2000],
                    "finished_at": now(),
                },
            )
            if job["operation"] == "check_plan":
                plan = self.store.get("plan", job["payload"]["plan_id"])
                self.store.put("plan", {**plan, "status": "BLOCKED", "error": error[:2000]})
            elif job["operation"] == "start_run":
                plan = self.start_plan(job)
                if plan["status"] == "CHECKING":
                    self.store.put("plan", {**plan, "status": "BLOCKED", "error": error[:2000]})

    def command(self, owner_id, request):
        with self.lock:
            kind, owner = self.environments.owner(owner_id)
            payload = {"owner_id": owner_id, **request.model_dump(exclude={"request_id"})}
            if self.store.has_request(request.request_id):
                return self.job("command", payload, request.request_id)
            if not owner.get("ready"):
                raise Conflict("工作区尚未准备完成。")
            if self.environments.busy(owner_id):
                raise Conflict("工作区有命令正在执行，请等待或取消后再提交。")
            result = self.job("command", payload, request.request_id)
            self.store.put(
                kind,
                {
                    **owner,
                    "workspace_generation": owner.get("workspace_generation", owner["version"]) + 1,
                },
            )
            return result
