"""Real Docker image lifecycle through the deployed API, no mocked training."""

import io
import os
import time
import uuid

import docker
import httpx
import pytest

pytestmark = pytest.mark.integration


def test_image_identity_tag_drift_and_deleted_image(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text("{}")
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path))
    engine = docker.from_env()
    suffix = uuid.uuid4().hex[:8]
    tag = f"ninna-image-test:{suffix}"
    # Distinct tiny images make cleanup safe; no production image is removed.
    first, _ = engine.images.build(
        fileobj=io.BytesIO(f"FROM scratch\nLABEL ninna.test={suffix}-a\n".encode()), tag=tag
    )
    second = None
    with httpx.Client(
        base_url=os.environ.get("NINNA_API_URL", "http://127.0.0.1:8000"), timeout=180
    ) as client:
        try:
            request = {"name": "image-test-" + suffix, "version": "v1", "source": tag}
            response = client.post("/api/assets/image", json=request)
            response.raise_for_status()
            asset = response.json()
            assert asset["image_id"] == first.id
            second, _ = engine.images.build(
                fileobj=io.BytesIO(f"FROM scratch\nLABEL ninna.test={suffix}-b\n".encode()), tag=tag
            )
            path = f"/api/assets/image/{request['name']}/v1"
            detail = client.get(path).json()
            assert detail["asset"]["image_id"] == first.id != second.id
            assert detail["availability"]["status"] == "AVAILABLE"
            runtime = client.post(
                "/api/assets/runtime",
                json={
                    "name": request["name"],
                    "version": "v1",
                    "image_ref": {"name": request["name"], "version": "v1"},
                },
            )
            assert runtime.status_code == 400  # scratch cannot satisfy training dependencies
            engine.images.remove(first.id, force=True)
            detail = client.get(path).json()
            assert detail["availability"]["status"] == "MISSING"
            assert detail["asset"] == asset
        finally:
            for image in [first, second]:
                if image:
                    try:
                        engine.images.remove(image.id, force=True)
                    except docker.errors.ImageNotFound:
                        pass


def test_remote_pull_persists_digest():
    with httpx.Client(
        base_url=os.environ.get("NINNA_API_URL", "http://127.0.0.1:8000"), timeout=180
    ) as client:
        response = client.post(
            "/api/image-pulls",
            json={
                "name": "alpine-test-" + uuid.uuid4().hex[:8],
                "version": "v1",
                "source": os.environ.get("NINNA_TEST_PULL_IMAGE", "alpine:3.21"),
            },
        )
        response.raise_for_status()
        job = response.json()
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            job = client.get("/api/image-pulls/" + job["id"]).json()
            if job["status"] in {"SUCCESS", "FAILED"}:
                break
            time.sleep(1)
        assert job["status"] == "SUCCESS", job
        assert "@sha256:" in job["resolved_reference"]
        asset = client.get(f"/api/assets/image/{job['request']['name']}/v1").json()["asset"]
        assert asset["pull_id"] == job["id"]
        assert docker.from_env().images.get(job["resolved_reference"]).id == asset["image_id"]
