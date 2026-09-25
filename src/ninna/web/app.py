from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ninna.config import Settings
from ninna.domain.schemas import CreateRun, CreateProject
from ninna.domain.integrations import IntegrationUpdate, HubPublish, HubImport
from ninna.services.platform import Platform
from ninna.agent.server import create_server


class PromoteRequest(BaseModel):
    version: str = Field(pattern=r"^[a-zA-Z0-9_.-]+$")


def create_app(settings=None, serve_frontend=True):
    settings = settings or Settings.from_env()
    platform = Platform(settings)

    @asynccontextmanager
    async def lifespan(app):
        platform.start()
        try:
            async with mcp_server.session_manager.run():
                yield
        finally:
            platform.close()

    app = FastAPI(title="Ninna Training Platform", lifespan=lifespan)
    app.state.platform = platform
    import httpx

    mcp_server = create_server(
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://ninna",
            timeout=120,
        )
    )
    app.state.mcp = mcp_server
    app.mount("/mcp", mcp_server.streamable_http_app())

    @app.exception_handler(ValueError)
    async def invalid(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(KeyError)
    async def missing(request: Request, exc: KeyError):
        return JSONResponse(status_code=404, content={"detail": f"Not found: {exc}"})

    @app.get("/api/integrations")
    def integrations():
        return {**platform.integrations.public(), "tracking": platform.tracking.status()}

    @app.post("/api/integrations")
    def configure_integrations(request: IntegrationUpdate):
        return platform.integrations.update(request.hub, request.aim)

    @app.get("/api/hub/status")
    def hub_status():
        return platform.hub.status()

    @app.get("/api/hub/repositories")
    def hub_repositories(kind: Literal["model", "dataset"] = "model"):
        return platform.hub.repositories(kind)

    @app.get("/api/hub/transfers")
    def hub_transfers():
        return platform.repo.list("hub_transfers")

    @app.post("/api/hub/publish", status_code=202)
    def hub_publish(request: HubPublish):
        return platform.hub.submit("publish", request)

    @app.post("/api/hub/import", status_code=202)
    def hub_import(request: HubImport):
        return platform.hub.submit("import", request)

    @app.get("/api/experiments")
    def experiments(project_id: str):
        members = {run["id"] for run in platform.repo.project_runs(project_id)}
        return {
            "tracking": platform.tracking.status(),
            "runs": [
                {**run, "project_id": project_id}
                for run in platform.tracking.experiments()
                if run["id"] in members
            ],
        }

    @app.get("/api/experiments/{run_id}/metrics")
    def experiment_metrics(run_id: str):
        return platform.tracking.metrics(run_id)

    @app.get("/api/health")
    def health():
        return platform.health()

    @app.post("/api/initialize")
    def initialize():
        return platform.initialize()

    @app.get("/api/assets/{kind}")
    def assets(kind: Literal["dataset", "model", "recipe", "runtime", "workspace"]):
        return platform.repo.assets(kind)

    @app.post("/api/assets/{kind}", status_code=201)
    def register(kind: Literal["dataset", "model", "recipe", "runtime", "workspace"], asset: dict):
        from ninna.domain.schemas import Ref

        Ref.model_validate({key: asset.get(key) for key in ["name", "version"]})
        required = {
            "dataset": ["path", "files", "checksum", "train_split", "test_split"],
            "model": ["path", "files", "architecture", "initialization", "parameter_count"],
            "recipe": [
                "optimizer",
                "loss",
                "epochs",
                "batch_size",
                "gradient_accumulation",
                "seed",
            ],
            "runtime": ["image_id", "image"],
            "workspace": ["path", "entrypoint"],
        }[kind]
        if any(key not in asset for key in required):
            raise ValueError("Required asset fields: " + ", ".join(required))
        if kind in {"dataset", "model", "workspace"}:
            platform.settings.host_path(Path(asset["path"]))
        if kind == "workspace" and (
            Path(asset["entrypoint"]).is_absolute() or ".." in Path(asset["entrypoint"]).parts
        ):
            raise ValueError("Workspace entrypoint must be a relative path")
        if kind == "runtime":
            platform.runtime_validator.validate(asset)
        return platform.repo.register(kind, asset)

    @app.get("/api/assets/{kind}/{name}/{version}")
    def asset_detail(
        kind: Literal["dataset", "model", "recipe", "runtime", "workspace"], name: str, version: str
    ):
        from ninna.services.asset_docs import describe_asset

        asset = platform.repo.asset(kind, {"name": name, "version": version})
        return describe_asset(kind, asset, platform.settings.root)

    @app.post("/api/workspaces/{name}/snapshots")
    def snapshot(name: str):
        return platform.workspace_snapshot(name)

    @app.get("/api/workspaces/{name}/files")
    def files(name: str, path: str | None = None):
        workspace = platform.repo.asset("workspace", {"name": name, "version": "v1"})
        from ninna.services.assets import EXCLUDED

        root = Path(workspace["path"]).resolve()
        if path is None:
            return [
                str(p.relative_to(root))
                for p in sorted(root.rglob("*"))
                if p.is_file()
                and not any(
                    part in EXCLUDED or part.startswith(".env.")
                    for part in p.relative_to(root).parts
                )
            ]
        resolved = (root / path).resolve()
        if not resolved.is_relative_to(root) or any(
            part in EXCLUDED or part.startswith(".env.") for part in Path(path).parts
        ):
            raise HTTPException(403, "Path not allowed")
        if not resolved.is_file():
            raise HTTPException(404, "File not found")
        return {"path": path, "content": resolved.read_text(errors="replace")[:100000]}

    @app.post("/api/projects", status_code=201)
    def create_project(request: CreateProject):
        return platform.repo.create_project(request)

    @app.get("/api/projects")
    def projects():
        runs = platform.repo.list("runs")
        result = []
        for project in platform.repo.list("projects"):
            members = [run for run in runs if platform.repo.run_project(run) == project["id"]]
            result.append(
                {
                    **project,
                    "run_count": len(members),
                    "active_count": sum(
                        run["status"] not in {"SUCCESS", "FAILED", "CANCELLED"} for run in members
                    ),
                    "last_run_at": members[0]["created_at"] if members else None,
                }
            )
        return result

    @app.get("/api/projects/{project_id}")
    def project(project_id: str):
        return platform.repo.get("projects", project_id)

    @app.get("/api/projects/{project_id}/runs")
    def project_runs(project_id: str):
        return [{**run, "project_id": project_id} for run in platform.repo.project_runs(project_id)]

    @app.post("/api/runs", status_code=201)
    def create_run(request: CreateRun):
        return platform.create_run(request)

    @app.get("/api/runs")
    def runs(project_id: str | None = None):
        records = (
            platform.repo.project_runs(project_id) if project_id else platform.repo.list("runs")
        )
        return [{**run, "project_id": platform.repo.run_project(run)} for run in records]

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        record = platform.repo.get("runs", run_id)
        return {**record, "project_id": platform.repo.run_project(record)}

    @app.post("/api/runs/{run_id}/cancel")
    def cancel(run_id: str):
        return platform.cancel(run_id)

    @app.get("/api/runs/{run_id}/logs")
    def logs(
        run_id: str, stream: Literal["stdout", "stderr"] = "stdout", offset: int = Query(0, ge=0)
    ):
        platform.repo.get("runs", run_id)
        path = platform.output(run_id) / (stream + ".log")
        with path.open("rb") as source:
            source.seek(offset)
            content = source.read(128 * 1024)
            return {"content": content.decode(errors="replace"), "offset": source.tell()}

    @app.get("/api/runs/{run_id}/metrics")
    def metrics(run_id: str):
        return {
            "events": platform.metric_events(run_id),
            "final": platform.repo.get("runs", run_id)["metrics"],
        }

    @app.get("/api/runs/{run_id}/diagnostics")
    def diagnostic(run_id: str):
        return platform.get_run_diagnostic_context(run_id)

    @app.get("/api/runs/{run_id}/artifacts/{filename}")
    def artifact(run_id: str, filename: str):
        run = platform.repo.get("runs", run_id)
        allowed = {item["name"] for item in run["artifacts"]} | {
            "run.json",
            "stdout.log",
            "stderr.log",
        }
        if filename not in allowed or Path(filename).name != filename:
            raise HTTPException(404, "Artifact not found")
        path = platform.output(run_id) / filename
        if not path.is_file():
            raise HTTPException(404, "Artifact not found")
        return FileResponse(path, filename=filename)

    @app.post("/api/runs/{run_id}/promote", status_code=201)
    def promote(run_id: str, request: PromoteRequest):
        return platform.promote(run_id, request.version)

    @app.api_route("/api/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def unknown_api(path: str):
        raise HTTPException(404, "API route not found")

    @app.api_route("/api", methods=["GET", "HEAD"], include_in_schema=False)
    def api_root():
        raise HTTPException(404, "API route not found")

    if serve_frontend:
        dist = Path(os.environ.get("NINNA_WEB_DIST", settings.root / "src" / "web" / "dist"))
        if not dist.is_dir():
            raise RuntimeError("Frontend missing. Run pnpm --dir src/web run build first.")
        app.frontend("/", directory=dist, fallback="index.html")
    return app
