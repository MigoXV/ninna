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
                    assert "start_certification" not in tools
                    assert "get_certification" not in tools
                    project = await session.call_tool("create_project", {"name": "mcp-project"})
                    assert not project.isError
                    projects = await session.call_tool("list_projects", {})
                    assert projects.structuredContent["projects"][0]["id"] == "mcp-project"
                    assert "project_id" in tools["create_run"].inputSchema["required"]
                    assert tools["describe_asset"].annotations.readOnlyHint
                    assert not tools["create_run"].annotations.idempotentHint
                    assert tools["cancel_run"].annotations.destructiveHint
                    assert {"training_spec", "execution_spec"} <= set(
                        tools["create_run"].inputSchema["properties"]
                    )
                    guide = await session.read_resource("ninna://guide")
                    assert "TrainingSpec" in guide.contents[0].text
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
        from tests.support.training import default_request

        request = default_request()
        request["execution_spec"]["resources"]["device"] = "cuda"
        import pytest

        with pytest.raises(Exception, match="CPU only"):
            await server.call_tool("create_run", request)
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
