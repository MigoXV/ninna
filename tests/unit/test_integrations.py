import json
import stat

import pytest

from ninna.config import Settings
from ninna.domain.integrations import HubSettingsUpdate
from ninna.services.integrations import IntegrationSettings
from ninna.services.platform import Platform


def test_hub_settings_are_optional_and_credentials_stay_private(tmp_path):
    settings = IntegrationSettings(tmp_path)
    assert settings.public()["hub"]["enabled"] is False
    settings.update(
        HubSettingsUpdate(
            enabled=True,
            endpoint="http://hub.example:28080",
            namespace="ninna",
            token="test-secret",
        )
    )
    assert "test-secret" not in json.dumps(settings.public())
    assert stat.S_IMODE(settings.path.stat().st_mode) == 0o600
    settings.update(
        HubSettingsUpdate(
            enabled=False, endpoint="http://hub.example:28080", namespace="ninna", token=""
        )
    )
    assert settings.read()["hub"]["token"] == "test-secret"
    settings.update(
        HubSettingsUpdate(enabled=True, endpoint="http://another.example", namespace="ninna")
    )
    assert settings.read()["hub"]["token"] == ""
    with pytest.raises(ValueError):
        settings.update(
            HubSettingsUpdate(
                enabled=True, endpoint="http://user:password@example.com", namespace="ninna"
            )
        )


def test_real_aim_roundtrip_and_replay(tmp_path):
    platform = Platform(Settings(tmp_path, tmp_path, tmp_path / "state"))
    run = {
        "id": "run-unit-aim",
        "status": "RUNNING",
        "created_at": "2026-09-25T00:00:00Z",
        "started_at": None,
        "finished_at": None,
        "training_spec": {"recipe": {"name": "test", "version": "v1"}},
        "execution_spec": {},
        "container_id": "real-execution-reference",
        "exit_code": None,
        "failure_reason": None,
        "metrics": None,
    }
    run["assets"] = {
        "recipe": {"optimizer": {"name": "Adam", "params": {"lr": 0.001}}, "epochs": 3}
    }
    platform.repo.save("runs", run)
    output = platform.output(run["id"])
    output.mkdir(parents=True)
    (output / "events.jsonl").write_text(
        '{"epoch":1,"train_loss":2.0}\n{"epoch":3,"train_loss":0.25}\n'
    )
    first = platform.tracking.sync(run)
    assert platform.tracking.sync(run)["aim_hash"] == first["aim_hash"]
    run.update(status="CANCELLED", exit_code=137, finished_at="2026-09-25T00:01:00Z")
    platform.repo.save("runs", run)
    platform.tracking.sync(run)
    curves = platform.tracking.metrics(run["id"])
    assert curves["source"] == "aim"
    assert curves["series"][0]["points"] == [{"step": 1, "value": 2.0}, {"step": 3, "value": 0.25}]
    assert platform.tracking.experiments()[0]["status"] == "CANCELLED"
    assert platform.tracking.experiments()[0]["recipe"]["optimizer"]["name"] == "Adam"
    assert (tmp_path / "state/aim/.aim/meta").exists()
    platform.close()


def test_hub_disabled_rejects_transfers_and_layout(tmp_path):
    platform = Platform(Settings(tmp_path, tmp_path, tmp_path / "state"))
    with pytest.raises(ValueError, match="未启用"):
        platform.hub.config()
    with pytest.raises(ValueError, match="Hugging Face"):
        platform.hub.validate_layout("model", tmp_path)
    platform.close()
