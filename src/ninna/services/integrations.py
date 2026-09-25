"""Server-side integration settings. Credentials never enter Run specs or responses."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit


class IntegrationSettings:
    def __init__(self, state: Path):
        self.path = state / "integrations.json"
        self.lock = threading.RLock()

    def read(self):
        with self.lock:
            value = {
                "hub": {
                    "enabled": False,
                    "endpoint": "http://192.168.0.222:28080",
                    "token": "",
                    "namespace": "ninna-platform",
                },
                "aim": {"enabled": True},
            }
            if self.path.exists():
                stored = json.loads(self.path.read_text())
                for key in value:
                    value[key].update(stored.get(key, {}))
            return value

    def public(self):
        value = self.read()
        value["hub"]["token_configured"] = bool(value["hub"].pop("token", ""))
        return value

    def update(self, hub=None, aim=None):
        with self.lock:
            value = self.read()
            if hub is not None:
                updates = hub.model_dump(exclude_none=True)
                endpoint = updates.get("endpoint", value["hub"]["endpoint"]).rstrip("/")
                parsed = urlsplit(endpoint)
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError(
                        "Hub endpoint must be an HTTP(S) origin without credentials or query"
                    )
                updates["endpoint"] = endpoint
                if updates.get("token") == "":
                    updates.pop("token")  # A blank browser field preserves the existing secret.
                if endpoint != value["hub"]["endpoint"] and not updates.get("token"):
                    value["hub"]["token"] = ""  # Never send an old credential to a new endpoint.
                value["hub"].update(updates)
            if aim is not None:
                value["aim"].update(aim.model_dump())
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                json.dump(value, stream)
            temporary.replace(self.path)
            return self.public()
