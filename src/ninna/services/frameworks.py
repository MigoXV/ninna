"""Framework discovery, preflight and immutable task runs."""

from __future__ import annotations

import io
import json
import math
import re
import tarfile
import uuid
from pathlib import Path, PurePosixPath

import yaml
from docker.types import Mount, DeviceRequest

from ninna.domain.frameworks import FrameworkManifest
from ninna.domain.schemas import CreateTask, TERMINAL
from ninna.services.assets import checksum, manifest, manifest_hash
from ninna.storage.repository import now


def relative_file(root: Path, name: str) -> Path:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Expected a relative artifact path")
    result = root.joinpath(*path.parts)
    if not result.resolve().is_relative_to(root.resolve()) or result.is_symlink():
        raise ValueError("Artifact must remain inside its run")
    return result


def read_archive(stream, limit=2_000_000):
    content = bytearray()
    for chunk in stream:
        content.extend(chunk)
        if len(content) > limit:
            raise ValueError("Framework description exceeds size limit")
    with tarfile.open(fileobj=io.BytesIO(content)) as archive:
        members = [m for m in archive.getmembers() if m.isfile()]
        if len(members) != 1 or members[0].size > limit:
            raise ValueError("Expected one regular description file")
        return archive.extractfile(members[0]).read().decode("utf-8")


