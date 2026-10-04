import hashlib

import pytest
from fastapi.testclient import TestClient

from ninna.config import Settings
from ninna.web.app import create_app
from ninna.work.store import Conflict


@pytest.fixture
def platform(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path, tmp_path / "state"), serve_frontend=False)
    yield app.state.platform, TestClient(app)
    app.state.platform.close()


def test_multiple_sources_idempotency_and_conflicts(platform):
    p, client = platform
    payload = {"name": "内网", "endpoint": "http://internal.example", "request_id": "one"}
    first = client.post("/api/v2/sources", json=payload)
    assert first.status_code == 201
    assert client.post("/api/v2/sources", json=payload).json()["id"] == first.json()["id"]
    assert client.post("/api/v2/sources", json={**payload, "name": "changed"}).status_code == 409
    second = client.post(
        "/api/v2/sources",
        json={**payload, "request_id": "two", "endpoint": "https://huggingface.co"},
    )
    assert second.json()["id"] != first.json()["id"]
    assert len(client.get("/api/v2/sources").json()) == 2
    assert (
        client.post(
            "/api/v2/sources",
            json={**payload, "request_id": "bad", "endpoint": "http://user:secret@example.com"},
        ).status_code
        == 400
    )
    assert p.repo.list("runs") == []


def test_download_is_not_registration_and_survives_source_disable(platform, tmp_path):
    p, client = platform
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "arbitrary.txt").write_text("not a Ninna asset")
    value = {
        "request_id": "download",
        "kind": "dataset",
        "name": "raw-data",
        "local_path": str(raw),
    }
    job = client.post("/api/v2/assets/acquire", json=value).json()
    p.work.tick()
    result = client.get("/api/v2/jobs/" + job["id"]).json()
    assert result["status"] == "SUCCESS", result
    asset = result["result"]
    assert asset["local_status"] == "DOWNLOADED"
    assert asset["compatibility"] == "NOT_CHECKED"
    assert p.repo.assets("dataset") == []
    assert client.post("/api/v2/assets/acquire", json=value).json()["id"] == job["id"]
    (__import__("pathlib").Path(asset["path"]) / "arbitrary.txt").write_text("changed")
    assert (
        client.get(f"/api/v2/assets/{asset['id']}?verify=true").json()["local_status"] == "CORRUPT"
    )


def test_stream_upload_hash_and_sealing(platform):
    _, client = platform
    key = client.post(
        "/api/v2/uploads", json={"request_id": "upload", "kind": "model", "name": "model"}
    ).json()["id"]
    payload = b'{"model_type":"test"}'
    sha = hashlib.sha256(payload).hexdigest()
    endpoint = f"/api/v2/uploads/{key}/files"
    assert (
        client.put(
            endpoint, params={"path": "../escape", "sha256": sha}, content=payload
        ).status_code
        == 400
    )
    assert (
        client.put(
            endpoint, params={"path": "config.json", "sha256": "0" * 64}, content=payload
        ).status_code
        == 400
    )
    assert (
        client.put(
            endpoint, params={"path": "config.json", "sha256": sha}, content=payload
        ).status_code
        == 200
    )
    result = client.post(f"/api/v2/uploads/{key}/complete", json={"request_id": "complete"})
    assert result.status_code == 200, result.text
    assert result.json()["files"] == {"config.json": sha}
    assert (
        client.put(endpoint, params={"path": "another", "sha256": sha}, content=payload).status_code
        == 409
    )
    assert (
        client.post(f"/api/v2/uploads/{key}/complete", json={"request_id": "complete"}).json()["id"]
        == result.json()["id"]
    )


def test_migration_preserves_original_bytes(platform, tmp_path):
    p, _ = platform
    root = tmp_path / "model"
    root.mkdir()
    (root / "weights").write_text("weights")
    from ninna.services.assets import manifest

    old = p.repo.register(
        "model", {"name": "old", "version": "v1", "path": str(root), "files": manifest(root)}
    )
    with p.repo.connection() as db:
        before = db.execute("SELECT body FROM assets").fetchall()
    assert p.work.migrate()["assets"] == 1
    assert p.work.store.list("asset") == []
    p.work.migrate(True)
    p.work.migrate(True)
    with p.repo.connection() as db:
        assert db.execute("SELECT body FROM assets").fetchall() == before
    assert len(p.work.store.list("asset")) == 1
    assert p.work.assets.resolve(p.work.store.list("asset")[0]["id"])[1] == {
        "name": old["name"],
        "version": old["version"],
    }


