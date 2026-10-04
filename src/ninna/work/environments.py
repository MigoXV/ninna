from __future__ import annotations

import json
import shutil
from pathlib import Path

from docker.errors import NotFound
from docker.types import Mount

from ninna.services.assets import snapshot, checksum
from ninna.storage.repository import now
from ninna.work.assets import safe_path
from ninna.work.store import Conflict, digest


class Environments:
    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.platform = service.platform

    def directory(self, owner_id):
        # IDs are resolved before filesystem access.
        self.owner(owner_id)
        return self.service.root / "workspaces" / owner_id

    def owner(self, owner_id):
        kind = "environment" if owner_id.startswith("environment-") else "work_item"
        return kind, self.store.get(kind, owner_id)

    def workspace(self, owner_id):
        return self.directory(owner_id) / "code"

    def busy(self, owner_id):
        return any(
            j["operation"] == "command"
            and j["payload"].get("owner_id") == owner_id
            and j["status"] in {"QUEUED", "RUNNING"}
            for j in self.store.list("job")
        )

    def initialize(self, job):
        key = job["payload"]["owner_id"]
        kind, owner = self.owner(key)
        if owner.get("ready"):
            container = self.container(key, start=True)
            return {"owner_id": key, "container_id": container.id}
        directory = self.directory(key)
        code = directory / "code"
        code.mkdir(parents=True, exist_ok=True)
        if kind == "work_item":
            revision = self.store.get("environment_revision", owner["environment_revision_id"])
            shutil.copytree(revision["code_path"], code, dirs_exist_ok=True)
            image_id = revision["image_id"]
            framework = revision.get("framework")
            entrypoint = revision.get("entrypoint", "integrations/ninna/runner.py")
        else:
            image = self.platform.repo.asset("image", owner["image_ref"])
            image_id = image["image_id"]
            framework = owner.get("framework")
            entrypoint = "integrations/ninna/runner.py"
            if owner.get("workspace_name"):
                source = self.platform.repo.asset(
                    "workspace", {"name": owner["workspace_name"], "version": "v1"}
                )
                _, path, _ = snapshot(Path(source["path"]), self.service.root / "snapshots")
                shutil.copytree(path, code, dirs_exist_ok=True)
                entrypoint = source["entrypoint"]
            if owner.get("git_url"):
                # Checkout happens inside the preparation container, not on the host.
                owner["pending_git"] = True
        owner.update(image_id=image_id, framework=framework, entrypoint=entrypoint)
        self.store.put(kind, owner)
        container = self.container(key, start=True)
        if owner.get("pending_git"):
            script = "import subprocess,sys; subprocess.run(['git','clone','--no-checkout',sys.argv[1],'/tmp/ninna-source'],check=True); subprocess.run(['git','-C','/tmp/ninna-source','checkout','--detach',sys.argv[2]],check=True); subprocess.run(['cp','-a','/tmp/ninna-source/.','/app/'],check=True)"
            result = container.exec_run(
                ["python", "-c", script, owner["git_url"], owner.get("git_revision") or "HEAD"]
            )
            if result.exit_code:
                raise ValueError("代码获取失败，请检查 Git 地址、版本和环境中的 git 工具。")
            result = container.exec_run(["git", "-C", "/app", "rev-parse", "HEAD"])
            owner["git_commit"] = result.output.decode().strip()
            owner.pop("pending_git", None)
        owner = self.store.get(kind, key) | {k: v for k, v in owner.items() if k != "version"}
        owner.update(
            status="DRAFT" if kind == "environment" else "ACTIVE",
            ready=True,
            container_id=container.id,
            workspace_generation=owner.get("workspace_generation", 0) + 1,
        )
        self.store.put(kind, owner)
        return {"owner_id": key, "container_id": container.id}

    def container(self, owner_id, start=False):
        kind, owner = self.owner(owner_id)
        name = "ninna-work-" + owner_id
        try:
            container = self.platform.docker.containers.get(name)
        except NotFound:
            if owner.get("container_id"):
                raise ValueError(
                    "工作区容器已丢失；文件仍保留，请从已发布环境创建新工作任务，不能假装恢复已安装的依赖。"
                )
            directory = self.directory(owner_id)
            (directory / "commands").mkdir(parents=True, exist_ok=True)
            helper = self.service.root / "helpers"
            helper.mkdir(exist_ok=True)
            shutil.copyfile(
                Path(__file__).with_name("command_runner.py"), helper / "command_runner.py"
            )
            assets = self.service.root / "assets"
            assets.mkdir(exist_ok=True)
            paths = [
                ("/app", directory / "code", False),
                ("/assets", assets, True),
                ("/ninna-commands", directory / "commands", False),
                ("/ninna-helper", helper, True),
            ]
            container = self.platform.docker.containers.create(
                owner["image_id"],
                ["python", "-c", "import time; time.sleep(2147483647)"],
                entrypoint=[],
                name=name,
                working_dir="/app",
                mem_limit="4g",
                nano_cpus=2 * 10**9,
                mounts=[
                    Mount(target, self.platform.settings.host_path(path), type="bind", read_only=ro)
                    for target, path, ro in paths
                ],
                labels={"ninna.role": "workspace", "ninna.owner_id": owner_id},
            )
            self.store.put(kind, {**owner, "container_id": container.id})
        if start:
            container.reload()
            if container.status in {"created", "exited"}:
                container.start()
        return container

    def files(self, owner_id, path=None):
        root = self.workspace(owner_id)
        from ninna.services.assets import EXCLUDED

        if path is None:
            return {
                "files": [
                    str(p.relative_to(root))
                    for p in sorted(root.rglob("*"))
                    if p.is_file()
                    and not p.is_symlink()
                    and not any(
                        part in EXCLUDED or part.startswith(".env")
                        for part in p.relative_to(root).parts
                    )
                ]
            }
        if any(part.startswith(".env") or part == ".git" for part in Path(path).parts):
            raise ValueError("该文件不通过工作区接口暴露。")
        target = safe_path(root, path)
        if not target.is_file():
            raise KeyError(path)
        return {"path": path, "content": target.read_text()[:1000000], "sha256": checksum(target)}

    def edit(self, owner_id, request):
        with self.service.lock:
            if not self.owner(owner_id)[1].get("ready"):
                raise Conflict("工作区尚未准备完成。")
            if self.busy(owner_id):
                raise Conflict("工作区正在执行命令，请等待结束再修改文件。")
            root = self.workspace(owner_id)
            if any(part.startswith(".env") or part == ".git" for part in Path(request.path).parts):
                raise ValueError("该文件不通过工作区接口修改。")
            target = safe_path(root, request.path)
            actual = checksum(target) if target.is_file() else None
            if actual != request.expected_sha256:
                raise Conflict("文件已改变，请重新读取并使用当前 SHA-256。")
            if request.delete:
                if target.exists():
                    target.unlink()
            else:
                if request.content is None:
                    raise ValueError("写入文件需要 content。")
                target.parent.mkdir(parents=True, exist_ok=True)
                temp = target.with_name(target.name + ".ninna-tmp")
                temp.write_text(request.content)
                temp.replace(target)
            kind, owner = self.owner(owner_id)
            self.store.put(
                kind,
                {
                    **owner,
                    "workspace_generation": owner.get("workspace_generation", owner["version"]) + 1,
                },
            )
            return {"path": request.path, "sha256": checksum(target) if target.exists() else None}

    def start_command(self, job):
        with self.service.lock:
            return self._start_command(job)

    def _start_command(self, job):
        job = self.store.get("job", job["id"])
        if job.get("cancel_requested"):
            return {"exit_code": -9}
        value = job["payload"]
        key = value["owner_id"]
        directory = self.directory(key) / "commands" / job["id"]
        directory.mkdir(parents=True, exist_ok=True)
        cwd = (
            safe_path(self.workspace(key), value["cwd"])
            if value["cwd"] != "."
            else self.workspace(key)
        )
        if not cwd.is_dir():
            raise ValueError("命令工作目录不存在。")
        command = {
            "argv": value["argv"],
            "cwd": "/app" + ("/" + value["cwd"] if value["cwd"] != "." else ""),
            "timeout_seconds": value["timeout_seconds"],
        }
        (directory / "request.json").write_text(json.dumps(command))
        container = self.container(key, start=True)
        execution = self.platform.docker.api.exec_create(
            container.id,
            ["python", "/ninna-helper/command_runner.py", "/ninna-commands/" + job["id"]],
            workdir="/app",
        )
        job.update(exec_id=execution["Id"], container_id=container.id, log_path=str(directory))
        self.store.put("job", job)
        self.platform.docker.api.exec_start(execution["Id"], detach=True)
        return None

    def poll_command(self, job):
        if job.get("cancel_requested"):
            self.cancel_command(job)
        if not job.get("exec_id"):
            raise ValueError("命令提交结果未知，不能自动重放；请检查工作区后新建命令。")
        state = self.platform.docker.api.exec_inspect(job["exec_id"])
        result = Path(job["log_path"]) / "exit.json"
        if state["Running"]:
            return None
        if not result.exists():
            raise ValueError("命令已中断，未留下完整退出记录；请检查日志。")
        return json.loads(result.read_text())

    def cancel_command(self, job):
        if not job.get("log_path"):
            return
        pid = Path(job["log_path"]) / "pid"
        if pid.exists():
            container = self.platform.docker.containers.get(job["container_id"])
            container.exec_run(
                [
                    "python",
                    "-c",
                    "import os,signal,sys; os.killpg(int(sys.argv[1]),signal.SIGKILL)",
                    pid.read_text().strip(),
                ]
            )

    def seal(self, owner_id):
        with self.service.lock:
            if self.busy(owner_id):
                raise Conflict("请等待工作区命令完成后再创建执行快照。")
            _, owner = self.owner(owner_id)
            if not owner.get("ready"):
                raise ValueError("环境尚未准备完成。")
            key, path, files = snapshot(self.workspace(owner_id), self.service.root / "snapshots")
            container = self.container(owner_id, start=True)
            # Docker commit excludes bind mounts: code, operations and assets remain separate.
            image = container.commit(
                repository="ninna/prepared",
                tag=owner_id + "-" + digest({"code": key, "at": now()})[:12],
                pause=True,
            )
            return {
                "image_id": image.id,
                "code_snapshot": key,
                "code_path": str(path),
                "files": files,
                "framework": owner.get("framework"),
                "entrypoint": owner.get("entrypoint"),
                "owner_id": owner_id,
                "workspace_version": self.owner(owner_id)[1].get(
                    "workspace_generation", self.owner(owner_id)[1]["version"]
                ),
            }

    def publish(self, job):
        key = job["payload"]["owner_id"]
        prepared = self.seal(key)
        # Validate imports and the declared framework inside the actual prepared image.
        validation = (
            self.platform.runtime_validator.validate(prepared, prepared.get("framework"))
            if not prepared.get("framework")
            else self.validate_framework(prepared)
        )
        revision = self.store.create(
            "environment_revision",
            {**prepared, "environment_id": key, "validation": validation, "status": "PUBLISHED"},
            "publish:" + job["id"],
            "publish_environment",
        )
        kind, owner = self.owner(key)
        self.store.put(kind, {**owner, "latest_revision_id": revision["id"]})
        return revision

    def validate_framework(self, prepared):
        # A prepared image excludes /app; dependency probes must see the captured code.
        import yaml
        from ninna.domain.frameworks import FrameworkManifest

        spec = FrameworkManifest.model_validate(
            yaml.safe_load((Path(prepared["code_path"]) / "ninna-framework.yaml").read_text())
        )
        if {"name": spec.name, "version": spec.version} != prepared["framework"]:
            raise ValueError("工作区 Framework 身份与环境不一致。")
        command = [
            "python",
            "-c",
            "import importlib,json,sys; print(json.dumps({n:getattr(importlib.import_module(n),'__version__','available') for n in sys.argv[1:]}))",
            *spec.imports,
        ]
        container = self.platform.docker.containers.create(
            prepared["image_id"],
            command,
            entrypoint=[],
            working_dir="/app",
            network_mode="none",
            mem_limit="2g",
            mounts=[
                Mount(
                    "/app",
                    self.platform.settings.host_path(Path(prepared["code_path"])),
                    type="bind",
                    read_only=True,
                )
            ],
            environment={"PYTHONPATH": "/app:/app/src"},
            labels={"ninna.role": "environment-validation"},
        )
        container.start()
        result = container.wait(timeout=120)
        if result["StatusCode"]:
            raise ValueError("环境依赖检查失败，请在工作区检查框架 imports 并修复。")
        return {
            "image_id": prepared["image_id"],
            "container_id": container.id,
            "versions": json.loads(
                container.logs(stdout=True, stderr=False).decode().strip().splitlines()[-1]
            ),
        }
