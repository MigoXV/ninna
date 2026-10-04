"""Immutable Docker image assets and independently persisted pull jobs."""

from __future__ import annotations

import copy
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import docker
from docker.utils import parse_repository_tag

from ninna.domain.schemas import ImageRequest, RuntimeRequest
from ninna.storage.repository import now


def failure(exc):
    # Docker/registry errors may contain URLs, credentials or response bodies.
    code = getattr(exc, "status_code", None)
    if isinstance(exc, docker.errors.ImageNotFound) or code == 404:
        return "镜像不存在，请检查地址、版本及当前 Docker Engine。"
    if code in (401, 403):
        return "仓库拒绝访问，请检查平台部署侧 Docker 凭据和仓库权限。"
    if isinstance(exc, docker.errors.DockerException):
        return "Docker 或镜像仓库请求失败，请检查连接、地址和部署侧凭据。"
    if "credential" in type(exc).__name__.lower() or "credentials" in type(exc).__module__:
        return "Docker credential helper 不可用，请在平台执行环境安装对应 helper。"
    return "镜像操作失败，请检查 Docker、仓库配置及可用磁盘空间。"


class ImageService:
    def __init__(self, platform):
        self.platform = platform
        self.repo = platform.repo
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ninna-image-pull")

    @property
    def docker(self):
        return self.platform.docker

    def close(self):
        self.pool.shutdown(wait=True)

    @staticmethod
    def inspect(image):
        attrs = image.attrs
        labels = (attrs.get("Config") or {}).get("Labels") or {}
        return {
            "image_id": image.id,
            "repo_digests": sorted(attrs.get("RepoDigests") or []),
            "tags": sorted(attrs.get("RepoTags") or []),
            "os": attrs.get("Os"),
            "architecture": attrs.get("Architecture"),
            "variant": attrs.get("Variant"),
            "size": attrs.get("Size", 0),
            "image_created_at": attrs.get("Created"),
            "build_source": {
                key: labels[key]
                for key in (
                    "org.opencontainers.image.source",
                    "org.opencontainers.image.revision",
                    "org.opencontainers.image.version",
                    "org.opencontainers.image.created",
                )
                if key in labels
            },
        }

    def local(self):
        try:
            return [self.inspect(image) for image in self.docker.images.list()]
        except Exception as exc:
            raise ValueError(failure(exc)) from exc

    def existing(self, ref):
        try:
            return self.repo.asset("image", ref)
        except ValueError:
            return None

    def check_target(self, request):
        if self.existing(request.model_dump()):
            raise ValueError("镜像资产版本已存在，请使用新版本。")
        for job in self.repo.list("image_pulls"):
            if job["status"] in {"CREATED", "RUNNING"} and all(
                job["request"][key] == getattr(request, key) for key in ("name", "version")
            ):
                raise ValueError("该镜像资产版本正在拉取，请查看已有任务。")

    def asset_value(self, request, image, pull_id=None, resolved_reference=None):
        return {
            "id": f"image:{request.name}:{request.version}",
            "name": request.name,
            "version": request.version,
            "description": request.description,
            "created_at": now(),
            "source_reference": request.source,
            "resolved_reference": resolved_reference,
            "pull_id": pull_id,
            "metadata": {},
            **self.inspect(image),
        }

    def register(self, request: ImageRequest):
        with self.lock:
            self.check_target(request)
            try:
                image = self.docker.images.get(request.source)
            except Exception as exc:
                raise ValueError(failure(exc)) from exc
            return self.repo.register("image", self.asset_value(request, image))

    def availability(self, asset):
        try:
            image = self.docker.images.get(asset["image_id"])
            return {"status": "AVAILABLE", "checked_at": now(), "image_id": image.id}
        except docker.errors.ImageNotFound:
            return {
                "status": "MISSING",
                "checked_at": now(),
                "error": "镜像已不在当前 Docker Engine 中。",
            }
        except Exception as exc:
            return {"status": "UNAVAILABLE", "checked_at": now(), "error": failure(exc)}

    def detail(self, asset):
        ref = {key: asset[key] for key in ("name", "version")}
        runtimes = [r for r in self.repo.assets("runtime") if r.get("image_ref") == ref]
        runs = [
            r
            for r in self.repo.list("runs")
            if (
                r.get("assets", {}).get("image", {}).get("image_id")
                or r.get("assets", {}).get("runtime", {}).get("image_id")
            )
            == asset["image_id"]
        ]
        return {
            "availability": self.availability(asset),
            "runtimes": runtimes,
            "runs": [
                {
                    "id": r["id"],
                    "project_id": self.repo.run_project(r),
                    "status": r["status"],
                    "created_at": r["created_at"],
                }
                for r in runs
            ],
            "pulls": [
                j
                for j in self.repo.list("image_pulls")
                if j["request"]["name"] == asset["name"]
                and j["request"]["version"] == asset["version"]
            ],
        }

    def resolve_runtime(self, runtime):
        if not runtime.get("image_ref"):
            raise ValueError("这是历史 Runtime，请选择引用镜像资产的新版本。")
        asset = self.repo.asset("image", runtime["image_ref"])
        state = self.availability(asset)
        if state["status"] != "AVAILABLE":
            raise ValueError(state["error"])
        return asset

    def register_runtime(self, request: RuntimeRequest):
        with self.lock:
            image = self.repo.asset("image", request.image_ref.model_dump())
            state = self.availability(image)
            if state["status"] != "AVAILABLE":
                raise ValueError(state["error"])
            try:
                evidence = self.platform.runtime_validator.validate(
                    image, request.framework.model_dump() if request.framework else None
                )
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(failure(exc)) from exc
            value = {
                **request.model_dump(),
                "profile": "framework-v1" if request.framework else "hf-training-cpu",
                "metadata": {
                    **evidence["versions"],
                    "devices": ["cpu", "cuda"] if request.framework else ["cpu"],
                },
                "validation": evidence,
            }
            return self.repo.register("runtime", value)

    def submit(self, request: ImageRequest):
        if request.source.startswith("sha256:"):
            raise ValueError("远端拉取需要仓库地址；本地 image ID 请使用注册本地镜像。")
        with self.lock:
            self.check_target(request)
            job = {
                "id": "pull-" + uuid.uuid4().hex[:12],
                "request": request.model_dump(),
                "status": "CREATED",
                "created_at": now(),
                "started_at": None,
                "finished_at": None,
                "resolved_reference": None,
                "result": None,
                "error": None,
                "layers": {},
                "logs": [],
            }
            self.repo.save("image_pulls", job)
            self.pool.submit(self.execute, copy.deepcopy(job))
            return job

    def complete(self, job, image):
        request = ImageRequest.model_validate(job["request"])
        value = self.asset_value(request, image, job["id"], job["resolved_reference"])
        # Commit the registered asset and job outcome together; recovery never guesses by tag.
        job.update(status="SUCCESS", result=value["id"], finished_at=now())
        self.repo.complete_image_pull(value, job)

    def execute(self, job):
        try:
            job.update(status="RUNNING", started_at=now())
            self.repo.save("image_pulls", job)
            source = job["request"]["source"]
            repository, _ = parse_repository_tag(source)
            descriptor = self.docker.api.inspect_distribution(source)["Descriptor"]["digest"]
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", descriptor):
                raise ValueError("Invalid registry digest")
            job["resolved_reference"] = repository + "@" + descriptor
            job["logs"].append("已解析仓库 digest，开始按固定内容拉取。")
            self.repo.save("image_pulls", job)
            for event in self.docker.api.pull(job["resolved_reference"], stream=True, decode=True):
                if event.get("error") or event.get("errorDetail"):
                    raise docker.errors.DockerException("Registry stream error")
                # Store structured progress only; never persist arbitrary registry error bodies.
                layer = str(event.get("id", ""))[:100]
                status = str(event.get("status", ""))
                allowed = {
                    "Pulling fs layer",
                    "Waiting",
                    "Downloading",
                    "Verifying Checksum",
                    "Download complete",
                    "Extracting",
                    "Pull complete",
                    "Already exists",
                }
                if status in allowed:
                    progress = event.get("progressDetail") or {}
                    job["layers"][layer] = {
                        "status": status,
                        "current": progress.get("current"),
                        "total": progress.get("total"),
                    }
                    line = f"{layer}: {status}"
                    if not job["logs"] or job["logs"][-1] != line:
                        job["logs"] = (job["logs"] + [line])[-300:]
                    self.repo.save("image_pulls", job)
            image = self.docker.images.get(job["resolved_reference"])
            self.complete(job, image)
        except Exception as exc:
            job.update(status="FAILED", finished_at=now(), error=failure(exc))
            self.repo.save("image_pulls", job)

    def recover(self):
        for job in self.repo.list("image_pulls"):
            if job["status"] not in {"CREATED", "RUNNING"}:
                continue
            try:
                if not job["resolved_reference"]:
                    raise ValueError("Unresolved interrupted pull")
                image = self.docker.images.get(job["resolved_reference"])
                self.complete(job, image)
            except Exception:
                job.update(
                    status="FAILED",
                    finished_at=now(),
                    error="平台重启中断了拉取，未确认镜像完成；请重新发起任务。",
                )
                self.repo.save("image_pulls", job)

    def migrate(self):
        """Create successors, never rewrite old versions or historical execution evidence."""
        if any(
            r["status"] not in {"SUCCESS", "FAILED", "CANCELLED"} for r in self.repo.list("runs")
        ):
            raise ValueError("请等待现有训练结束后迁移 Runtime。")
        results = []
        for runtime in self.repo.assets("runtime"):
            if runtime.get("image_ref"):
                continue
            image_id = runtime["image_id"]
            ref = {"name": "docker-" + image_id.split(":")[-1], "version": "v1"}
            image = self.existing(ref)
            if image is None:
                image = self.register(
                    ImageRequest(**ref, source=image_id, description="从历史 Runtime 纳管")
                )
            version = (
                "v4"
                if runtime["name"] == "mnist-pytorch-runtime" and runtime["version"] == "v3"
                else runtime["version"] + "-image-v1"
            )
            target = {"name": runtime["name"], "version": version}
            try:
                previous = self.repo.asset("runtime", target)
            except ValueError:
                previous = None
            if previous:
                if previous.get("image_ref") != ref:
                    raise ValueError("Runtime 迁移目标版本冲突。")
                results.append(previous)
                continue
            # Old non-HF environments remain viewable but cannot become new training Runtimes.
            if not runtime.get("metadata", {}).get("transformers"):
                continue
            results.append(
                self.register_runtime(
                    RuntimeRequest(**target, image_ref=ref, description="从历史 Runtime 迁移")
                )
            )
        return results
