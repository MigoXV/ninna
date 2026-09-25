from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ninna.domain.schemas import TERMINAL, TRANSITIONS


def now():
    return datetime.now(timezone.utc).isoformat()


RECORD_TABLES = {"runs", "certifications", "hub_transfers", "tracking"}


class Repository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS assets (
                    kind TEXT, name TEXT, version TEXT, body TEXT NOT NULL,
                    PRIMARY KEY(kind,name,version));
                CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS certifications (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS hub_transfers (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tracking (id TEXT PRIMARY KEY, body TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=30)
            try:
                yield db
                db.commit()
            finally:
                db.close()

    def register(self, kind, asset):
        value = dict(asset)
        value.setdefault("id", f"{kind}:{value['name']}:{value['version']}")
        value.setdefault("metadata", {})
        encoded = json.dumps(value, sort_keys=True)
        with self.connection() as db:
            previous = db.execute(
                "SELECT body FROM assets WHERE kind=? AND name=? AND version=?",
                (kind, value["name"], value["version"]),
            ).fetchone()
            if previous and previous[0] != encoded:
                raise ValueError(
                    "Asset version already exists with different content; create a new version"
                )
            db.execute(
                "INSERT OR IGNORE INTO assets VALUES (?,?,?,?)",
                (kind, value["name"], value["version"], encoded),
            )
        return value

    def assets(self, kind):
        with self.connection() as db:
            return [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT body FROM assets WHERE kind=? ORDER BY name,version", (kind,)
                )
            ]

    def asset(self, kind, ref):
        with self.connection() as db:
            row = db.execute(
                "SELECT body FROM assets WHERE kind=? AND name=? AND version=?",
                (kind, ref["name"], ref["version"]),
            ).fetchone()
        if not row:
            raise ValueError(f"Unregistered {kind}: {ref['name']}/{ref['version']}")
        return json.loads(row[0])

    def save(self, table, value):
        if table not in RECORD_TABLES:
            raise ValueError("Unknown record type")
        with self.connection() as db:
            db.execute(
                f"INSERT OR REPLACE INTO {table} VALUES (?,?)",
                (value["id"], json.dumps(value, allow_nan=False)),
            )

    def get(self, table, key):
        if table not in RECORD_TABLES:
            raise ValueError("Unknown record type")
        with self.connection() as db:
            row = db.execute(f"SELECT body FROM {table} WHERE id=?", (key,)).fetchone()
        if not row:
            raise KeyError(key)
        return json.loads(row[0])

    def list(self, table):
        if table not in RECORD_TABLES:
            raise ValueError("Unknown record type")
        with self.connection() as db:
            values = [json.loads(row[0]) for row in db.execute(f"SELECT body FROM {table}")]
        return sorted(values, key=lambda v: v["created_at"], reverse=True)

    def update_run(self, key, **changes):
        with self.lock:
            run = self.get("runs", key)
            if run["status"] in TERMINAL:
                raise ValueError("Terminal Run is immutable")
            if "status" in changes and changes["status"] != run["status"]:
                target = changes["status"]
                if target not in TRANSITIONS.get(run["status"], set()):
                    raise ValueError(f"Invalid transition {run['status']} -> {target}")
                run["events"].append({"from": run["status"], "to": target, "at": now()})
            run.update(changes)
            self.save("runs", run)
            return run
