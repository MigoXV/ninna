import asyncio
import json

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from ninna.agent.server import create_server
from ninna.config import Settings
from ninna.services.asset_docs import describe_asset
from ninna.services.assets import manifest, manifest_hash
from ninna.services.platform import Platform
from ninna.web.app import create_app


def test_mcp_http_catalog_resource_and_asset_roundtrip(tmp_path):
    async def exercise():
        app = create_app(Settings(tmp_path, tmp_path, tmp_path / "state"), serve_frontend=False)

        # Only protocol lifespan here. Integration tests exercise the real platform worker.
        def client_factory(**kwargs):
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), follow_redirects=True, **kwargs
            )

        async with app.state.mcp.session_manager.run(), client_factory() as client:
            async with streamable_http_client("http://localhost/mcp/", http_client=client) as (
                reader,
                writer,
                _,
            ):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                    assert tools["browse_images"].annotations.readOnlyHint
                    app.state.platform.repo.register(
                        "image",
                        {
                            "name": "test-image",
                            "version": "v1",
                            "source_reference": "registry.example/team/pytorch:v1",
                            "image_id": "sha256:abc",
                            "tags": [],
                            "created_at": "2026-09-25",
                        },
                    )
                    catalog = await session.call_tool(
                        "browse_images", {"registry": "registry.example", "namespace": "team"}
                    )
                    assert not catalog.isError
                    assert catalog.structuredContent["items"][0]["name"] == "pytorch"
                    assert "start_certification" not in tools
                    assert "get_certification" not in tools
                    project = await session.call_tool("create_project", {"name": "mcp-project"})
                    assert not project.isError
                    projects = await session.call_tool("list_projects", {})
                    assert projects.structuredContent["projects"][0]["id"] == "mcp-project"
                    assert "create_run" not in tools and "create_task" not in tools
                    assert tools["describe_asset"].annotations.readOnlyHint
                    assert tools["submit_run"].annotations.idempotentHint
                    assert tools["start_run"].annotations.idempotentHint
                    assert tools["cancel_run"].annotations.destructiveHint
                    capabilities = await session.call_tool("get_capabilities", {})
                    assert capabilities.structuredContent["api_version"] == 2
                    assert "execute_task_command" in tools
                    start = await session.call_tool(
                        "start_run",
                        {
                            "request": {
                                "request_id": "missing-work",
                                "work_item_id": "absent",
                                "task": "vad",
                                "recipe": {"name": "scratch", "version": "v1"},
                            }
                        },
                    )
                    assert start.isError
                    guide = await session.read_resource("ninna://guide")
                    assert "Ninna" in guide.contents[0].text
                    asset = {
                        "name": "adam",
                        "version": "v1",
                        "optimizer": {"name": "Adam"},
                        "loss": "CrossEntropyLoss",
                        "epochs": 1,
                        "batch_size": 128,
                        "gradient_accumulation": 1,
                        "seed": 7,
                    }
                    registered = await session.call_tool(
                        "register_asset", {"kind": "recipe", "asset": asset}
                    )
                    assert not registered.isError
                    described = await session.call_tool(
                        "describe_asset",
                        {"kind": "recipe", "ref": {"name": "adam", "version": "v1"}},
                    )
                    assert not described.isError, described
                    assert described.structuredContent is not None, described
                    assert described.structuredContent["asset"]["optimizer"]["name"] == "Adam"
                    resource = await session.read_resource("ninna://assets/recipe/adam/v1")
                    assert json.loads(resource.contents[0].text)["asset"]["version"] == "v1"
                    changed = await session.call_tool(
                        "register_asset", {"kind": "recipe", "asset": {**asset, "epochs": 2}}
                    )
                    assert changed.isError
                    assert "new version" in changed.content[0].text
                    missing = await session.call_tool("get_run", {"run_id": "missing"})
                    assert missing.isError and "404" in missing.content[0].text
                    traversal = await session.call_tool("get_run", {"run_id": "../health"})
                    assert traversal.isError
                    assert app.state.platform.repo.list("runs") == []

    asyncio.run(exercise())


def test_invalid_resources_never_reach_api_and_transport_errors_are_actionable():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("secret URL must not be echoed")

    async def exercise():
        server = create_server(
            client_factory=lambda: httpx.AsyncClient(
                transport=httpx.MockTransport(handler), base_url="http://localhost"
            )
        )
        request = {
            "request_id": "bad",
            "work_item_id": "work",
            "task": "train",
            "recipe": {"name": "r", "version": "v1"},
            "resources": {"device": "cuda"},
        }
        with pytest.raises(Exception, match="GPU UUID"):
            await server.call_tool("prepare_run_plan", {"request": request})
        assert not calls
        with pytest.raises(Exception, match="outcome is unknown") as error:
            await server.call_tool("platform_health", {})
        assert "secret URL" not in str(error.value)

    asyncio.run(exercise())