class FrameworkService:
    def __init__(self, platform):
        self.platform = platform
        self.repo = platform.repo

    def discover_image(self, image_asset):
        docker = self.platform.docker
        image = docker.images.get(image_asset["image_id"])
        if image.attrs.get("Config", {}).get("WorkingDir") != "/app":
            raise ValueError("Framework image WORKDIR must be /app")
        container = docker.containers.create(image.id, ["true"], network_mode="none")
        try:
            raw = read_archive(container.get_archive("/app/ninna-framework.yaml")[0])
            spec = FrameworkManifest.model_validate(yaml.safe_load(raw))
            skill = read_archive(container.get_archive("/app/" + spec.skill)[0])
            agents = read_archive(container.get_archive("/app/AGENTS.md")[0])
            return {
                "manifest": spec.model_dump(),
                "skill": skill,
                "agents": agents,
                "image_id": image.id,
                "manifest_sha256": __import__("hashlib").sha256(raw.encode()).hexdigest(),
            }
        finally:
            container.remove()

    def import_image(self, request):
        """Extract tracked code without starting the image; never import model/data payloads."""
        with self.platform.operation_lock:
            return self._import_image(request)

    def _import_image(self, request):
        image = self.repo.asset("image", request.image.model_dump())
        description = self.discover_image(image)
        spec = description["manifest"]
        target = self.platform.settings.root / "workspaces" / request.workspace_name
        if target.exists():
            raise ValueError("Workspace exists; choose a new workspace name")
        container = self.platform.docker.containers.create(
            image["image_id"], ["true"], network_mode="none"
        )
        try:
            # Dockerfile excludes all data, models, caches and virtual environments.
            stream, _ = container.get_archive("/app")
            target.mkdir(parents=True)
            import tempfile

            with tempfile.SpooledTemporaryFile(max_size=8_000_000) as buffer:
                size = 0
                for chunk in stream:
                    size += len(chunk)
                    if size > 256_000_000:
                        raise ValueError(
                            "Framework source exceeds 256 MB; remove data, weights and caches"
                        )
                    buffer.write(chunk)
                buffer.seek(0)
                archive = tarfile.open(fileobj=buffer)
                for member in archive:
                    parts = PurePosixPath(member.name).parts
                    if not parts or parts[0] != "app":
                        raise ValueError("Invalid framework archive root")
                    if len(parts) == 1:
                        continue
                    path = relative_file(target, "/".join(parts[1:]))
                    if member.isdir():
                        path.mkdir(parents=True, exist_ok=True)
                    elif member.isfile():
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with archive.extractfile(member) as src, path.open("wb") as dst:
                            __import__("shutil").copyfileobj(src, dst)
                    else:
                        raise ValueError("Framework archive cannot contain links or devices")
                archive.close()
            existing = next(
                (
                    f
                    for f in self.repo.assets("framework")
                    if f["name"] == spec["name"] and f["version"] == spec["version"]
                ),
                None,
            )
            if existing:
                if any(existing.get(k) != v for k, v in spec.items()):
                    raise ValueError("Framework version already exists with a different manifest")
                framework = existing
            else:
                framework = self.repo.register(
                    "framework",
                    {
                        **spec,
                        "documentation": description,
                        "metadata": {"description": ", ".join(spec["tasks"])},
                    },
                )
            workspace = self.repo.register(
                "workspace",
                {
                    "name": request.workspace_name,
                    "version": "v1",
                    "path": str(target),
                    "entrypoint": "integrations/ninna/runner.py",
                    "metadata": {
                        "framework": {k: spec[k] for k in ("name", "version")},
                        "git_commit": image.get("build_source", {}).get(
                            "org.opencontainers.image.revision"
                        ),
                    },
                },
            )
            return {"framework": framework, "workspace": workspace}
        except Exception:
            __import__("shutil").rmtree(target, ignore_errors=True)
            raise
        finally:
            container.remove()

    def preflight(self, request: CreateTask):
        self.repo.get("projects", request.project_id)
        framework = self.repo.asset("framework", request.framework.model_dump())
        spec = FrameworkManifest.model_validate(
            {k: framework[k] for k in FrameworkManifest.model_fields if k in framework}
        )
        if request.task not in spec.tasks:
            raise ValueError("Task is not declared by this framework")
        task = spec.tasks[request.task]
        if request.operation not in task.operations:
            raise ValueError("Operation is not supported by this task")
        operation = task.operations[request.operation]
        for key in request.inputs:
            if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]*", key):
                raise ValueError("Invalid input name")
        for key, kind in operation.required_inputs.items():
            if key not in request.inputs or request.inputs[key].kind != kind:
                raise ValueError(f"Missing {kind} input: {key}")
        inputs = {k: self.repo.asset(v.kind, v.ref.model_dump()) for k, v in request.inputs.items()}
        for key, asset in inputs.items():
            self.platform.settings.host_path(Path(asset["path"]))
            if manifest(Path(asset["path"])) != asset["files"]:
                raise ValueError(f"Input checksum changed: {key}")
        recipe = self.repo.asset("recipe", request.recipe.model_dump())
        if (
            recipe.get("framework") != request.framework.model_dump()
            or recipe.get("task") != request.task
        ):
            raise ValueError("Recipe does not belong to this framework task")
        if recipe.get("operation", "train") != request.operation:
            raise ValueError("Recipe operation mismatch")
        runtime = self.repo.asset("runtime", request.execution_spec.runtime.model_dump())
        image = self.platform.images.resolve_runtime(runtime)
        identity = runtime.get("framework")
        if identity != request.framework.model_dump():
            raise ValueError("Runtime has not been validated for this framework version")
        if request.parent_run_id:
            parent = self.repo.get("runs", request.parent_run_id)
            if self.repo.run_project(parent) != request.project_id:
                raise ValueError("Parent run must belong to the same project")
        source = None
        if operation.needs_source and not request.source:
            raise ValueError("Operation requires an explicit source artifact")
        if request.source:
            parent = self.repo.get("runs", request.source.run_id)
            if (
                parent["status"] not in TERMINAL
                or self.repo.run_project(parent) != request.project_id
            ):
                raise ValueError("Source must be a sealed run in the same project")
            if (
                parent.get("task_spec", {}).get("framework") != request.framework.model_dump()
                or parent.get("task_spec", {}).get("task") != request.task
            ):
                raise ValueError("Source framework/task mismatch")
            entries = {a["name"]: a for a in parent["artifacts"]}
            if request.source.path not in entries:
                raise ValueError("Source artifact is not in the sealed manifest")
            path = relative_file(self.platform.output(parent["id"]), request.source.path)
            if checksum(path) != entries[request.source.path]["sha256"]:
                raise ValueError("Source artifact checksum changed")
            if request.operation == "train":
                if not request.source.path.endswith(".ckpt"):
                    raise ValueError("Resume requires a training .ckpt")
                if parent["task_spec"]["inputs"] != request.model_dump()["inputs"]:
                    raise ValueError("Resume input identities changed")
                previous = parent["assets"]["recipe"]["config"]
                current = recipe["config"]
                for field in ("model", "data", "optimizer", "lr_scheduler", "seed_everything"):
                    if previous.get(field) != current.get(field):
                        raise ValueError(f"Resume configuration changed: {field}")
            if request.operation in {"evaluate", "export"}:
                for name, value in request.inputs.items():
                    if (
                        value.kind == "model"
                        and parent["task_spec"]["inputs"].get(name) != value.model_dump()
                    ):
                        raise ValueError("Source model identity changed")
            source = {"path": str(path), "sha256": checksum(path)}
        return {
            "framework": framework,
            "operation": operation.model_dump(),
            "inputs": inputs,
            "recipe": recipe,
            "runtime": runtime,
            "image": image,
            "source": source,
        }

    def create(self, request, run_id=None):
        from ninna.services.platform import write_json

        with self.platform.operation_lock:
            resolved = self.preflight(request)
            workspace = self.platform.resolve_workspace(
                request.execution_spec.workspace.model_dump()
            )
            path = Path(workspace["snapshot_path"])
            spec = FrameworkManifest.model_validate(
                yaml.safe_load((path / "ninna-framework.yaml").read_text())
            )
            registered = resolved["framework"]
            if spec.model_dump() != {k: registered[k] for k in spec.model_dump()}:
                raise ValueError("Workspace framework manifest differs from registered version")
            if not (path / spec.skill).is_file() or not (path / "AGENTS.md").is_file():
                raise ValueError("Workspace is missing agent instructions")
            key = run_id or "run-" + uuid.uuid4().hex[:12]
            execution = request.execution_spec.model_dump()
            execution["workspace"]["snapshot"] = workspace["snapshot"]
            inputs = resolved["inputs"]
            # Summary refs keep the existing project list and experiment UI compatible.
            summary = {
                k: (
                    request.inputs[k].ref.model_dump()
                    if k in request.inputs
                    else {"name": "none", "version": "v1"}
                )
                for k in ("dataset", "model")
            }
            summary["recipe"] = request.recipe.model_dump()
            assets = {k: resolved[k] for k in ("framework", "recipe", "runtime", "image")}
            assets.update({k: inputs[k] for k in ("dataset", "model") if k in inputs})
            assets["workspace"] = workspace
            run = {
                "id": key,
                "run_id": key,
                "project_id": request.project_id,
                "task_spec": request.model_dump(),
                "training_spec": summary,
                "execution_spec": execution,
                "assets": assets,
                "inputs": inputs,
                "source_artifact": resolved["source"],
                "operation_contract": resolved["operation"],
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
                "parent_run_id": request.parent_run_id
                or (request.source.run_id if request.source else None),
                "artifacts": [],
                "container_state": None,
                "metadata": {},
                "monitor_error": None,
                "runtime_validation": resolved["runtime"]["validation"],
            }
            output = self.platform.output(key)
            (output / "config").mkdir(parents=True, exist_ok=True)
            write_json(output / "config/run.json", run)
            write_json(output / "run.json", run)
            for name in ("stdout.log", "stderr.log"):
                (output / name).touch()
            self.repo.save("runs", run)
            return run

    def prepare(self, run):
        from ninna.services.assets import manifest
        from docker.errors import NotFound

        p = self.platform
        key = run["id"]
        run = self.repo.update_run(key, status="PREPARING") if run["status"] == "CREATED" else run
        for asset in run["inputs"].values():
            if manifest(Path(asset["path"])) != asset["files"]:
                raise ValueError("Input asset checksum changed")
        workspace = run["assets"]["workspace"]
        if manifest(Path(workspace["snapshot_path"])) != workspace["files"]:
            raise ValueError("Workspace checksum changed")
        p.images.resolve_runtime(run["assets"]["runtime"])
        mounts = [
            Mount(
                "/app",
                p.settings.host_path(Path(workspace["snapshot_path"])),
                type="bind",
                read_only=True,
            ),
            Mount(
                "/config",
                p.settings.host_path(p.output(key) / "config"),
                type="bind",
                read_only=True,
            ),
            Mount("/output", p.settings.host_path(p.output(key)), type="bind"),
        ]
        for name, asset in run["inputs"].items():
            mounts.append(
                Mount(
                    "/inputs/" + name,
                    p.settings.host_path(Path(asset["path"])),
                    type="bind",
                    read_only=True,
                )
            )
        if run["source_artifact"]:
            source = run["source_artifact"]
            if checksum(Path(source["path"])) != source["sha256"]:
                raise ValueError("Source artifact changed before launch")
            mounts.append(
                Mount(
                    "/source/artifact",
                    p.settings.host_path(Path(source["path"])),
                    type="bind",
                    read_only=True,
                )
            )
        resources = run["execution_spec"]["resources"]
        with p.operation_lock:
            if (
                self.repo.get("runs", key)["status"] in TERMINAL
                or self.repo.get("runs", key)["cancel_requested"]
            ):
                return
            try:
                container = p.docker.containers.get("ninna-" + key)
            except NotFound:
                device_requests = []
                if resources["device"] == "cuda":
                    available = {g["uuid"]: g for g in self.gpus()}
                    gpu = available.get(resources["gpu_ids"][0])
                    if not gpu or gpu["memory_used_mb"] > 128 or gpu["utilization"] > 0:
                        raise ValueError(
                            "Selected GPU is unavailable or occupied; choose an idle GPU"
                        )
                    device_requests = [
                        DeviceRequest(device_ids=resources["gpu_ids"], capabilities=[["gpu"]])
                    ]
                container = p.docker.containers.create(
                    run["assets"]["image"]["image_id"],
                    ["python", "-u", "-m", "integrations.ninna.runner", "/config/run.json"],
                    entrypoint=[],
                    working_dir="/app",
                    name="ninna-" + key,
                    hostname=key,
                    mounts=mounts,
                    network_mode="none",
                    network_disabled=True,
                    mem_limit=f"{resources['memory_mb']}m",
                    nano_cpus=resources["cpu_threads"] * 10**9,
                    shm_size="1g",
                    device_requests=device_requests,
                    environment={
                        "PYTHONPATH": "/app:/app/src",
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "PYTHONUNBUFFERED": "1",
                        "HF_HOME": "/output/cache/hf",
                        "HF_DATASETS_CACHE": "/output/cache/datasets",
                        "HF_HUB_OFFLINE": "1",
                        "TRANSFORMERS_OFFLINE": "1",
                        "OMP_NUM_THREADS": str(resources["cpu_threads"]),
                        "NINNA_OUTPUT": "/output",
                    },
                    labels={"ninna.run_id": key, "ninna.role": "training"},
                    log_config={"Type": "json-file", "Config": {}},
                )
            self.repo.update_run(key, container_id=container.id)
            container.reload()
            if container.status == "created":
                container.start()
            self.repo.update_run(key, status="RUNNING", started_at=run["started_at"] or now())

    def finish(self, run, changes, exit_code):
        from ninna.services.platform import write_json

        output = self.platform.output(run["id"])
        status, reason, result = "SUCCESS", None, {}
        if run["cancel_requested"]:
            status, reason = "CANCELLED", "Cancelled by platform"
        elif exit_code != 0:
            status, reason = "FAILED", f"Container exited with code {exit_code}"
        else:
            try:
                result = json.loads((output / "result.json").read_text())
                if (
                    result.get("protocol_version") != 1
                    or result.get("operation") != run["task_spec"]["operation"]
                ):
                    raise ValueError("Invalid task result protocol")
                for key, value in result.get("metrics", {}).items():
                    if not isinstance(value, (int, float)) or not math.isfinite(value):
                        raise ValueError(f"Invalid metric: {key}")
                entries = result.get("artifacts", [])
                if not entries:
                    raise ValueError("Task produced no declared artifacts")
                kinds = set()
                for item in entries:
                    path = relative_file(output, item["path"])
                    if not path.is_file() or checksum(path) != item["sha256"]:
                        raise ValueError("Result artifact checksum mismatch")
                    kinds.add(item["kind"])
                if not set(run["operation_contract"]["required_artifacts"]) <= kinds:
                    raise ValueError("Required task artifacts are missing")
                if run["task_spec"]["operation"] == "train":
                    evidence = result.get("evidence", {})
                    initial = evidence.get("initial_trainable_hash", "")
                    final = evidence.get("final_trainable_hash", "")
                    if (
                        not isinstance(evidence.get("optimizer_steps"), int)
                        or evidence["optimizer_steps"] <= 0
                        or not isinstance(initial, str)
                        or not isinstance(final, str)
                        or not re.fullmatch(r"[0-9a-f]{64}", initial)
                        or not re.fullmatch(r"[0-9a-f]{64}", final)
                        or initial == final
                    ):
                        raise ValueError("No evidence of optimizer updates")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                status, reason = "FAILED", str(exc)
        artifacts = []
        for path in sorted(output.rglob("*")):
            relative = path.relative_to(output)
            if (
                path.is_file()
                and not path.is_symlink()
                and "cache" not in relative.parts
                and relative.as_posix() != "run.json"
            ):
                artifacts.append(
                    {
                        "name": relative.as_posix(),
                        "size": path.stat().st_size,
                        "sha256": checksum(path),
                    }
                )
        run = self.repo.update_run(
            run["id"],
            **changes,
            status=status,
            exit_code=exit_code,
            finished_at=now(),
            failure_reason=reason,
            metrics=result.get("metrics", {}),
            metadata={
                "result": result,
                "quality": result.get("quality", {"status": "not_evaluated"}),
            },
            artifacts=artifacts,
        )
        write_json(output / "run.json", run)
        return run

    def gpus(self):
        import subprocess

        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=uuid,name,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        values = []
        for line in result.stdout.splitlines():
            uid, name, total, used, utilization = [v.strip() for v in line.split(",")]
            values.append(
                {
                    "uuid": uid,
                    "name": name,
                    "memory_total_mb": int(total),
                    "memory_used_mb": int(used),
                    "utilization": int(utilization),
                }
            )
        return values

    def promote(self, key, version, artifact_path="model", kind="model"):
        """Promote a declared model/data directory without changing its source Run."""
        import shutil
        from ninna.domain.schemas import Ref

        run = self.repo.get("runs", key)
        if run["status"] != "SUCCESS":
            raise ValueError("Only successful task outputs can be promoted")
        if kind not in {"model", "dataset"}:
            raise ValueError("Promotion kind must be model or dataset")
        source = relative_file(self.platform.output(key), artifact_path)
        if not source.is_dir():
            raise ValueError("Select an exported artifact directory")
        declared = {a["path"]: a for a in run["metadata"]["result"]["artifacts"]}
        files = manifest(source)
        if not files:
            raise ValueError("Artifact directory is empty")
        for name, digest in files.items():
            entry = declared.get(str(PurePosixPath(artifact_path) / name))
            if not entry or digest != entry["sha256"]:
                raise ValueError("Artifact is not sealed or has changed")
        kinds = {v["kind"] for k, v in declared.items() if k.startswith(artifact_path + "/")}
        if kind not in kinds and not (kind == "model" and "adapter" in kinds):
            raise ValueError("Selected directory does not contain the requested asset type")
        identity = Ref(
            name=run["task_spec"]["framework"]["name"] + "-" + run["task_spec"]["task"],
            version=version,
        )
        destination = (
            self.platform.settings.root
            / ("data-bin" if kind == "dataset" else "model-bin")
            / identity.name
            / identity.version
        )
        with self.platform.operation_lock:
            if destination.exists():
                raise ValueError("Asset output already exists; choose a new version")
            shutil.copytree(source, destination)
            metadata = {
                "source_run_id": key,
                "framework": run["task_spec"]["framework"],
                "task": run["task_spec"]["task"],
                "base_inputs": run["task_spec"]["inputs"],
                "format": "huggingface.adapter"
                if "adapter" in kinds and "model" not in kinds
                else ("huggingface.PreTrainedModel" if kind == "model" else "huggingface.Dataset"),
            }
            value = {
                **identity.model_dump(),
                "path": str(destination),
                "files": files,
                "checksum": manifest_hash(files),
                "metadata": metadata,
            }
            if kind == "model":
                value.update(
                    architecture={
                        "framework": run["task_spec"]["framework"],
                        "task": run["task_spec"]["task"],
                    },
                    initialization={"source_run_id": key},
                    parameter_count=None,
                )
            else:
                value.update(train_split={"name": "train"}, test_split={"name": "test"})
            return self.repo.register(kind, value)
