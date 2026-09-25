"""Real Docker tests. The running platform is the sole owner of the execution queue."""

import copy
import os
import time
import uuid
from pathlib import Path

import docker
import httpx
import pytest

from ninna.services.certification import default_request

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    with httpx.Client(
        base_url=os.environ.get("NINNA_API_URL", "http://127.0.0.1:8000"), timeout=600
    ) as client:
        response = client.post("/api/initialize")
        response.raise_for_status()
        yield client


def wait(client, key, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get("/api/runs/" + key).json()
        if run["status"] in {"SUCCESS", "FAILED", "CANCELLED"}:
            return run
        time.sleep(1)
    pytest.fail("Run timed out: " + key)


@pytest.fixture(scope="module")
def certified(client):
    response = client.post("/api/certifications", json={"quick": False})
    response.raise_for_status()
    key = response.json()["id"]
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        report = client.get("/api/certifications/" + key).json()
        if report["status"] != "RUNNING":
            assert report["status"] == "PASS", report
            return report
        time.sleep(2)
    pytest.fail("Certification timed out")


def test_mnist_e2e(certified):
    assert len(certified["run_ids"]) == 2
    assert all(c["status"] == "PASS" for c in certified["checks"])


@pytest.mark.parametrize("kind", ["dataset", "model", "recipe", "runtime"])
def test_registry(client, kind):
    assert client.get("/api/assets/" + kind).json()


@pytest.mark.parametrize("index", [0, 1], ids=["recipe_a", "recipe_b"])
def test_recipe_a_and_b(client, certified, index):
    run = client.get("/api/runs/" + certified["run_ids"][index]).json()
    assert run["status"] == "SUCCESS"
    assert run["metrics"]["test_accuracy"] > 0.98


def test_docker_container_created_and_mounts(client, certified):
    run = client.get("/api/runs/" + certified["run_ids"][0]).json()
    container = docker.from_env().containers.get(run["container_id"])
    assert container.attrs["Config"]["Labels"]["ninna.run_id"] == run["id"]
    mounts = {m["Destination"]: m for m in container.attrs["Mounts"]}
    assert mounts["/dataset"]["RW"] is False
    assert mounts["/workspace"]["RW"] is False
    assert mounts["/output"]["RW"] is True
    assert container.attrs["HostConfig"]["NetworkMode"] == "none"


def test_model_hash_changes_and_checkpoint_reload(client, certified):
    for key in certified["run_ids"]:
        run = client.get("/api/runs/" + key).json()
        assert run["metadata"]["initial_model_hash"] != run["metadata"]["trained_model_hash"]
        checkpoint = client.get(f"/api/runs/{key}/artifacts/checkpoint.pt")
        assert checkpoint.status_code == 200 and len(checkpoint.content) > 10000
    assert (
        sum("Checkpoint reload" in c["name"] and c["status"] == "PASS" for c in certified["checks"])
        == 2
    )


def test_recipe_decoupling(client, certified):
    a, b = [client.get("/api/runs/" + key).json() for key in certified["run_ids"]]
    left, right = copy.deepcopy(a["training_spec"]), copy.deepcopy(b["training_spec"])
    assert left.pop("recipe") != right.pop("recipe")
    assert left == right
    assert a["execution_spec"] == b["execution_spec"]
    assert a["metadata"]["initial_model_hash"] == b["metadata"]["initial_model_hash"]


def register_failure_workspace(client, content):
    root = Path(__file__).resolve().parents[2]
    name = "failure-" + uuid.uuid4().hex[:8]
    path = root / "tmp-workspace" / name
    path.mkdir(parents=True)
    (path / "train.py").write_text(content)
    asset = {"name": name, "version": "v1", "path": str(path), "entrypoint": "train.py"}
    client.post("/api/assets/workspace", json=asset).raise_for_status()
    request = default_request(version="quick-v1")
    request["execution_spec"]["workspace"]["name"] = name
    response = client.post("/api/runs", json=request)
    response.raise_for_status()
    return response.json()


def test_failed_run_logs_preserved(client):
    run = register_failure_workspace(
        client, "print('starting failure case', flush=True)\nimport package_that_does_not_exist\n"
    )
    run = wait(client, run["id"])
    assert run["status"] == "FAILED" and run["exit_code"] != 0
    context = client.get(f"/api/runs/{run['id']}/diagnostics").json()
    assert "package_that_does_not_exist" in context["stderr"]
    assert "starting failure case" in context["stdout"]
    assert context["container_id"] and context["training_spec"] and context["execution_spec"]
    assert context["assets"]["workspace"]["snapshot"]


def test_bad_recipe(client):
    recipe = client.get("/api/assets/recipe").json()[0]
    recipe = {
        **recipe,
        "name": "bad-" + uuid.uuid4().hex[:8],
        "optimizer": {"name": "Adam", "params": {"lr": -1}},
    }
    recipe.pop("id")
    client.post("/api/assets/recipe", json=recipe).raise_for_status()
    request = default_request()
    request["training_spec"]["recipe"] = {"name": recipe["name"], "version": recipe["version"]}
    run = client.post("/api/runs", json=request).json()
    run = wait(client, run["id"])
    assert run["status"] == "FAILED"
    assert (
        "Invalid learning rate" in client.get(f"/api/runs/{run['id']}/diagnostics").json()["stderr"]
    )


@pytest.mark.parametrize("platform_cancel", [True, False])
def test_interrupted_run(client, platform_cancel):
    run = register_failure_workspace(
        client, "import time\nprint('ready', flush=True)\ntime.sleep(300)\n"
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        run = client.get("/api/runs/" + run["id"]).json()
        if run["status"] == "RUNNING":
            break
        time.sleep(1)
    assert run["status"] == "RUNNING"
    if platform_cancel:
        client.post(f"/api/runs/{run['id']}/cancel").raise_for_status()
    else:
        docker.from_env().containers.get(run["container_id"]).stop(timeout=1)
    finished = wait(client, run["id"])
    assert finished["status"] == ("CANCELLED" if platform_cancel else "FAILED")
    assert finished["exit_code"] is not None


def test_model_artifact_reused(client, certified):
    key = certified["run_ids"][0]
    version = "trained-" + uuid.uuid4().hex[:8]
    asset = client.post(f"/api/runs/{key}/promote", json={"version": version})
    asset.raise_for_status()
    request = default_request(version="quick-v1")
    request["training_spec"]["model"]["version"] = version
    run = client.post("/api/runs", json=request).json()
    run = wait(client, run["id"])
    source = client.get("/api/runs/" + key).json()
    assert run["status"] == "SUCCESS"
    assert run["metadata"]["initial_model_hash"] == source["metadata"]["trained_model_hash"]


def test_platform_restart_recovers_container(client):
    containers = docker.from_env().containers.list(
        filters={
            "label": ["com.docker.compose.project=ninna", "com.docker.compose.service=platform"]
        }
    )
    if not containers:
        pytest.skip("Restart recovery scenario requires Compose deployment")
    run = register_failure_workspace(
        client, "import time\nprint('restart test ready', flush=True)\ntime.sleep(120)\n"
    )
    for _ in range(60):
        run = client.get("/api/runs/" + run["id"]).json()
        if run["status"] == "RUNNING":
            break
        time.sleep(1)
    assert run["status"] == "RUNNING"
    container_id = run["container_id"]
    containers[0].restart(timeout=10)
    for _ in range(60):
        try:
            response = client.get("/api/runs/" + run["id"])
            if response.status_code == 200:
                break
        except httpx.TransportError:
            pass
        time.sleep(1)
    resumed = response.json()
    assert resumed["container_id"] == container_id
    assert resumed["status"] == "RUNNING"
    client.post("/api/runs/" + run["id"] + "/cancel").raise_for_status()
    assert wait(client, run["id"])["status"] == "CANCELLED"


def test_hf_formats_and_inference_alignment(client, certified):
    datasets = client.get("/api/assets/dataset").json()
    dataset = next(
        asset for asset in datasets if asset["name"] == "mnist" and asset["version"] == "v2"
    )
    assert dataset["metadata"]["format"] == "huggingface.DatasetDict"
    assert dataset["metadata"]["conversion"]["all_images_and_labels_equal"]
    assert dataset["metadata"]["conversion"]["preprocessing_exact"]
    for key in certified["run_ids"]:
        run = client.get("/api/runs/" + key).json()
        assert run["assets"]["model"]["initial_checkpoint"] == "model.safetensors"
        assert run["assets"]["dataset"]["version"] == "v2"
        bundle = client.get(f"/api/runs/{key}/artifacts/model.tar.gz")
        assert bundle.status_code == 200
        import io
        import tarfile

        with tarfile.open(fileobj=io.BytesIO(bundle.content)) as archive:
            names = set(archive.getnames())
        assert {
            "model/config.json",
            "model/model.safetensors",
            "model/preprocessor_config.json",
        } <= names
    checks = [
        check for check in certified["checks"] if "HF model reload and inference" in check["name"]
    ]
    assert len(checks) == 2
    assert all(check["evidence"]["hf_logits_exact"] for check in checks)


def test_legacy_assets_remain_executable(client):
    request = default_request(version="quick-v1")
    for kind in ("dataset", "model"):
        request["training_spec"][kind]["version"] = "v1"
    request["execution_spec"]["runtime"]["version"] = "v1"
    request["execution_spec"]["workspace"]["name"] = "mnist"
    run = client.post("/api/runs", json=request)
    run.raise_for_status()
    finished = wait(client, run.json()["id"])
    assert finished["status"] == "SUCCESS"
    assert finished["metrics"]["test_accuracy"] > 0.95
