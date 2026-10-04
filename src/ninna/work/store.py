"""Additive SQLite storage; never rewrites legacy assets or sealed runs."""

from __future__ import annotations

import hashlib
import json
import threading
import uuid

from ninna.storage.repository import now


class Conflict(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Store:
    def __init__(self, repository):
        self.repo = repository
        self.lock = threading.RLock()
        with self.repo.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS work_schema (version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO work_schema VALUES (2);
                CREATE TABLE IF NOT EXISTS work_objects (
                    kind TEXT, id TEXT, body TEXT NOT NULL, PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS work_requests (
                    request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                    kind TEXT NOT NULL, object_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS work_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_id TEXT NOT NULL, body TEXT NOT NULL);
            """)

    def get(self, kind, key):
        with self.repo.connection() as db:
            row = db.execute(
                "SELECT body FROM work_objects WHERE kind=? AND id=?", (kind, key)
            ).fetchone()
        if row is None:
            raise KeyError(f"{kind}/{key}")
        return json.loads(row[0])

    def list(self, kind):
        with self.repo.connection() as db:
            rows = db.execute(
                "SELECT body FROM work_objects WHERE kind=? ORDER BY rowid DESC", (kind,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def put(self, kind, value, expected_version=None):
        with self.lock, self.repo.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT body FROM work_objects WHERE kind=? AND id=?", (kind, value["id"])
            ).fetchone()
            version = json.loads(previous[0]).get("version", 0) if previous else 0
            if expected_version is not None and expected_version != version:
                raise Conflict("对象已改变，请重新读取后再提交。")
            value = {**value, "version": version + 1, "updated_at": now()}
            db.execute(
                "INSERT OR REPLACE INTO work_objects VALUES (?,?,?)",
                (kind, value["id"], json.dumps(value)),
            )
            event = {
                "kind": kind,
                "object_id": value["id"],
                "at": now(),
                "status": value.get("status"),
                "version": value["version"],
            }
            db.execute(
                "INSERT INTO work_events(object_id,body) VALUES (?,?)",
                (value["id"], json.dumps(event)),
            )
        return value

    def create(self, kind, payload, request_id, scope, prefix=None):
        """Atomically publish both the object and its retry identity before a worker sees it."""
        fingerprint = digest({"scope": scope, "payload": payload})
        with self.lock, self.repo.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT fingerprint,kind,object_id FROM work_requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if old:
                if old[0] != fingerprint:
                    raise Conflict("request_id 已用于不同请求，请保留原请求或使用新 ID。")
                return json.loads(
                    db.execute(
                        "SELECT body FROM work_objects WHERE kind=? AND id=?", (old[1], old[2])
                    ).fetchone()[0]
                )
            key = (prefix or kind) + "-" + uuid.uuid4().hex[:16]
            value = {**payload, "id": key, "created_at": now(), "updated_at": now(), "version": 1}
            db.execute("INSERT INTO work_objects VALUES (?,?,?)", (kind, key, json.dumps(value)))
            db.execute(
                "INSERT INTO work_requests VALUES (?,?,?,?)", (request_id, fingerprint, kind, key)
            )
            event = {
                "kind": kind,
                "object_id": key,
                "at": now(),
                "status": value.get("status"),
                "version": 1,
            }
            db.execute(
                "INSERT INTO work_events(object_id,body) VALUES (?,?)", (key, json.dumps(event))
            )
        return value

    def has_request(self, request_id):
        with self.repo.connection() as db:
            return (
                db.execute(
                    "SELECT 1 FROM work_requests WHERE request_id=?", (request_id,)
                ).fetchone()
                is not None
            )

    def events(self, after=0, object_id=None):
        with self.repo.connection() as db:
            rows = db.execute(
                "SELECT sequence,body FROM work_events WHERE sequence>? "
                + ("AND object_id=? " if object_id else "")
                + "ORDER BY sequence LIMIT 200",
                (after, object_id) if object_id else (after,),
            ).fetchall()
        return {
            "items": [{"cursor": row[0], **json.loads(row[1])} for row in rows],
            "cursor": rows[-1][0] if rows else after,
        }
