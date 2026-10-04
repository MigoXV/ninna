"""Typed MCP capabilities for external Codex clients; never hosts an Agent."""

from typing import Any, Literal
from urllib.parse import quote

from mcp.types import ToolAnnotations
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
)

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True)
EDIT = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True)


def add_tools(server, call):
    def path(key):
        return quote(key, safe="")

    @server.tool(annotations=READ)
    async def get_capabilities() -> dict[str, Any]:
        """Read version 2 capabilities and limits before using Ninna. Codex owns reasoning."""
        return await call("GET", "/api/v2/capabilities")

    @server.tool(annotations=READ)
    async def list_sources() -> dict[str, Any]:
        """List independent hosting platforms; credentials never enter the response."""
        return {"items": await call("GET", "/api/v2/sources")}

    @server.tool(annotations=WRITE)
    async def configure_source(
        request: SourceInput, source_id: str | None = None, expected_version: int | None = None
    ) -> dict[str, Any]:
        """Add/update a hosting platform. token_env names a deployment variable, not a token value.
        Updates need expected_version. Keep request_id stable when retrying the same request.
        """
        if source_id:
            update = SourceUpdate(**request.model_dump(), expected_version=expected_version)
            return await call(
                "POST", "/api/v2/sources/" + path(source_id), json=update.model_dump()
            )
        return await call("POST", "/api/v2/sources", json=request.model_dump())

    @server.tool(annotations=READ)
    async def check_source(source_id: str) -> dict[str, Any]:
        """Check one source; its failure does not invalidate downloaded local assets."""
        return await call("GET", f"/api/v2/sources/{path(source_id)}/status")

    @server.tool(annotations=READ)
    async def search_source_assets(
        source_id: str,
        kind: Literal["model", "dataset"] = "model",
        query: str = "",
        offset: int = 0,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Search one hosting platform with pagination; includes downloaded revisions."""
        return await call(
            "GET",
            f"/api/v2/sources/{path(source_id)}/assets",
            params={"kind": kind, "q": query, "offset": offset, "limit": limit},
        )

    @server.tool(annotations=READ)
    async def list_asset_revisions(
        kind: Literal["model", "dataset"] | None = None,
    ) -> dict[str, Any]:
        """List local asset identities and availability. Downloaded does not mean training-compatible."""
        return {"items": await call("GET", "/api/v2/assets", params={"kind": kind} if kind else {})}

    @server.tool(annotations=READ)
    async def inspect_asset_revision(asset_id: str, verify: bool = False) -> dict[str, Any]:
        """Inspect provenance/files. verify hashes local files; large assets can take time."""
        return await call("GET", "/api/v2/assets/" + path(asset_id), params={"verify": verify})

    @server.tool(annotations=WRITE)
    async def acquire_asset(request: Acquire) -> dict[str, Any]:
        """Download/import exactly one source: HF platform, HTTP URL or Ninna-host local path.
        No ninna-asset.json required. Returns a persistent Job; wait and inspect its result.
        For files on the Codex machine use `poetry run ninna upload --help` and streaming HTTP.
        """
        return await call("POST", "/api/v2/assets/acquire", json=request.model_dump())

    @server.tool(annotations=WRITE)
    async def bind_asset(asset_id: str, request: Binding) -> dict[str, Any]:
        """Describe downloaded files for training: dataset splits or model loading metadata.
        Does not prove compatibility; prepare_run_plan checks the selected framework operation.
        """
        return await call(
            "POST", f"/api/v2/assets/{path(asset_id)}/binding", json=request.model_dump()
        )

    @server.tool(annotations=WRITE)
    async def publish_asset_revision(asset_id: str, request: PublishAsset) -> dict[str, Any]:
        """Explicitly publish to a selected hosting platform (external write). Requires user intent.
        Returns a Job; downloading/training never publishes automatically.
        """
        return await call(
            "POST", f"/api/v2/assets/{path(asset_id)}/publish", json=request.model_dump()
        )

    @server.tool(annotations=READ)
    async def list_environments() -> dict[str, Any]:
        """List environment drafts and immutable published revisions usable by work items."""
        return {"items": await call("GET", "/api/v2/environments")}

    @server.tool(annotations=WRITE)
    async def create_environment(request: EnvironmentInput) -> dict[str, Any]:
        """Create a preparation environment from an Image and optional Workspace or Git checkout.
        Preparation is asynchronous. Edit files/run commands using the returned environment ID.
        """
        return await call("POST", "/api/v2/environments", json=request.model_dump())

    @server.tool(annotations=WRITE)
    async def prepare_environment(environment_id: str, request: Mutation) -> dict[str, Any]:
        """Prepare a migrated draft or retry failed setup. Returns a Job; inspect actual result."""
        return await call(
            "POST",
            f"/api/v2/environments/{path(environment_id)}/prepare",
            json=request.model_dump(),
        )

    @server.tool(annotations=WRITE)
    async def publish_environment(environment_id: str, request: Mutation) -> dict[str, Any]:
        """Freeze prepared dependencies/code and validate them; creates a new immutable revision.
        Existing work items retain their own state. Wait for Job SUCCESS before selecting revision.
        """
        return await call(
            "POST",
            f"/api/v2/environments/{path(environment_id)}/publish",
            json=request.model_dump(),
        )

    @server.tool(annotations=READ)
    async def list_work_items(project_id: str) -> dict[str, Any]:
        """Find persistent work goals in one project when continuing in a new Codex session."""
        return {"items": await call("GET", "/api/v2/work-items", params={"project_id": project_id})}

    @server.tool(annotations=WRITE)
    async def create_work_item(request: WorkInput) -> dict[str, Any]:
        """Save a user goal and create an independent workspace from a published environment.
        Does not train. Wait for workspace readiness using get_work_context before commands.
        """
        return await call("POST", "/api/v2/work-items", json=request.model_dump())

    @server.tool(annotations=READ)
    async def get_work_context(work_item_id: str) -> dict[str, Any]:
        """Recover goal, constraints, Agent summary, next step, plans, Jobs and actual Runs.
        Agent summaries are not execution evidence; verify platform metrics and artifacts.
        """
        return await call("GET", "/api/v2/work-items/" + path(work_item_id))

    @server.tool(annotations=WRITE)
    async def update_work_item(work_item_id: str, request: WorkUpdate) -> dict[str, Any]:
        """Persist a concise progress summary/next step, not hidden reasoning or conversation logs.
        Uses optimistic version checking. Failed Runs do not automatically finish the work item.
        """
        return await call(
            "POST", "/api/v2/work-items/" + path(work_item_id), json=request.model_dump()
        )

    @server.tool(annotations=READ)
    async def read_task_files(owner_id: str, relative_path: str | None = None) -> dict[str, Any]:
        """List or read environment/work-item files, returning SHA-256 for conflict-safe edits."""
        return await call(
            "GET",
            f"/api/v2/workspaces/{path(owner_id)}/files",
            params={"path": relative_path} if relative_path else {},
        )

    @server.tool(annotations=EDIT)
    async def edit_task_file(owner_id: str, request: FileEdit) -> dict[str, Any]:
        """Write/delete a task-local file. expected_sha256=null only for a new file.
        Existing file edits require the SHA returned by read_task_files. Never edits old Runs.
        """
        return await call(
            "POST", f"/api/v2/workspaces/{path(owner_id)}/files", json=request.model_dump()
        )

    @server.tool(annotations=EDIT)
    async def execute_task_command(owner_id: str, request: Command) -> dict[str, Any]:
        """Execute argv inside a managed preparation container, not the platform host.
        CPU-only preparation; formal training uses submit_run. Returns persistent Job/logs.
        Use ['bash','-lc',script] only when shell semantics are intended. One command per workspace.
        """
        return await call(
            "POST", f"/api/v2/workspaces/{path(owner_id)}/commands", json=request.model_dump()
        )

    @server.tool(annotations=WRITE)
    async def set_workspace_state(
        owner_id: str, action: Literal["start", "stop"], request: Mutation
    ) -> dict[str, Any]:
        """Start/stop a workspace while preserving files and installed dependencies. Never deletes it."""
        return await call(
            "POST", f"/api/v2/workspaces/{path(owner_id)}/{action}", json=request.model_dump()
        )

    @server.tool(annotations=READ)
    async def list_jobs() -> dict[str, Any]:
        """Find persisted transfers, setup, commands and submissions after a connection failure."""
        return {"items": await call("GET", "/api/v2/jobs")}

    @server.tool(annotations=READ)
    async def get_job(job_id: str) -> dict[str, Any]:
        """Read Job state/result. A successful run-submission Job is not a successful training Run."""
        return await call("GET", "/api/v2/jobs/" + path(job_id))

    @server.tool(annotations=READ)
    async def read_job_logs(
        job_id: str, stream: Literal["stdout", "stderr"] = "stdout", offset: int = 0
    ) -> dict[str, Any]:
        """Read command output incrementally by byte offset; empty output is not completion."""
        return await call(
            "GET", f"/api/v2/jobs/{path(job_id)}/logs", params={"stream": stream, "offset": offset}
        )

    @server.tool(annotations=WRITE)
    async def cancel_job(job_id: str, request: Mutation) -> dict[str, Any]:
        """Cancel queued work or a running preparation command. Does not delete the workspace."""
        return await call("POST", f"/api/v2/jobs/{path(job_id)}/cancel", json=request.model_dump())

    @server.tool(annotations=WRITE)
    async def prepare_run_plan(request: PlanInput) -> dict[str, Any]:
        """Freeze input versions, code and dependencies and check a framework operation.
        Returns a plan in CHECKING; read_run_plan until READY/BLOCKED. Never downloads implicitly.
        """
        return await call("POST", "/api/v2/run-plans", json=request.model_dump())

    @server.tool(annotations=READ)
    async def read_run_plan(plan_id: str) -> dict[str, Any]:
        """Read the fixed execution plan or its concrete preparation blocker."""
        return await call("GET", "/api/v2/run-plans/" + path(plan_id))

    @server.tool(annotations=WRITE)
    async def submit_run(request: SubmitRun) -> dict[str, Any]:
        """Submit a READY plan once using request_id. Returns a Job whose result contains run_id.
        Follow get_run/metrics/artifacts to terminal; submission success is not training success.
        """
        return await call("POST", "/api/v2/runs", json=request.model_dump())

    @server.tool(annotations=READ)
    async def wait_for_events(
        after: int = 0, object_id: str | None = None, wait_seconds: float = 25
    ) -> dict[str, Any]:
        """Wait up to 30 seconds for persisted changes. Save cursor; reconnect without losing events.
        Does not wake an exited Codex session. Run-link events reference actual Run IDs.
        """
        return await call(
            "GET",
            "/api/v2/events",
            params={
                k: v
                for k, v in {"after": after, "object_id": object_id, "wait": wait_seconds}.items()
                if v is not None
            },
        )
