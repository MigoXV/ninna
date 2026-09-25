"""Aim SDK adapter. Ninna owns the UI and reads curves back from Aim storage."""

from __future__ import annotations

import hashlib
import json
import math
import threading

from ninna.storage.repository import now


class AimTracking:
    def __init__(self, platform):
        self.platform = platform
        self.store = platform.repo
        self.path = platform.settings.state / "aim"
        self.lock = threading.RLock()
        self.aim_repo = None
        self.indexer = None
        self.stop_event = threading.Event()
        self.thread = None
        self.error = None

    def _open(self):
        if self.aim_repo is None:
            from aim import Repo
            from aim.sdk.index_manager import RepoIndexManager

            self.aim_repo = Repo(str(self.path), init=True)
            # Aim 3.29 SDK queries use a metadata index normally maintained by Aim's UI.
            # Maintain that index synchronously, without running or embedding its UI.
            self.indexer = RepoIndexManager.get_index_manager(self.aim_repo)
        return self.aim_repo

    def start(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="ninna-aim")
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=30)

    def status(self):
        return {
            "enabled": self.platform.integrations.read()["aim"]["enabled"],
            "engine": "aim",
            "version": "3.29.1",
            "repo": str(self.path),
            "error": self.error,
            "tracked_runs": len(self.store.list("tracking")),
        }

    def _loop(self):
        while not self.stop_event.is_set():
            if self.platform.integrations.read()["aim"]["enabled"]:
                for run in reversed(self.store.list("runs")):
                    if self.stop_event.is_set():
                        break
                    try:
                        self.sync(run)
                        self.error = None
                    except Exception as exc:
                        self.error = f"Aim 同步失败：{type(exc).__name__}: {str(exc)[:300]}"
                        break
            self.stop_event.wait(2)

    def sync(self, run):
        from aim import Run

        events = self.platform.metric_events(run["id"])
        signature = hashlib.sha256(
            json.dumps([2, run, events], sort_keys=True).encode()
        ).hexdigest()
        with self.lock:
            try:
                record = self.store.get("tracking", run["id"])
                if record.get("signature") == signature:
                    return record
            except KeyError:
                record = {"id": run["id"], "created_at": now(), "aim_hash": None, "signature": None}
            repo = self._open()
            tracked = Run(
                record["aim_hash"],
                repo=repo,
                experiment="Ninna",
                system_tracking_interval=None,
                log_system_params=False,
                capture_terminal_logs=False,
            )
            record["aim_hash"] = tracked.hash
            self.store.save("tracking", record)
            try:
                tracked["ninna"] = {
                    key: run[key]
                    for key in [
                        "id",
                        "status",
                        "created_at",
                        "started_at",
                        "finished_at",
                        "training_spec",
                        "execution_spec",
                        "container_id",
                        "exit_code",
                        "failure_reason",
                    ]
                }
                assets = run.get("assets", {})
                recipe = assets.get("recipe", {})
                tracked["recipe"] = {
                    key: recipe[key]
                    for key in (
                        "name",
                        "version",
                        "training_loop",
                        "loss",
                        "optimizer",
                        "scheduler",
                        "epochs",
                        "batch_size",
                        "gradient_accumulation",
                        "freeze",
                        "seed",
                    )
                    if key in recipe
                }
                tracked["provenance"] = {
                    "dataset_checksum": assets.get("dataset", {}).get("checksum"),
                    "model_checksum": assets.get("model", {}).get("checksum"),
                    "runtime_image_id": assets.get("runtime", {}).get("image_id"),
                    "workspace_snapshot": assets.get("workspace", {}).get("snapshot"),
                    "git_commit": assets.get("workspace", {}).get("git_commit"),
                }
                tracked["summary"] = {
                    key: value
                    for key, value in (run.get("metrics") or {}).items()
                    if key not in {"history", "train_loss"}
                }
                for event in events:
                    for name in ("train_loss", "test_loss", "test_accuracy", "lr", "elapsed_time"):
                        value = event.get(name)
                        if isinstance(value, (int, float)) and math.isfinite(value):
                            tracked.track(
                                value,
                                name=name,
                                step=int(event["epoch"]),
                                epoch=int(event["epoch"]),
                            )
            finally:
                tracked.close()
            self.indexer.index(record["aim_hash"])
            repo.container_pool.clear()
            record.update(signature=signature, synced_at=now())
            self.store.save("tracking", record)
            return record

    def experiments(self):
        with self.lock:
            if not self.path.exists():
                return []
            repo = self._open()
            repo.container_pool.clear()
            result = []
            for run in repo.iter_runs():
                params = run.get("ninna", default=None)
                if params:
                    result.append(
                        {
                            **params,
                            "aim_hash": run.hash,
                            "summary": run.get("summary", default={}),
                            "recipe": run.get("recipe", default={}),
                            "provenance": run.get("provenance", default={}),
                        }
                    )
            return sorted(result, key=lambda value: value["created_at"], reverse=True)

    def metrics(self, key):
        from aim import Run

        with self.lock:
            record = self.store.get("tracking", key)
            repo = self._open()
            repo.container_pool.clear()
            run = Run(record["aim_hash"], repo=repo, read_only=True)
            series = []
            for metric in run.metrics():
                steps, columns = metric.data.items_list()
                values = columns[0]
                series.append(
                    {
                        "name": metric.name,
                        "context": metric.context.to_dict(),
                        "points": [
                            {"step": int(step), "value": float(value)}
                            for step, value in zip(steps, values)
                        ],
                    }
                )
            return {
                "run_id": key,
                "aim_hash": record["aim_hash"],
                "source": "aim",
                "synced_at": record.get("synced_at"),
                "series": series,
            }
