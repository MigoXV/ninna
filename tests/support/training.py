"""Developer-only real Docker regression helpers, never imported by the application."""

import json
import time

import docker
from docker.types import Mount


def default_request(recipe="mnist-adam", version="v1", snapshot="current"):
    return {
        "project_id": "mnist-tests",
        "training_spec": {
            "dataset": {"name": "mnist", "version": "v2"},
            "model": {"name": "mnist-cnn", "version": "v2"},
            "recipe": {"name": recipe, "version": version},
        },
        "execution_spec": {
            "runtime": {"name": "mnist-pytorch-runtime", "version": "v3"},
            "workspace": {"name": "mnist-hf", "snapshot": snapshot},
            "resources": {"device": "cpu", "gpu_count": 0, "cpu_threads": 4, "memory_mb": 4096},
        },
    }


def ensure_project(client):
    response = client.get("/api/projects/mnist-tests")
    if response.status_code == 404:
        client.post(
            "/api/projects", json={"name": "mnist-tests", "description": "开发回归测试"}
        ).raise_for_status()
    else:
        response.raise_for_status()


def certify(client, quick=False):
    """Submit through the running platform; reload outputs in a separate Docker container."""
    ensure_project(client)
    response = client.post("/api/initialize")
    response.raise_for_status()
    conversion = response.json()["conversion"]
    assert (
        conversion["all_images_and_labels_equal"]
        and conversion["preprocessing_exact"]
        and conversion["logits_exact"]
    )
    snap = client.post("/api/workspaces/mnist-hf/snapshots")
    snap.raise_for_status()
    report = {"status": "PASS", "checks": [], "run_ids": []}

    def check(name, condition, evidence=None):
        assert condition, (name, evidence)
        report["checks"].append({"name": name, "status": "PASS", "evidence": evidence})

    for recipe in ("mnist-adam", "mnist-sgd"):
        response = client.post(
            "/api/runs",
            json=default_request(recipe, "quick-v1" if quick else "v1", snap.json()["snapshot"]),
        )
        response.raise_for_status()
        key = response.json()["id"]
        report["run_ids"].append(key)
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            run = client.get(f"/api/runs/{key}").json()
            if run["status"] in {"SUCCESS", "FAILED", "CANCELLED"}:
                break
            time.sleep(1)
        check(recipe + ": Run SUCCESS", run["status"] == "SUCCESS", run.get("failure_reason"))
        context = client.get(f"/api/runs/{key}/diagnostics").json()
        engine = docker.from_env()
        container = engine.containers.get(run["container_id"])
        mounts = {m["Destination"]: m for m in container.attrs["Mounts"]}
        check(
            recipe + ": Training in container",
            context["process"]["docker_env"]
            and context["process"]["run_id"] == key
            and bool(context["process-observation"]["Processes"]),
        )
        check(
            recipe + ": Dataset and workspace mounted",
            all(
                path in mounts and mounts[path]["RW"] is False
                for path in ("/dataset", "/workspace")
            ),
        )
        check(recipe + ": Logs collected", bool(context["stdout"]))
        checkpoint = client.get(f"/api/runs/{key}/artifacts/checkpoint.pt")
        check(
            recipe + ": Checkpoint saved",
            checkpoint.status_code == 200 and len(checkpoint.content) > 10000,
        )
        verifier = engine.containers.create(
            run["assets"]["runtime"]["image_id"],
            ["python", "-u", "/workspace/verify.py"],
            working_dir="/workspace",
            mounts=[
                Mount(path, item["Source"], type="bind", read_only=True)
                for path, item in mounts.items()
            ],
            network_disabled=True,
            mem_limit="4g",
            nano_cpus=4 * 10**9,
        )
        verifier.start()
        result = verifier.wait(timeout=600)
        logs = verifier.logs().decode()
        check(recipe + ": Checkpoint reload", result["StatusCode"] == 0, logs[-2000:])
        verified = json.loads(logs.strip().splitlines()[-1])
        check(
            recipe + ": HF model reload and inference",
            verified["hf_reload"]
            and verified["hf_auto_model_reload"]
            and verified["hf_logits_exact"],
            verified,
        )
        metrics = run["metrics"]
        check(
            recipe + ": Model updated",
            metrics["initial_model_hash"]
            != metrics["trained_model_hash"]
            == verified["trained_model_hash"],
        )
        check(recipe + ": Loss decreased", metrics["final_loss"] < metrics["initial_loss"])
        check(
            recipe + ": Test accuracy",
            verified["test_accuracy"] > (0.95 if quick else 0.98)
            and abs(verified["test_accuracy"] - metrics["test_accuracy"]) < 1e-9,
            verified["test_accuracy"],
        )
    return report
