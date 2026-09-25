"""Optional HF-compatible central storage with pinned, checksum-verified local assets."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath

from huggingface_hub import HfApi, hf_hub_download, snapshot_download

from ninna.services.assets import manifest, manifest_hash
from ninna.storage.repository import now


class HubService:
    def __init__(self, platform):
        self.platform = platform
        self.repo = platform.repo
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ninna-hub")
        self.lock = threading.Lock()

    def config(self):
        config = self.platform.integrations.read()["hub"]
        if not config["enabled"]:
            raise ValueError("中心存储未启用；本地训练仍可使用。")
        return config

    @staticmethod
    def api(config):
        return HfApi(endpoint=config["endpoint"], token=config["token"] or False)

    def status(self):
        config = self.platform.integrations.public()["hub"]
        if not config["enabled"]:
            return {**config, "status": "DISABLED"}
        try:
            api = self.api(self.config())
            identity = api.whoami() if config["token_configured"] else None
            list(api.list_models(limit=1))
            return {
                **config,
                "status": "CONNECTED",
                "account": identity.get("name") if identity else None,
            }
        except Exception:
            return {
                **config,
                "status": "UNAVAILABLE",
                "error": "连接失败，请检查地址、凭据和服务状态。",
            }

    def repositories(self, kind):
        api = self.api(self.config())
        values = api.list_models(limit=100) if kind == "model" else api.list_datasets(limit=100)
        return [{"id": v.id, "sha": v.sha, "private": v.private, "kind": kind} for v in values]

    def recover(self):
        for record in self.repo.list("hub_transfers"):
            if record["status"] in {"CREATED", "RUNNING"}:
                record.update(
                    status="FAILED",
                    finished_at=now(),
                    error="平台重启中断了传输；可重新发起，已有远端 commit 不会回滚。",
                )
                self.repo.save("hub_transfers", record)

    def submit(self, direction, request):
        config = self.config()
        if direction == "publish":
            asset = self.repo.asset(
                request.kind, {"name": request.name, "version": request.version}
            )
            if not str(asset.get("metadata", {}).get("format", "")).startswith("huggingface."):
                raise ValueError("中心存储只发布 Hugging Face 格式的模型与数据集")
            # Resolve the complete input now; jobs never read a later edited request.
            request_data = {**request.model_dump(), "asset": asset}
        else:
            request_data = request.model_dump()
        record = {
            "id": "transfer-" + uuid.uuid4().hex[:12],
            "direction": direction,
            "request": request_data,
            "endpoint": config["endpoint"],
            "status": "CREATED",
            "created_at": now(),
            "finished_at": None,
            "result": None,
            "error": None,
        }
        self.repo.save("hub_transfers", record)
        self.pool.submit(self._execute, record, config)
        return record

    def _execute(self, record, config):
        record = copy.deepcopy(record)
        record["status"] = "RUNNING"
        self.repo.save("hub_transfers", record)
        try:
            operation = self._publish if record["direction"] == "publish" else self._import
            record["result"] = operation(record, config)
            record["status"] = "SUCCESS"
        except Exception as exc:
            # Third-party HTTP exceptions can contain signed URLs or credentials.
            reason = (
                str(exc)
                if isinstance(exc, ValueError) and not hasattr(exc, "request")
                else type(exc).__name__
            )
            token = config.get("token")
            if token:
                reason = reason.replace(token, "[redacted]")
            record.update(status="FAILED", error=reason[:1000])
        finally:
            record["finished_at"] = now()
            self.repo.save("hub_transfers", record)

    def _publish(self, record, config):
        request = record["request"]
        asset = request["asset"]
        source = Path(asset["path"])
        if any(path.is_symlink() for path in source.rglob("*")):
            raise ValueError("发布的资产不能包含符号链接")
        if manifest(source) != asset["files"]:
            raise ValueError("待发布资产的文件校验失败")
        staging = self.platform.settings.state / "hub-staging" / record["id"]
        staging.parent.mkdir(exist_ok=True)
        shutil.copytree(source, staging)
        portable = {key: value for key, value in asset.items() if key not in {"path", "id"}}
        document = {
            "schema_version": 1,
            "publication_id": record["id"],
            "kind": request["kind"],
            "asset": portable,
        }
        (staging / "ninna-asset.json").write_text(
            json.dumps(document, indent=2, ensure_ascii=False)
        )
        try:
            payload = {
                **config,
                "repo_id": request["repo_id"],
                "kind": request["kind"],
                "private": request["private"],
                "folder": str(staging),
                "message": f"Ninna {asset['name']}/{asset['version']} ({record['id']})",
            }
            # huggingface_hub 0.36 parses CommitInfo URLs using its process-wide HF_ENDPOINT.
            # Isolate each upload, so changing endpoints never races with another API call.
            process = subprocess.run(
                [sys.executable, "-m", "ninna.services.hub_upload"],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                timeout=600,
                env={
                    **os.environ,
                    "HF_ENDPOINT": config["endpoint"],
                    "HF_HUB_DISABLE_PROGRESS_BARS": "1",
                    "HF_HUB_DISABLE_TELEMETRY": "1",
                },
            )
            receipt = json.loads(process.stdout.strip().splitlines()[-1])
            if process.returncode:
                raise ValueError(
                    f"Hub 上传失败：{receipt.get('error')} (HTTP {receipt.get('status_code')})"
                )
            return {
                "repo_id": request["repo_id"],
                "revision": receipt["revision"],
                "kind": request["kind"],
                "checksum": asset["checksum"],
                "asset_id": asset["id"],
            }
        finally:
            shutil.rmtree(staging)

    def _import(self, record, config):
        request = record["request"]
        if any(
            asset["name"] == request["name"] and asset["version"] == request["version"]
            for asset in self.repo.assets(request["kind"])
        ):
            raise ValueError("本地资产版本已注册，请使用新版本")
        api = self.api(config)
        info = api.repo_info(
            request["repo_id"], repo_type=request["kind"], revision=request["revision"]
        )
        commit = info.sha
        if not commit:
            raise ValueError("Hub 未返回不可变 commit；无法注册可复现资产")
        staging = self.platform.settings.state / "hub-staging" / record["id"]
        staging.mkdir(parents=True)
        try:
            if not any(item.rfilename == "ninna-asset.json" for item in (info.siblings or [])):
                raise ValueError("仓库缺少 ninna-asset.json；请先发布带训练元数据的 HF 资产")
            path = Path(
                hf_hub_download(
                    repo_id=request["repo_id"],
                    repo_type=request["kind"],
                    filename="ninna-asset.json",
                    revision=commit,
                    endpoint=config["endpoint"],
                    token=config["token"] or False,
                    local_dir=staging,
                )
            )
            document = json.loads(path.read_text())
            if document.get("schema_version") != 1 or document.get("kind") != request["kind"]:
                raise ValueError("资产清单版本或类型不匹配")
            asset = document["asset"]
            files = asset["files"]
            if not isinstance(files, dict) or not files:
                raise ValueError("资产清单为空")
            for name in files:
                relative = PurePosixPath(name)
                if relative.is_absolute() or ".." in relative.parts or name.startswith(".cache/"):
                    raise ValueError("资产清单包含非法路径")
            snapshot_download(
                repo_id=request["repo_id"],
                repo_type=request["kind"],
                revision=commit,
                endpoint=config["endpoint"],
                token=config["token"] or False,
                local_dir=staging,
                allow_patterns=list(files),
                max_workers=2,
            )
            # Copy only declared payload, excluding HF download cache and unrelated Hub files.
            target = (
                self.platform.settings.root
                / ("data-bin" if request["kind"] == "dataset" else "model-bin")
                / request["name"]
                / request["version"]
            )
            with self.platform.operation_lock, self.lock:
                if target.exists():
                    raise ValueError("本地资产版本已存在，请使用新版本")
                temporary = staging / "validated"
                temporary.mkdir()
                for name in files:
                    source = staging / name
                    if source.is_symlink() or not source.is_file():
                        raise ValueError("资产文件缺失或包含符号链接")
                    destination = temporary / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                actual = manifest(temporary)
                if actual != files or manifest_hash(actual) != asset["checksum"]:
                    raise ValueError("下载资产的 SHA-256 校验失败")
                self.validate_layout(request["kind"], temporary)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary.rename(target)
                asset.update(name=request["name"], version=request["version"], path=str(target))
                asset.pop("id", None)
                asset.setdefault("metadata", {})["hub"] = {
                    "endpoint": config["endpoint"],
                    "repo_id": request["repo_id"],
                    "revision": commit,
                    "kind": request["kind"],
                }
                registered = self.repo.register(request["kind"], asset)
                return {
                    "asset_id": registered["id"],
                    "repo_id": request["repo_id"],
                    "revision": commit,
                    "checksum": asset["checksum"],
                }
        finally:
            shutil.rmtree(staging)

    @staticmethod
    def validate_layout(kind, root):
        required = (
            ["config.json", "preprocessor_config.json"]
            if kind == "model"
            else ["dataset_dict.json"]
        )
        if any(not (root / name).is_file() for name in required):
            raise ValueError("不是支持的 Hugging Face 模型或 DatasetDict 目录")
        if kind == "model" and not list(root.glob("*.safetensors")):
            raise ValueError("HF 模型缺少 Safetensors 权重")

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)