def test_asset_documentation_never_changes_payload_and_bounds_readme(tmp_path):
    root = tmp_path / "model"
    root.mkdir()
    readme = root / "README.md"
    content = "模型说明\n" * 30000
    readme.write_text(content)
    asset = {
        "name": "cnn",
        "version": "v1",
        "path": str(root),
        "metadata": {"format": "huggingface.PreTrainedModel"},
    }
    description = describe_asset("model", asset, tmp_path)
    assert description["readme_truncated"]
    assert "local_files_only=True" in description["documentation"]
    assert readme.read_text() == content
    assert describe_asset("model", asset, tmp_path / "other")["readme"] is None


@pytest.mark.parametrize("existing_readme", [False, True])
def test_publication_documentation_preserves_immutable_payload(
    tmp_path, monkeypatch, existing_readme
):
    from types import SimpleNamespace

    source = tmp_path / "model"
    source.mkdir()
    (source / "config.json").write_text('{"model_type":"mnist"}')
    if existing_readme:
        (source / "README.md").write_text("# 原始模型说明\n不可改写。")
    original = manifest(source)
    asset = {
        "name": "cnn",
        "version": "v1",
        "id": "model:cnn:v1",
        "path": str(source),
        "files": original,
        "checksum": manifest_hash(original),
        "metadata": {"format": "huggingface.PreTrainedModel"},
    }
    platform = Platform(Settings(tmp_path, tmp_path, tmp_path / "state"))

    def upload(command, **kwargs):
        from pathlib import Path

        staging = Path(json.loads(kwargs["input"])["folder"])
        card = (staging / "README.md").read_text()
        assert (
            card == "# 原始模型说明\n不可改写。" if existing_readme else "from_pretrained" in card
        )
        portable = json.loads((staging / "ninna-asset.json").read_text())["asset"]
        assert portable["files"] == original and portable["checksum"] == asset["checksum"]
        assert manifest(source) == original
        return SimpleNamespace(returncode=0, stdout='{"revision":"commit-123"}\n')

    monkeypatch.setattr("ninna.services.hub.subprocess.run", upload)
    try:
        result = platform.hub._publish(
            {
                "id": "transfer-unit",
                "request": {
                    "kind": "model",
                    "asset": asset,
                    "repo_id": "test/cnn",
                    "private": True,
                },
            },
            {"endpoint": "http://hub.invalid", "token": ""},
        )
        assert result["checksum"] == asset["checksum"]
        assert manifest(source) == original
    finally:
        platform.close()


def test_mcp_compact_context_and_filtered_catalogs(tmp_path):
    async def exercise():
        app = create_app(Settings(tmp_path, tmp_path, tmp_path / "state"), serve_frontend=False)
        p = app.state.platform
        store = p.work.store
        work = store.create(
            "work_item", {"status": "ACTIVE", "ready": True}, "compact-owner", "test"
        )
        plan = store.create(
            "plan",
            {
                "work_item_id": work["id"],
                "status": "READY",
                "recipe": {"name": "r", "version": "v1"},
                "prepared": {"files": {"heavy-source": "hash"}},
                "request": {"large": "payload"},
            },
            "compact-plan",
            "test",
        )
        env = store.create(
            "environment",
            {"name": "preludio2 ready", "ready": True, "latest_revision_id": "published"},
            "compact-env",
            "test",
        )
        store.create("environment", {"name": "other draft", "ready": False}, "draft-env", "test")
        store.create(
            "environment_revision",
            {"environment_id": env["id"], "status": "PUBLISHED", "files": {"heavy-source": "hash"}},
            "compact-rev",
            "test",
        )
        store.create(
            "asset",
            {
                "name": "AVA model",
                "kind": "model",
                "path": str(tmp_path),
                "files": {"config.json": "hash"},
                "repo_id": "owner/vad",
            },
            "compact-asset",
            "test",
        )

        def factory(**kwargs):
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), follow_redirects=True, **kwargs
            )

        async with app.state.mcp.session_manager.run(), factory() as client:
            async with streamable_http_client("http://localhost/mcp/", http_client=client) as (
                r,
                w,
                _,
            ):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    result = await s.call_tool(
                        "list_environments", {"query": "preludio2", "published_only": True}
                    )
                    assert not result.isError
                    items = result.structuredContent["items"]
                    assert len(items) == 1
                    assert items[0]["id"] == env["id"] and "files" not in items[0]["revisions"][0]
                    result = await s.call_tool(
                        "list_asset_revisions", {"kind": "model", "query": "AVA"}
                    )
                    asset = result.structuredContent["items"][0]
                    assert asset["file_count"] == 1 and "files" not in asset
                    result = await s.call_tool("get_work_context", {"work_item_id": work["id"]})
                    assert result.structuredContent["plans"][0]["id"] == plan["id"]
                    assert "prepared" not in result.structuredContent["plans"][0]
                    full = await s.call_tool(
                        "get_work_context", {"work_item_id": work["id"], "compact": False}
                    )
                    assert full.structuredContent["plans"][0]["prepared"]["files"] == {
                        "heavy-source": "hash"
                    }
        p.close()

    asyncio.run(exercise())
