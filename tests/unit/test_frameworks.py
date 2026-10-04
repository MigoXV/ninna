import json

import pytest
from fastapi.testclient import TestClient

from ninna.config import Settings
from ninna.domain.frameworks import FrameworkManifest, ImportFramework
from ninna.domain.schemas import Resources
from ninna.services.assets import checksum, snapshot
from ninna.services.frameworks import relative_file
from ninna.web.app import create_app


def test_docker_transport_timeout_keeps_run_reconcilable(monkeypatch, tmp_path):
    from requests.exceptions import ReadTimeout
    from ninna.services.platform import Platform

    platform = Platform(Settings(tmp_path, tmp_path, tmp_path))
    run = {"id": "run-timeout", "status": "RUNNING"}
    updates = []
    monkeypatch.setattr(platform.repo, "list", lambda _: [run])
    monkeypatch.setattr(platform.repo, "update_run", lambda key, **values: updates.append(values))

    def collect(_):
        platform.stop_event.set()
        raise ReadTimeout("Docker daemon is temporarily busy")

    monkeypatch.setattr(platform, "_collect", collect)
    platform._loop()
    assert updates == [{"monitor_error": "Docker daemon is temporarily busy"}]


def test_explicit_single_gpu_and_cpu_boundaries():
    assert Resources(device="cuda", gpu_count=1, gpu_ids=["GPU-test"]).gpu_ids == ["GPU-test"]
    for values in (
        {"device": "cuda"},
        {"device": "cpu", "gpu_count": 1},
        {"device": "cuda", "gpu_count": 1, "gpu_ids": ["0"]},
        {"device": "cuda", "gpu_count": 2, "gpu_ids": ["GPU-a", "GPU-b"]},
    ):
        with pytest.raises(ValueError):
            Resources(**values)


def test_manifest_rejects_escaping_skill_and_unknown_operation():
    value = dict(
        name="example",
        version="v1",
        skill=".agents/skills/example/SKILL.md",
        tasks={
            "task": {
                "description": "test",
                "operations": {"train": {"argv": ["python", "-m", "example"]}},
            }
        },
    )
    FrameworkManifest.model_validate(value)
    with pytest.raises(ValueError):
        FrameworkManifest.model_validate({**value, "skill": "../SKILL.md"})
    value["tasks"]["task"]["operations"] = {"shell": {"argv": ["bash"]}}
    with pytest.raises(ValueError):
        FrameworkManifest.model_validate(value)


@pytest.mark.parametrize("name", [".", "..", "../outside", "/absolute", ""])
def test_image_import_rejects_unsafe_workspace_names(name):
    with pytest.raises(ValueError):
        ImportFramework(image={"name": "example", "version": "v1"}, workspace_name=name)


def test_workspace_excludes_payload_but_includes_agent_contract(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for name in [
        "AGENTS.md",
        ".agents/skills/demo/SKILL.md",
        "src/demo.py",
        "data-bin/large",
        "model-bin/weight",
        ".env.local",
        "outputs/run",
    ]:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test")
    _, target, files = snapshot(source, tmp_path / "snapshots")
    assert set(files) == {"AGENTS.md", ".agents/skills/demo/SKILL.md", "src/demo.py"}
    assert (target / "AGENTS.md").is_file()


def test_nested_artifacts_are_downloadable_but_links_cannot_escape(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path, tmp_path / "state"), serve_frontend=False)
    p = app.state.platform
    output = p.output("run-test")
    (output / "checkpoints").mkdir(parents=True)
    artifact = output / "checkpoints/last.ckpt"
    artifact.write_bytes(b"checkpoint")
    p.repo.save(
        "runs",
        {"id": "run-test", "created_at": "now", "artifacts": [{"name": "checkpoints/last.ckpt"}]},
    )
    client = TestClient(app)
    assert client.get("/api/runs/run-test/artifacts/checkpoints/last.ckpt").content == b"checkpoint"
    assert client.get("/api/runs/run-test/artifacts/unlisted").status_code == 404
    (output / "outside").symlink_to(tmp_path)
    for name in ("../escape", "/etc/passwd", "outside/secret"):
        with pytest.raises(ValueError):
            relative_file(output, name)


def test_task_result_uses_task_evidence_not_accuracy_or_loss_decrease(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path, tmp_path / "state"), serve_frontend=False)
    p = app.state.platform
    run = {
        "id": "run-test",
        "created_at": "now",
        "status": "RUNNING",
        "events": [],
        "cancel_requested": False,
        "task_spec": {"operation": "train"},
        "operation_contract": {"required_artifacts": ["checkpoint"]},
    }
    p.repo.save("runs", run)
    output = p.output(run["id"])
    output.mkdir(parents=True)
    checkpoint = output / "last.ckpt"
    checkpoint.write_bytes(b"evidence")
    (output / "result.json").write_text(
        json.dumps(
            {
                "protocol_version": 1,
                "operation": "train",
                "metrics": {"val_wer": 0.7},
                "quality": {"status": "failed"},
                "evidence": {
                    "optimizer_steps": 2,
                    "initial_trainable_hash": "a" * 64,
                    "final_trainable_hash": "b" * 64,
                },
                "artifacts": [
                    {"path": "last.ckpt", "kind": "checkpoint", "sha256": checksum(checkpoint)}
                ],
            }
        )
    )
    completed = p.frameworks.finish(run, {}, 0)
    assert completed["status"] == "SUCCESS"
    assert completed["metadata"]["quality"]["status"] == "failed"
    with pytest.raises(ValueError, match="immutable"):
        p.repo.update_run(run["id"], metrics={})


def test_missing_real_optimizer_evidence_fails(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path, tmp_path / "state"), serve_frontend=False)
    p = app.state.platform
    run = {
        "id": "empty",
        "created_at": "now",
        "status": "RUNNING",
        "events": [],
        "cancel_requested": False,
        "task_spec": {"operation": "train"},
        "operation_contract": {"required_artifacts": []},
    }
    p.repo.save("runs", run)
    output = p.output("empty")
    output.mkdir(parents=True)
    (output / "result.json").write_text(
        json.dumps({"protocol_version": 1, "operation": "train", "artifacts": []})
    )
    assert p.frameworks.finish(run, {}, 0)["status"] == "FAILED"
