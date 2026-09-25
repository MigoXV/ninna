"""Opt-in acceptance against the configured real KohakuHub, Docker and Aim SDK."""

import os
import time
import uuid

import httpx
import pytest

from ninna.services.certification import default_request

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("NINNA_HUB_INTEGRATION") != "1", reason="Requires configured real KohakuHub"
    ),
]


def wait_record(client, table, key, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if table == "runs":
            record = client.get(f"/api/runs/{key}").json()
        else:
            record = next(r for r in client.get("/api/hub/transfers").json() if r["id"] == key)
        if record["status"] in {"SUCCESS", "FAILED", "CANCELLED"}:
            assert record["status"] == "SUCCESS", record
            return record
        time.sleep(1)
    pytest.fail(f"Timeout waiting for {table}/{key}")


def submit(client, endpoint, payload):
    response = client.post(endpoint, json=payload)
    response.raise_for_status()
    return response.json()


def test_hub_to_training_to_hub_and_aim():
    with httpx.Client(
        base_url=os.environ.get("NINNA_API_URL", "http://127.0.0.1:8000"), timeout=180
    ) as client:
        config = client.get("/api/integrations").json()
        assert config["hub"]["enabled"] and config["aim"]["enabled"]
        assert "token" not in config["hub"]
        assert client.get("/api/hub/status").json()["status"] == "CONNECTED"
        namespace = config["hub"]["namespace"]
        version = "central-" + uuid.uuid4().hex[:8]
        published = {}
        for kind, name in [("dataset", "mnist"), ("model", "mnist-cnn")]:
            job = submit(
                client,
                "/api/hub/publish",
                {
                    "kind": kind,
                    "name": name,
                    "version": "v2",
                    "repo_id": f"{namespace}/{name}",
                    "private": True,
                },
            )
            published[kind] = wait_record(client, "transfers", job["id"])["result"]
            job = submit(
                client,
                "/api/hub/import",
                {
                    "kind": kind,
                    "name": name,
                    "version": version,
                    "repo_id": f"{namespace}/{name}",
                    "revision": published[kind]["revision"],
                },
            )
            downloaded = wait_record(client, "transfers", job["id"])["result"]
            assert downloaded["checksum"] == published[kind]["checksum"]
        request = default_request(version="quick-v1")
        request["training_spec"]["dataset"]["version"] = version
        request["training_spec"]["model"]["version"] = version
        run = wait_record(client, "runs", submit(client, "/api/runs", request)["id"])
        assert run["metrics"]["test_accuracy"] > 0.95
        assert run["runtime_validation"]["versions"]["transformers"]
        assert all(
            run["assets"][kind]["metadata"]["hub"]["revision"] for kind in ("model", "dataset")
        )
        asset = submit(client, f"/api/runs/{run['id']}/promote", {"version": version + "-trained"})
        result = wait_record(
            client,
            "transfers",
            submit(
                client,
                "/api/hub/publish",
                {
                    "kind": "model",
                    "name": asset["name"],
                    "version": asset["version"],
                    "repo_id": f"{namespace}/mnist-cnn",
                    "private": True,
                },
            )["id"],
        )
        imported = wait_record(
            client,
            "transfers",
            submit(
                client,
                "/api/hub/import",
                {
                    "kind": "model",
                    "name": "mnist-cnn",
                    "version": version + "-returned",
                    "repo_id": f"{namespace}/mnist-cnn",
                    "revision": result["result"]["revision"],
                },
            )["id"],
        )
        assert imported["result"]["checksum"] == asset["checksum"]
        # Moving main must not change the earlier input commit.
        original = wait_record(
            client,
            "transfers",
            submit(
                client,
                "/api/hub/import",
                {
                    "kind": "model",
                    "name": "mnist-cnn",
                    "version": version + "-original",
                    "repo_id": f"{namespace}/mnist-cnn",
                    "revision": published["model"]["revision"],
                },
            )["id"],
        )
        assert original["result"]["checksum"] == published["model"]["checksum"]
        assert original["result"]["checksum"] != imported["result"]["checksum"]
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            response = client.get(f"/api/experiments/{run['id']}/metrics")
            experiments = client.get("/api/experiments").json()["runs"]
            experiment = next((item for item in experiments if item["id"] == run["id"]), None)
            if response.status_code == 200 and experiment and experiment["status"] == "SUCCESS":
                curves = response.json()
                break
            time.sleep(1)
        else:
            pytest.fail("Aim did not record the completed Docker training")
        assert curves["source"] == "aim"
        loss = next(s for s in curves["series"] if s["name"] == "train_loss")
        assert loss["points"] == [{"step": 1, "value": run["metrics"]["train_loss"][0]}]


def test_non_hf_runtime_cannot_create_training_or_register():
    with httpx.Client(
        base_url=os.environ.get("NINNA_API_URL", "http://127.0.0.1:8000"), timeout=180
    ) as client:
        runtimes = client.get("/api/assets/runtime").json()
        legacy = next((r for r in runtimes if r["version"] == "v1"), None)
        if legacy is None:
            pytest.skip("No historical non-HF image in this installation")
        count = len(client.get("/api/runs").json())
        request = default_request()
        request["execution_spec"]["runtime"]["version"] = "v1"
        response = client.post("/api/runs", json=request)
        assert response.status_code == 400 and "HF" in response.json()["detail"]
        assert len(client.get("/api/runs").json()) == count
        forged = {
            **legacy,
            "name": "fake-hf",
            "version": "v1",
            "metadata": {"transformers": "4", "datasets": "4"},
        }
        forged.pop("id", None)
        response = client.post("/api/assets/runtime", json=forged)
        assert response.status_code == 400 and "HF" in response.json()["detail"]


def test_optional_hub_offline_training_and_aim_backfill():
    with httpx.Client(
        base_url=os.environ.get("NINNA_API_URL", "http://127.0.0.1:8000"), timeout=180
    ) as client:
        previous = client.get("/api/integrations").json()
        hub = {key: previous["hub"][key] for key in ["enabled", "endpoint", "namespace"]}
        try:
            submit(
                client,
                "/api/integrations",
                {"hub": {**hub, "enabled": False}, "aim": {"enabled": False}},
            )
            rejected = client.post(
                "/api/hub/publish",
                json={
                    "kind": "model",
                    "name": "mnist-cnn",
                    "version": "v2",
                    "repo_id": hub["namespace"] + "/mnist-cnn",
                },
            )
            assert rejected.status_code == 400
            run = wait_record(
                client,
                "runs",
                submit(client, "/api/runs", default_request(version="quick-v1"))["id"],
            )
            assert run["metrics"]["test_accuracy"] > 0.95
        finally:
            submit(client, "/api/integrations", {"hub": hub, "aim": previous["aim"]})
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            data = client.get("/api/experiments").json()
            if any(
                item["id"] == run["id"] and item["status"] == "SUCCESS" for item in data["runs"]
            ):
                break
            time.sleep(1)
        else:
            pytest.fail("Aim did not backfill metrics after re-enabling")
        metrics = client.get(f"/api/experiments/{run['id']}/metrics").json()
        assert metrics["source"] == "aim" and metrics["series"]
