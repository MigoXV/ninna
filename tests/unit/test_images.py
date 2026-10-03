from types import SimpleNamespace
from unittest.mock import Mock

import docker
import pytest

from ninna.domain.schemas import ImageRequest, RuntimeRequest
from ninna.services.images import ImageService
from ninna.storage.repository import Repository


@pytest.fixture
def service(tmp_path):
    image = SimpleNamespace(
        id="sha256:" + "a" * 64,
        attrs={
            "Os": "linux",
            "Architecture": "amd64",
            "RepoTags": ["demo:v1"],
            "RepoDigests": [],
            "Size": 42,
        },
    )
    engine = Mock()
    engine.images.get.return_value = image
    platform = SimpleNamespace(
        repo=Repository(tmp_path / "db.sqlite3"), docker=engine, runtime_validator=Mock()
    )
    platform.runtime_validator.validate.return_value = {
        "versions": {"torch": "2"},
        "image_id": image.id,
    }
    instance = ImageService(platform)
    yield instance
    instance.close()


def request(**kwargs):
    return ImageRequest(name="demo", version="v1", source="demo:v1", **kwargs)


def test_registration_uses_inspected_identity_and_preserves_missing_asset(service):
    asset = service.register(request())
    assert asset["image_id"] == "sha256:" + "a" * 64
    assert asset["tags"] == ["demo:v1"]
    with pytest.raises(ValueError, match="版本已存在"):
        service.register(request())
    service.docker.images.get.side_effect = docker.errors.ImageNotFound("missing")
    assert service.availability(asset)["status"] == "MISSING"
    assert service.repo.asset("image", asset) == asset


def test_runtime_resolves_identity_not_tag(service):
    asset = service.register(request())
    runtime = service.register_runtime(
        RuntimeRequest(name="runtime", version="v1", image_ref={"name": "demo", "version": "v1"})
    )
    service.resolve_runtime(runtime)
    service.docker.images.get.assert_called_with(asset["image_id"])
    assert "image_id" not in runtime
    service.platform.runtime_validator.validate.side_effect = ValueError("missing HF dependencies")
    with pytest.raises(ValueError, match="dependencies"):
        service.register_runtime(
            RuntimeRequest(name="bad", version="v1", image_ref={"name": "demo", "version": "v1"})
        )
    assert len(service.repo.assets("runtime")) == 1


def test_pull_pins_digest_and_commits_asset(service):
    service.docker.api.inspect_distribution.return_value = {
        "Descriptor": {"digest": "sha256:" + "b" * 64}
    }
    service.docker.api.pull.return_value = iter([{"id": "abcd", "status": "Download complete"}])
    job = service.submit(request())
    service.close()
    stored = service.repo.get("image_pulls", job["id"])
    assert stored["status"] == "SUCCESS"
    assert stored["resolved_reference"] == "demo@sha256:" + "b" * 64
    service.docker.api.pull.assert_called_once_with(
        stored["resolved_reference"], stream=True, decode=True
    )
    assert service.repo.asset("image", request().model_dump())["pull_id"] == job["id"]


def test_failed_pull_preserves_evidence_without_credentials(service):
    service.docker.api.inspect_distribution.side_effect = docker.errors.APIError(
        "secret-password", response=SimpleNamespace(status_code=401)
    )
    job = service.submit(request())
    service.close()
    stored = service.repo.get("image_pulls", job["id"])
    assert stored["status"] == "FAILED"
    assert "secret-password" not in str(stored)
    assert "凭据" in stored["error"]
    assert not service.repo.assets("image")


def test_recovery_does_not_retry_mutable_tag(service):
    job = {
        "id": "interrupted",
        "created_at": "2026-09-25",
        "status": "RUNNING",
        "request": request().model_dump(),
        "resolved_reference": None,
    }
    service.repo.save("image_pulls", job)
    service.recover()
    assert service.repo.get("image_pulls", job["id"])["status"] == "FAILED"
    service.docker.api.pull.assert_not_called()


@pytest.mark.parametrize(
    "source", ["https://user:password@registry/image", "user:password@registry/image"]
)
def test_source_rejects_credentials(source):
    with pytest.raises(ValueError):
        ImageRequest(name="demo", version="v1", source=source)