def test_workspace_optimistic_edits_and_event_cursor(platform):
    p, client = platform
    owner = p.work.store.create("environment", {"name": "draft", "ready": True}, "env", "test")
    key = owner["id"]
    root = p.work.environments.workspace(key)
    root.mkdir(parents=True)
    endpoint = f"/api/v2/workspaces/{key}/files"
    value = {"request_id": "edit", "path": "train.py", "content": "print(1)"}
    created = client.post(endpoint, json=value)
    assert created.status_code == 200
    sha = created.json()["sha256"]
    assert client.post(endpoint, json=value).json() == created.json()
    assert (
        client.post(
            endpoint, json={**value, "request_id": "conflict", "content": "print(2)"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            endpoint,
            json={**value, "request_id": "next", "content": "print(2)", "expected_sha256": sha},
        ).status_code
        == 200
    )
    (root / "link").symlink_to(root.parent)
    assert (
        client.post(
            endpoint, json={**value, "request_id": "escape", "path": "link/out"}
        ).status_code
        == 400
    )
    events = client.get("/api/v2/events").json()
    assert events["items"]
    assert client.get("/api/v2/events", params={"after": events["cursor"]}).json()["items"] == []


def test_store_optimistic_update(platform):
    p, _ = platform
    value = p.work.store.create("work_item", {"title": "work"}, "work", "test")
    p.work.store.put("work_item", {**value, "title": "new"}, expected_version=1)
    with pytest.raises(Conflict):
        p.work.store.put("work_item", value, expected_version=1)
    assert p.work.store.get("work_item", value["id"])["title"] == "new"


def test_restart_does_not_replay_unknown_preparation(platform):
    p, _ = platform
    job = p.work.job("initialize", {"owner_id": "missing"}, "init")
    p.work.store.put("job", {**job, "status": "RUNNING"})
    p.work.start()
    p.work.close()
    assert p.work.store.get("job", job["id"])["status"] == "FAILED"


def test_submit_freezes_workspace_and_retries_after_context_changes(platform):
    p, client = platform
    work = p.work.store.create("work_item", {"status": "ACTIVE", "ready": True}, "owner", "test")
    plan = p.work.store.create(
        "plan",
        {
            "work_item_id": work["id"],
            "status": "READY",
            "prepared": {"workspace_version": work["version"]},
        },
        "plan",
        "test",
    )
    request = {"plan_id": plan["id"], "request_id": "submit"}
    first = client.post("/api/v2/runs", json=request)
    assert first.status_code == 202
    p.work.store.put("work_item", {**work, "summary": "new context"})
    assert client.post("/api/v2/runs", json=request).json()["id"] == first.json()["id"]
    assert (
        client.post("/api/v2/runs", json={**request, "request_id": "different"}).status_code == 409
    )
    assert len(p.work.store.list("job")) == 1


def test_registered_asset_is_visible_once_before_and_after_migration(platform, tmp_path):
    p, client = platform
    root = tmp_path / "registered-model"
    root.mkdir()
    (root / "config.json").write_text("{}")
    from ninna.services.assets import manifest

    response = client.post(
        "/api/v2/definitions/model",
        json={
            "name": "registered",
            "version": "v1",
            "path": str(root),
            "files": manifest(root),
            "architecture": {},
            "initialization": {},
            "parameter_count": None,
        },
    )
    assert response.status_code == 201, response.text
    values = client.get("/api/v2/assets").json()
    assert len(values) == 1
    assert values[0]["legacy_ref"] == {"name": "registered", "version": "v1"}
    p.work.migrate(True)
    assert len(p.work.store.list("asset")) == 1


def test_source_update_cannot_move_legacy_credentials(platform):
    p, client = platform
    source = p.work.store.create(
        "source",
        {
            "name": "internal",
            "endpoint": "https://original.example",
            "protocol": "hf",
            "enabled": True,
            "token_env": None,
            "legacy_credentials": True,
        },
        "original",
        "test",
    )
    request = {
        "request_id": "move",
        "expected_version": source["version"],
        "name": "changed",
        "endpoint": "https://another.example",
        "enabled": True,
    }
    updated = client.post("/api/v2/sources/" + source["id"], json=request)
    assert updated.status_code == 200
    assert updated.json()["legacy_credentials"] is False
    invalid = client.post(
        "/api/v2/sources/" + source["id"],
        json={
            **request,
            "request_id": "invalid",
            "expected_version": updated.json()["version"],
            "endpoint": "https://another.example?secret=x",
        },
    )
    assert invalid.status_code == 400


def test_progress_summary_does_not_invalidate_prepared_execution(platform):
    p, client = platform
    work = p.work.store.create(
        "work_item",
        {"status": "ACTIVE", "ready": True, "workspace_generation": 3},
        "summary-owner",
        "test",
    )
    plan = p.work.store.create(
        "plan",
        {"work_item_id": work["id"], "status": "READY", "prepared": {"workspace_version": 3}},
        "summary-plan",
        "test",
    )
    updated = client.post(
        "/api/v2/work-items/" + work["id"],
        json={
            "request_id": "summary",
            "expected_version": work["version"],
            "summary": "检查通过，准备提交",
        },
    )
    assert updated.status_code == 200
    assert (
        client.post(
            "/api/v2/runs", json={"request_id": "submit-summary", "plan_id": plan["id"]}
        ).status_code
        == 202
    )


def test_source_disable_keeps_existing_download_available(platform, tmp_path):
    p, client = platform
    source = client.post(
        "/api/v2/sources",
        json={
            "request_id": "connected-source",
            "name": "source",
            "endpoint": "https://hosting.example",
        },
    ).json()
    staging = tmp_path / "downloaded"
    staging.mkdir()
    (staging / "config.json").write_text('{"model_type":"bert"}')
    asset = p.work.assets.adopt(
        staging,
        {"name": "model", "kind": "model"},
        {"source_id": source["id"], "repo_id": "team/model", "revision": "fixed-commit"},
    )
    response = client.post(
        "/api/v2/sources/" + source["id"],
        json={
            "request_id": "disable",
            "name": source["name"],
            "endpoint": source["endpoint"],
            "enabled": False,
            "expected_version": source["version"],
        },
    )
    assert response.status_code == 200
    assert client.get("/api/v2/sources/" + source["id"] + "/status").json()["status"] == "DISABLED"
    assert (
        client.get("/api/v2/assets/" + asset["id"], params={"verify": True}).json()["local_status"]
        == "DOWNLOADED"
    )
    assert p.work.assets.resolve(asset["id"])[0] == "model"
