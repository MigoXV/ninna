from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query, Request

from ninna.storage.repository import now
from ninna.work.assets import safe_path, http_url
from ninna.work.schemas import (
    Mutation,
    SourceInput,
    SourceUpdate,
    Acquire,
    PublishAsset,
    EnvironmentInput,
    WorkInput,
    WorkUpdate,
    FileEdit,
    Command,
    PlanInput,
    SubmitRun,
    Binding,
    UploadInput,
)
from ninna.work.store import Conflict


def router(service):
    api = APIRouter(prefix="/api/v2")
    store = service.store

    @api.get("/capabilities")
    def capabilities():
        return service.capabilities()

    @api.get("/migration")
    def migration_report():
        return service.migrate()

    @api.post("/migration")
    def migrate(request: Mutation):
        return service.mutate(
            "migration", request.request_id, {}, lambda: service.migrate(apply=True)
        )

    @api.get("/sources")
    def sources():
        return store.list("source")

    @api.post("/sources", status_code=201)
    def source_create(request: SourceInput):
        return service.create_source(request)

    @api.post("/sources/{key}")
    def source_update(key: str, request: SourceUpdate):
        def update():
            source = store.get("source", key)
            values = request.model_dump(exclude={"request_id", "expected_version"})
            values["endpoint"] = http_url(values["endpoint"])
            from urllib.parse import urlsplit

            if urlsplit(values["endpoint"]).query or urlsplit(values["endpoint"]).fragment:
                raise ValueError("托管平台地址不能包含查询参数或片段。")
            return store.put(
                "source",
                {
                    **source,
                    **values,
                    "legacy_credentials": source.get("legacy_credentials", False)
                    and values["endpoint"] == source["endpoint"]
                    and not values["token_env"],
                },
                request.expected_version,
            )

        return service.mutate(
            "source_update:" + key, request.request_id, request.model_dump(), update
        )

    @api.get("/sources/{key}/status")
    def source_status(key: str):
        return service.assets.source_status(key)

    @api.get("/sources/{key}/assets")
    def browse(
        key: str,
        kind: Literal["model", "dataset"] = "model",
        q: str = "",
        offset: int = Query(0, ge=0, le=10000),
        limit: int = Query(30, ge=1, le=100),
    ):
        return service.assets.browse(key, kind, q, offset, limit)

    @api.get("/assets")
    def assets(kind: Literal["model", "dataset"] | None = None):
        return [
            service.assets.describe(a["id"])
            for a in store.list("asset")
            if kind is None or a["kind"] == kind
        ]

    @api.post("/assets/acquire", status_code=202)
    def acquire(request: Acquire):
        if sum(bool(v) for v in (request.source_id, request.url, request.local_path)) != 1:
            raise ValueError("必须且只能选择一个资产来源。")
        if request.source_id:
            service.assets.source(request.source_id)
        return service.job(
            "acquire", request.model_dump(exclude={"request_id"}), request.request_id
        )

    @api.get("/assets/{key}")
    def asset(key: str, verify: bool = False):
        return service.assets.describe(key, verify)

    @api.post("/assets/{key}/binding")
    def binding(key: str, request: Binding):
        return service.mutate(
            "bind:" + key,
            request.request_id,
            request.model_dump(),
            lambda: service.assets.bind(key, request.metadata),
        )

    @api.post("/assets/{key}/publish", status_code=202)
    def publish_asset(key: str, request: PublishAsset):
        service.assets.describe(key)
        service.assets.source(request.source_id)
        return service.job(
            "publish_asset",
            {"asset_id": key, **request.model_dump(exclude={"request_id"})},
            request.request_id,
        )

    @api.post("/uploads", status_code=201)
    def upload_create(request: UploadInput):
        return store.create(
            "upload",
            {**request.model_dump(exclude={"request_id"}), "status": "OPEN"},
            request.request_id,
            "upload",
        )

    @api.put("/uploads/{key}/files")
    async def upload_file(
        key: str, request: Request, path: str, sha256: str = Query(pattern=r"^[a-f0-9]{64}$")
    ):
        value = store.get("upload", key)
        if value["status"] != "OPEN":
            raise Conflict("上传已封存。")
        root = service.root / "uploads" / key
        root.mkdir(parents=True, exist_ok=True)
        target = safe_path(root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        import uuid

        temporary = target.with_name(target.name + "." + uuid.uuid4().hex + ".partial")
        digest = hashlib.sha256()
        try:
            with temporary.open("wb") as output:
                async for chunk in request.stream():
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != sha256:
                raise ValueError("上传文件 SHA-256 不匹配。")
            with service.lock:
                if store.get("upload", key)["status"] != "OPEN":
                    raise Conflict("上传已封存。")
                temporary.replace(target)
            return {"path": path, "sha256": sha256}
        finally:
            temporary.unlink(missing_ok=True)

    @api.post("/uploads/{key}/complete")
    def upload_complete(key: str, request: Mutation):
        def complete():
            value = store.get("upload", key)
            if value.get("asset_id"):
                return service.assets.describe(value["asset_id"])
            root = service.root / "uploads" / key
            if any(root.rglob("*.partial")):
                raise Conflict("仍有文件上传中。")
            asset = service.assets.adopt(root, value, {"upload_id": key})
            store.put("upload", {**value, "status": "COMPLETE", "asset_id": asset["id"]})
            return asset

        return service.mutate("complete_upload:" + key, request.request_id, {}, complete)

    @api.get("/environments")
    def environments():
        return [
            {
                **e,
                "revisions": [
                    r for r in store.list("environment_revision") if r["environment_id"] == e["id"]
                ],
            }
            for e in store.list("environment")
        ]

    @api.post("/environments", status_code=201)
    def environment_create(request: EnvironmentInput):
        return service.create_environment(request)

    @api.post("/environments/{key}/prepare", status_code=202)
    def prepare_environment(key: str, request: Mutation):
        store.get("environment", key)
        return service.job("initialize", {"owner_id": key}, request.request_id)

    @api.post("/environments/{key}/publish", status_code=202)
    def publish_environment(key: str, request: Mutation):
        store.get("environment", key)
        return service.job("publish_environment", {"owner_id": key}, request.request_id)

    @api.get("/environment-revisions/{key}")
    def revision(key: str):
        return store.get("environment_revision", key)

    @api.get("/work-items")
    def work_items(project_id: str):
        service.platform.repo.get("projects", project_id)
        return [w for w in store.list("work_item") if w["project_id"] == project_id]

    @api.post("/work-items", status_code=201)
    def work_create(request: WorkInput):
        return service.create_work(request)

    @api.get("/work-items/{key}")
    def work_context(key: str):
        return service.context(key)

    @api.post("/work-items/{key}")
    def work_update(key: str, request: WorkUpdate):
        return service.mutate(
            "update_work:" + key,
            request.request_id,
            request.model_dump(),
            lambda: store.put(
                "work_item",
                {
                    **store.get("work_item", key),
                    **request.model_dump(exclude={"request_id", "expected_version"}),
                },
                request.expected_version,
            ),
        )

    @api.get("/workspaces/{key}/files")
    def files(key: str, path: str | None = None):
        return service.environments.files(key, path)

    @api.post("/workspaces/{key}/files")
    def edit(key: str, request: FileEdit):
        return service.mutate(
            "edit:" + key,
            request.request_id,
            request.model_dump(),
            lambda: service.environments.edit(key, request),
        )

    @api.post("/workspaces/{key}/commands", status_code=202)
    def command(key: str, request: Command):
        return service.command(key, request)

    @api.post("/workspaces/{key}/{action}")
    def lifecycle(key: str, action: Literal["start", "stop"], request: Mutation):
        def change():
            if service.environments.busy(key):
                raise Conflict("工作区有命令执行中，请先等待或取消。")
            container = service.environments.container(key, start=action == "start")
            if action == "stop":
                container.stop(timeout=5)
            container.reload()
            return {"owner_id": key, "container_id": container.id, "status": container.status}

        return service.mutate(action + ":" + key, request.request_id, {}, change)

    @api.get("/jobs")
    def jobs():
        return store.list("job")

    @api.get("/jobs/{key}")
    def job(key: str):
        return store.get("job", key)

    @api.get("/jobs/{key}/logs")
    def logs(
        key: str, stream: Literal["stdout", "stderr"] = "stdout", offset: int = Query(0, ge=0)
    ):
        value = store.get("job", key)
        path = Path(value["log_path"]) / (stream + ".log") if value.get("log_path") else None
        content = b""
        if path and path.exists():
            with path.open("rb") as file:
                file.seek(offset)
                content = file.read(131072)
        return {
            "content": content.decode(errors="replace"),
            "offset": offset + len(content),
            "status": value["status"],
        }

    @api.post("/jobs/{key}/cancel")
    def cancel_job(key: str, request: Mutation):
        with service.lock:
            value = store.get("job", key)
            if value["status"] not in {"QUEUED", "RUNNING"}:
                return value
            if value["status"] == "QUEUED":
                return store.put("job", {**value, "status": "CANCELLED", "finished_at": now()})
            if value["operation"] != "command":
                raise Conflict("该操作已开始；请等待结果，训练运行使用 Run 取消接口。")
            service.environments.cancel_command(value)
            return store.put("job", {**value, "cancel_requested": True})

    @api.post("/run-plans", status_code=202)
    def plan(request: PlanInput):
        return service.make_plan(request)

    @api.get("/run-plans/{key}")
    def read_plan(key: str):
        return store.get("plan", key)

    @api.post("/runs", status_code=202)
    def run(request: SubmitRun):
        return service.submit(request)

    @api.post("/runs/start", status_code=202)
    def start_run(request: PlanInput):
        return service.start_run(request)

    @api.get("/events")
    async def events(
        after: int = Query(0, ge=0),
        object_id: str | None = None,
        wait: float = Query(0, ge=0, le=30),
    ):
        deadline = asyncio.get_running_loop().time() + wait
        while True:
            result = store.events(after, object_id)
            if result["items"] or asyncio.get_running_loop().time() >= deadline:
                return result
            await asyncio.sleep(0.25)

    return api


def install(app, service):
    app.include_router(router(service))

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "code": "CONFLICT",
                    "message": str(exc),
                    "retryable": False,
                    "next_action": "重新读取对象后提交。",
                }
            },
        )
