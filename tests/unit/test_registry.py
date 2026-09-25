from pathlib import Path

import pytest

from ninna.config import Settings
from ninna.domain.schemas import CreateRun
from ninna.services.assets import snapshot
from tests.support.training import default_request
from ninna.storage.repository import Repository


@pytest.fixture
def repo(tmp_path):
    return Repository(tmp_path / "test.sqlite3")


@pytest.mark.parametrize("kind", ["dataset", "model", "recipe", "runtime", "workspace"])
def test_asset_registry(repo, kind):
    asset = {"name": "asset", "version": "v1", "metadata": {"count": 1}}
    stored = repo.register(kind, asset)
    assert repo.asset(kind, asset) == stored
    assert repo.register(kind, asset) == stored
    with pytest.raises(ValueError, match="different content"):
        repo.register(kind, {**asset, "metadata": {"count": 2}})
    assert len(repo.assets(kind)) == 1


def test_run_state_machine(repo):
    repo.save("runs", {"id": "one", "status": "CREATED", "events": [], "created_at": "2026"})
    with pytest.raises(ValueError, match="Invalid transition"):
        repo.update_run("one", status="SUCCESS")
    for status in ["PREPARING", "RUNNING", "SUCCESS"]:
        repo.update_run("one", status=status)
    with pytest.raises(ValueError, match="immutable"):
        repo.update_run("one", metrics={})
    assert [e["to"] for e in repo.get("runs", "one")["events"]] == [
        "PREPARING",
        "RUNNING",
        "SUCCESS",
    ]


def test_snapshot_includes_untracked_and_does_not_change(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "untracked.py").write_text("before")
    (source / ".env").write_text("secret")
    key, path, files = snapshot(source, tmp_path / "snapshots")
    (source / "untracked.py").write_text("after")
    assert (path / "untracked.py").read_text() == "before"
    assert ".env" not in files
    assert snapshot(source, tmp_path / "snapshots")[0] != key


def test_snapshot_rejects_links(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "link").symlink_to("/etc/passwd")
    with pytest.raises(ValueError, match="symlinks"):
        snapshot(source, tmp_path / "snapshots")


def test_host_path_mapping():
    settings = Settings(
        Path("/workspace/apps/ninna"), Path("/host/repos/apps/ninna"), Path("/tmp/state")
    )
    assert (
        settings.host_path(Path("/workspace/apps/ninna/data-bin/mnist"))
        == "/host/repos/apps/ninna/data-bin/mnist"
    )
    with pytest.raises(ValueError):
        settings.host_path(Path("/other/mnist"))


def test_create_run_schema_rejects_gpu_and_unknown_fields():
    request = default_request()
    assert CreateRun.model_validate(request).execution_spec.resources.device == "cpu"
    request["execution_spec"]["resources"]["gpu_count"] = 1
    with pytest.raises(ValueError, match="CPU only"):
        CreateRun.model_validate(request)
    request = default_request()
    request["training_spec"]["docker"] = "wrong-boundary"
    with pytest.raises(ValueError):
        CreateRun.model_validate(request)


def test_worker_lock_prevents_two_executors(tmp_path):
    from ninna.services.platform import Platform

    settings = Settings(tmp_path, tmp_path, tmp_path / "state")
    first, second = Platform(settings), Platform(settings)
    first.start()
    try:
        with pytest.raises(RuntimeError, match="Another Ninna executor"):
            second.start()
    finally:
        first.close()
    second.start()
    second.close()


def test_create_run_captures_snapshot_and_cancellation(tmp_path, monkeypatch):
    from ninna.services.platform import Platform

    platform = Platform(Settings(tmp_path, tmp_path, tmp_path / "state"))
    monkeypatch.setattr(
        platform.runtime_validator, "validate", lambda asset: {"test": "domain-only"}
    )
    source = tmp_path / "workspace"
    source.mkdir()
    (source / "train.py").write_text("print('initial')")
    for kind, name in [
        ("dataset", "mnist"),
        ("model", "mnist-cnn"),
        ("recipe", "mnist-adam"),
        ("runtime", "mnist-pytorch-runtime"),
    ]:
        platform.repo.register(
            kind,
            {
                "name": name,
                "version": "v3" if kind == "runtime" else "v1" if kind == "recipe" else "v2",
            },
        )
    platform.repo.register(
        "workspace",
        {"name": "mnist-hf", "version": "v1", "path": str(source), "entrypoint": "train.py"},
    )
    from ninna.domain.schemas import CreateProject

    platform.repo.create_project(CreateProject(name="mnist-tests"))
    run = platform.create_run(CreateRun.model_validate(default_request()))
    (source / "train.py").write_text("print('changed')")
    assert run["execution_spec"]["workspace"]["snapshot"] != "current"
    assert (
        Path(run["assets"]["workspace"]["snapshot_path"]) / "train.py"
    ).read_text() == "print('initial')"
    assert (platform.output(run["id"]) / "config/run.json").exists()
    cancelled = platform.cancel(run["id"])
    assert cancelled["status"] == "CANCELLED" and cancelled["container_id"] is None
    assert platform.cancel(run["id"]) == cancelled
    platform.repo.create_project(CreateProject(name="another-project"))
    wrong = {**default_request(), "project_id": "another-project", "parent_run_id": run["id"]}
    with pytest.raises(ValueError, match="parent.*project"):
        platform.create_run(CreateRun.model_validate(wrong))
    retry = platform.create_run(
        CreateRun.model_validate({**default_request(), "parent_run_id": run["id"]})
    )
    assert retry["project_id"] == run["project_id"] == "mnist-tests"
    assert retry["id"] != run["id"]
    assert platform.repo.get("runs", run["id"]) == cancelled
