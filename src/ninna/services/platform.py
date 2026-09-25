from __future__ import annotations

import copy
import fcntl
import json
import logging
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import docker
from docker.types import Mount

from ninna.config import Settings
from ninna.domain.schemas import CreateRun, TERMINAL
from ninna.services.assets import checksum, manifest, manifest_hash, snapshot
from ninna.storage.repository import Repository, now

logger = logging.getLogger(__name__)


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))
    temporary.replace(path)


class Platform:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = Repository(settings.state / "ninna.sqlite3")
        self._docker = None
        self.stop_event = threading.Event()
        self.thread = None
        self.worker_lock = None
        self.operation_lock = threading.RLock()
        self.bootstrap_lock = threading.Lock()
        from ninna.services.integrations import IntegrationSettings
        from ninna.services.hub import HubService
        from ninna.services.tracking import AimTracking
        from ninna.services.runtime import HFRuntimeValidator

        self.integrations = IntegrationSettings(settings.state)
        self.hub = HubService(self)
        self.tracking = AimTracking(self)
        self.runtime_validator = HFRuntimeValidator(lambda: self.docker)

    @property
    def docker(self):
        if self._docker is None:
            self._docker = docker.from_env(timeout=30)
        return self._docker

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.worker_lock = (self.settings.state / "executor.lock").open("a")
        try:
            fcntl.flock(self.worker_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.worker_lock.close()
            self.worker_lock = None
            raise RuntimeError("Another Ninna executor owns this storage; run one platform process")
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="ninna-executor")
        self.thread.start()
        self.hub.recover()
        self.tracking.start()

    def close(self):
        self.tracking.close()
        self.hub.close()
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=35)
        if self.worker_lock and (not self.thread or not self.thread.is_alive()):
            fcntl.flock(self.worker_lock, fcntl.LOCK_UN)
            self.worker_lock.close()
            self.worker_lock = None

    def output(self, run_id):
        # Run IDs are resolved through the repository before exposing files.
        return self.settings.state / "runs" / run_id

    def health(self):
        try:
            self.docker.ping()
            docker_status = "available"
        except docker.errors.DockerException as exc:
            docker_status = str(exc)
        return {
            "docker": docker_status,
            "initialized": bool(self.repo.assets("workspace")),
            "runtime_available": bool(self.repo.assets("runtime")),
            "time": now(),
        }

    def initialize(self):
        from ninna.services.assets import initialize

        with self.bootstrap_lock:
            self.mount_probe()
            initialize(self)
            from ninna.services.huggingface import initialize_hf

            return initialize_hf(self)

    def mount_probe(self):
        path = self.settings.state / "mount-probe.txt"
        token = uuid.uuid4().hex
        path.write_text(token)
        image = self.docker.images.get(self.settings.runtime_image)
        result = self.docker.containers.run(
            image.id,
            [
                "python",
                "-c",
                "from pathlib import Path; print(Path('/probe/mount-probe.txt').read_text())",
            ],
            mounts=[
                Mount(
                    "/probe",
                    self.settings.host_path(self.settings.state),
                    type="bind",
                    read_only=True,
                )
            ],
            network_disabled=True,
            network_mode="none",
            remove=True,
        )
        if result.decode().strip() != token:
            raise ValueError("Docker mount probe failed: check NINNA_ROOT and NINNA_HOST_ROOT")

    def workspace_snapshot(self, name):
        with self.operation_lock:
            asset = self.repo.asset("workspace", {"name": name, "version": "v1"})
            key, path, files = snapshot(Path(asset["path"]), self.settings.state / "snapshots")
            info = {**asset, "snapshot": key, "snapshot_path": str(path), "files": files}
            try:
                commit = subprocess.run(
                    ["git", "-C", str(self.settings.root), "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
                info["git_commit"] = commit
            except (subprocess.SubprocessError, FileNotFoundError):
                info["git_commit"] = None
            write_json(self.settings.state / "snapshots" / (key + ".json"), info)
            return info

    def create_run(self, request: CreateRun):
        with self.operation_lock:
            training = request.training_spec.model_dump()
            execution = request.execution_spec.model_dump()
            assets = {kind: self.repo.asset(kind, ref) for kind, ref in training.items()}
            assets["runtime"] = self.repo.asset("runtime", execution["runtime"])
            runtime_evidence = self.runtime_validator.validate(assets["runtime"])
            workspace_ref = execution["workspace"]
            if workspace_ref["snapshot"] == "current":
                workspace = self.workspace_snapshot(workspace_ref["name"])
            else:
                key = workspace_ref["snapshot"]
                if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
                    raise ValueError("Invalid workspace snapshot ID")
                info = self.settings.state / "snapshots" / (key + ".json")
                if not info.exists():
                    raise ValueError("Workspace snapshot is unavailable")
                workspace = json.loads(info.read_text())
                if workspace["name"] != workspace_ref["name"]:
                    raise ValueError("Snapshot does not belong to requested workspace")
            assets["workspace"] = workspace
            execution["workspace"]["snapshot"] = workspace["snapshot"]
            if request.parent_run_id:
                self.repo.get("runs", request.parent_run_id)
            run_id = "run-" + uuid.uuid4().hex[:12]
            run = {
                "id": run_id,
                "run_id": run_id,
                "training_spec": training,
                "execution_spec": execution,
                "assets": assets,
                "status": "CREATED",
                "created_at": now(),
                "started_at": None,
                "finished_at": None,
                "container_id": None,
                "exit_code": None,
                "metrics": None,
                "failure_reason": None,
                "events": [],
                "cancel_requested": False,
                "parent_run_id": request.parent_run_id,
                "artifacts": [],
                "container_state": None,
                "metadata": {},
                "monitor_error": None,
                "runtime_validation": runtime_evidence,
            }
            output = self.output(run_id)
            output.mkdir(parents=True)
            (output / "config").mkdir()
            write_json(output / "config" / "run.json", run)
            for name in ["stdout.log", "stderr.log"]:
                (output / name).touch()
            write_json(output / "run.json", run)
            self.repo.save("runs", run)
            return run

    def mounts(self, run, output_read_only=False):
        assets = run["assets"]
        paths = [
            ("/dataset", Path(assets["dataset"]["path"]), True),
            ("/model", Path(assets["model"]["path"]), True),
            ("/workspace", Path(assets["workspace"]["snapshot_path"]), True),
            ("/config", self.output(run["id"]) / "config", True),
            ("/output", self.output(run["id"]), output_read_only),
        ]
        return [
            Mount(target, self.settings.host_path(source), type="bind", read_only=readonly)
            for target, source, readonly in paths
        ]

    def _prepare(self, run):
        key = run["id"]
        if run["status"] == "CREATED":
            run = self.repo.update_run(key, status="PREPARING")
        for kind in ["dataset", "model"]:
            asset = run["assets"][kind]
            if manifest(Path(asset["path"])) != asset["files"]:
                raise ValueError(f"{kind} asset checksum changed")
        workspace = run["assets"]["workspace"]
        if manifest(Path(workspace["snapshot_path"])) != workspace["files"]:
            raise ValueError("Workspace snapshot checksum changed")
        image_id = run["assets"]["runtime"]["image_id"]
        self.runtime_validator.validate(run["assets"]["runtime"])
        with self.operation_lock:
            run = self.repo.get("runs", key)
            if run["status"] in TERMINAL or run["cancel_requested"]:
                return
            try:
                container = self.docker.containers.get("ninna-" + key)
            except docker.errors.NotFound:
                resources = run["execution_spec"]["resources"]
                container = self.docker.containers.create(
                    image_id,
                    ["python", "-u", "/workspace/" + workspace["entrypoint"]],
                    name="ninna-" + key,
                    hostname=key,
                    working_dir="/workspace",
                    mounts=self.mounts(run),
                    network_disabled=True,
                    network_mode="none",
                    tty=False,
                    mem_limit=f"{resources['memory_mb']}m",
                    nano_cpus=resources["cpu_threads"] * 10**9,
                    environment={"PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1"},
                    labels={"ninna.run_id": key, "ninna.role": "training"},
                    log_config={"Type": "json-file", "Config": {}},
                )
            self.repo.update_run(key, container_id=container.id)
            container.reload()
            if container.status == "created":
                container.start()
            self.repo.update_run(key, status="RUNNING", started_at=now())

    def _collect(self, run):
        container = self.docker.containers.get(run["container_id"])
        container.reload()
        output = self.output(run["id"])
        for name, stdout in [("stdout.log", True), ("stderr.log", False)]:
            data = container.logs(stdout=stdout, stderr=not stdout)
            temporary = output / (name + ".tmp")
            temporary.write_bytes(data)
            temporary.replace(output / name)
        inspect = container.attrs
        write_json(output / "container.json", inspect)
        changes = {"container_state": inspect["State"], "monitor_error": None}
        if inspect["State"]["Running"]:
            try:
                processes = container.top()
                write_json(output / "process-observation.json", processes)
            except docker.errors.APIError:
                pass  # The process can exit between inspect and top.
            self.repo.update_run(run["id"], **changes)
            return
        if container.status not in {"exited", "dead"}:
            return
        with self.operation_lock:
            run = self.repo.get("runs", run["id"])
            if run["status"] in TERMINAL:
                return
            exit_code = inspect["State"]["ExitCode"]
            metrics = None
            reason = None
            status = "SUCCESS"
            if run["cancel_requested"]:
                status, reason = "CANCELLED", "Cancelled by platform request"
            elif exit_code != 0:
                status = "FAILED"
                reason = (
                    "Container OOM killed"
                    if inspect["State"].get("OOMKilled")
                    else f"Container exited with code {exit_code}"
                )
            else:
                try:
                    metrics = json.loads((output / "metrics.json").read_text())
                    required = {
                        "train_loss",
                        "final_train_loss",
                        "test_loss",
                        "test_accuracy",
                        "epochs",
                        "elapsed_time",
                        "initial_loss",
                        "final_loss",
                        "initial_model_hash",
                        "trained_model_hash",
                    }
                    if not required.issubset(metrics) or not (output / "checkpoint.pt").is_file():
                        raise ValueError("Required training outputs are missing")
                    if (
                        metrics["initial_model_hash"] == metrics["trained_model_hash"]
                        or metrics["final_loss"] >= metrics["initial_loss"]
                    ):
                        raise ValueError(
                            "Training evidence failed: weights unchanged or loss did not decrease"
                        )
                except (OSError, ValueError, KeyError) as exc:
                    status, reason = "FAILED", str(exc)
            if status == "FAILED":
                stderr = (output / "stderr.log").read_text(errors="replace").strip()
                if stderr:
                    reason += ": " + stderr.splitlines()[-1][:600]
            artifacts = [
                {"name": p.name, "size": p.stat().st_size, "sha256": checksum(p)}
                for p in sorted(output.iterdir())
                if p.is_file() and p.name != "run.json"
            ]
            metadata = (
                {
                    k: metrics[k]
                    for k in [
                        "initial_model_hash",
                        "trained_model_hash",
                        "initial_loss",
                        "final_loss",
                    ]
                }
                if metrics
                else {}
            )
            run = self.repo.update_run(
                run["id"],
                **changes,
                status=status,
                exit_code=exit_code,
                finished_at=now(),
                metrics=metrics,
                failure_reason=reason,
                artifacts=artifacts,
                metadata=metadata,
            )
            write_json(output / "run.json", run)

    def _loop(self):
        while not self.stop_event.is_set():
            active = [r for r in reversed(self.repo.list("runs")) if r["status"] not in TERMINAL]
            # Reconcile existing containers before taking another queued Run.
            running = [r for r in active if r["status"] in {"PREPARING", "RUNNING"}]
            candidates = running or active[:1]
            for run in candidates:
                try:
                    if run["status"] in {"CREATED", "PREPARING"}:
                        self._prepare(run)
                    else:
                        self._collect(run)
                except docker.errors.NotFound as exc:
                    self._fail(run["id"], f"Docker resource missing: {exc}")
                except docker.errors.APIError as exc:
                    if exc.status_code is not None and exc.status_code < 500:
                        self._fail(run["id"], f"Docker request rejected: {exc}")
                    else:
                        self.repo.update_run(run["id"], monitor_error=str(exc))
                except docker.errors.DockerException as exc:
                    try:
                        self.repo.update_run(run["id"], monitor_error=str(exc))
                    except ValueError:
                        pass
                    logger.warning("Docker monitoring error for %s: %s", run["id"], exc)
                except Exception as exc:
                    logger.exception("Run %s failed", run["id"])
                    self._fail(run["id"], str(exc))
            self.stop_event.wait(1)

    def _fail(self, key, reason):
        with self.operation_lock:
            run = self.repo.get("runs", key)
            if run["status"] in TERMINAL:
                return
            output = self.output(key)
            with (output / "stderr.log").open("a") as stream:
                stream.write("Platform: " + reason + "\n")
            run = self.repo.update_run(
                key, status="FAILED", finished_at=now(), failure_reason=reason
            )
            write_json(output / "run.json", run)

    def cancel(self, key):
        with self.operation_lock:
            run = self.repo.get("runs", key)
            if run["status"] in TERMINAL:
                return run
            run = self.repo.update_run(key, cancel_requested=True)
            if run["container_id"]:
                self.docker.containers.get(run["container_id"]).stop(timeout=3)
            else:
                run = self.repo.update_run(
                    key,
                    status="CANCELLED",
                    finished_at=now(),
                    failure_reason="Cancelled before container start",
                )
                write_json(self.output(key) / "run.json", run)
            return run

    def wait(self, key, timeout=1800):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = self.repo.get("runs", key)
            if run["status"] in TERMINAL:
                return run
            time.sleep(1)
        self.cancel(key)
        raise TimeoutError(f"Run {key} exceeded {timeout} seconds")

    def metric_events(self, key):
        self.repo.get("runs", key)
        path = self.output(key) / "events.jsonl"
        if not path.exists():
            return []
        events = []
        for line in path.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        return events

    def get_run_diagnostic_context(self, key):
        run = self.repo.get("runs", key)
        result = copy.deepcopy(run)
        try:
            result["tracking"] = self.repo.get("tracking", key)
        except KeyError:
            result["tracking"] = None
        output = self.output(key)
        for stream in ["stdout", "stderr"]:
            result[stream] = (output / (stream + ".log")).read_text(errors="replace")
        for name in ["container.json", "process.json", "process-observation.json"]:
            path = output / name
            result[name.removesuffix(".json")] = (
                json.loads(path.read_text()) if path.exists() else None
            )
        result["resource_info"] = run["execution_spec"]["resources"]
        return result

    def verify_checkpoint(self, run):
        container = self.docker.containers.create(
            run["assets"]["runtime"]["image_id"],
            ["python", "-u", "/workspace/verify.py"],
            working_dir="/workspace",
            mounts=self.mounts(run, output_read_only=True),
            network_disabled=True,
            network_mode="none",
            labels={"ninna.run_id": run["id"], "ninna.role": "verification"},
            mem_limit="4g",
            nano_cpus=4 * 10**9,
        )
        container.start()
        result = container.wait(timeout=600)
        logs = container.logs().decode(errors="replace")
        if result["StatusCode"] != 0:
            raise ValueError(f"Checkpoint reload failed in {container.id}: {logs}")
        return {**json.loads(logs.strip().splitlines()[-1]), "container_id": container.id}

    def promote(self, key, version):
        from ninna.domain.schemas import Ref

        run = self.repo.get("runs", key)
        if run["status"] != "SUCCESS":
            raise ValueError("Only SUCCESS runs can be promoted")
        original = run["assets"]["model"]
        Ref(name=original["name"], version=version)
        target = self.settings.root / "model-bin" / original["name"] / version
        with self.operation_lock:
            if target.exists():
                raise ValueError("Model version directory already exists")
            hf = original.get("metadata", {}).get("format") == "huggingface.PreTrainedModel"
            shutil.copytree(self.output(key) / "model" if hf else original["path"], target)
            if not hf:
                shutil.copyfile(self.output(key) / "checkpoint.pt", target / "checkpoint.pt")
            value = {
                **original,
                "version": version,
                "path": str(target),
                "initial_checkpoint": "model.safetensors" if hf else "checkpoint.pt",
                "files": manifest(target),
                "checksum": manifest_hash(manifest(target)),
                "metadata": {
                    **original["metadata"],
                    "source_run_id": key,
                    "initial_model_hash": run["metadata"]["trained_model_hash"],
                    "trained_model_hash": run["metadata"]["trained_model_hash"],
                },
            }
            value.pop("id", None)
            return self.repo.register("model", value)
