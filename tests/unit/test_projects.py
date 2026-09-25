import sqlite3

import pytest
from fastapi.testclient import TestClient

from ninna.config import Settings
from ninna.domain.schemas import CreateProject
from ninna.storage.repository import Repository
from ninna.web.app import create_app


def test_projects_persist_and_reject_duplicate_names(tmp_path):
    repo = Repository(tmp_path / "db.sqlite3")
    project = repo.create_project(
        CreateProject(name="image-classification", description="图像分类")
    )
    with pytest.raises(ValueError, match="already exists"):
        repo.create_project(CreateProject(name=project["name"]))
    assert Repository(repo.path).get("projects", project["id"]) == project
    with pytest.raises(ValueError):
        CreateProject(name="../escape")


def test_historical_membership_preserves_execution_evidence(tmp_path):
    repo = Repository(tmp_path / "db.sqlite3")
    record = {
        "id": "old-run",
        "status": "SUCCESS",
        "created_at": "2026",
        "metrics": {"test_accuracy": 0.98},
    }
    repo.save("runs", record)
    with sqlite3.connect(repo.path) as db:
        original = db.execute("SELECT body FROM runs").fetchone()[0]
    migrated = Repository(repo.path)
    assert migrated.project_runs("legacy") == [record]
    assert migrated.get("runs", "old-run") == record
    with sqlite3.connect(repo.path) as db:
        assert db.execute("SELECT body FROM runs").fetchone()[0] == original
    assert len(Repository(repo.path).list("projects")) == 1


def test_project_api_isolation_and_removed_certification(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path, tmp_path / "state"), serve_frontend=False)
    client = TestClient(app)
    for name in ("first", "second"):
        assert client.post("/api/projects", json={"name": name}).status_code == 201
        app.state.platform.repo.save(
            "runs", {"id": name, "project_id": name, "created_at": "2026", "status": "SUCCESS"}
        )
    assert client.post("/api/projects", json={"name": "first"}).status_code == 400
    assert [r["id"] for r in client.get("/api/projects/first/runs").json()] == ["first"]
    assert [r["id"] for r in client.get("/api/runs?project_id=second").json()] == ["second"]
    assert client.get("/api/projects/missing/runs").status_code == 404
    assert client.get("/api/projects").json()[0]["run_count"] == 1
    assert client.get("/api/certifications").status_code == 404
    assert "/api/certifications" not in client.get("/openapi.json").json()["paths"]


def test_run_requires_project_and_checks_it_before_execution(tmp_path):
    from tests.support.training import default_request

    app = create_app(Settings(tmp_path, tmp_path, tmp_path / "state"), serve_frontend=False)
    client = TestClient(app)
    request = default_request()
    request.pop("project_id", None)
    assert client.post("/api/runs", json=request).status_code == 422
    request["project_id"] = "missing"
    assert client.post("/api/runs", json=request).status_code == 404
    assert app.state.platform._docker is None
