"""Multi-source acquisition. File availability is independent of training compatibility."""

from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import httpx
from huggingface_hub import HfApi, snapshot_download

from ninna.services.assets import manifest, manifest_hash
from ninna.storage.repository import now
from ninna.work.store import digest


def http_url(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("需要不含登录凭据的 HTTP(S) 地址。")
    return value.rstrip("/")


def safe_path(root: Path, relative: str):
    part = PurePosixPath(relative)
    if not relative or part.is_absolute() or ".." in part.parts or "\\" in relative:
        raise ValueError("需要工作目录内的相对路径。")
    target = root.joinpath(*part.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("路径越出工作目录。")
    if any(root.joinpath(*part.parts[:i]).is_symlink() for i in range(1, len(part.parts) + 1)):
        raise ValueError("不允许符号链接。")
    return target


def payload_manifest(root):
    if any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("资产不能包含符号链接。")
    files = manifest(root)
    if not files:
        raise ValueError("资产目录为空。")
    return files


class Assets:
    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.platform = service.platform

    def index_registered(self, kind, asset):
        """Expose immutable legacy/produced assets through the unified catalog."""
        if kind not in {"model", "dataset"}:
            return None
        ref = {"name": asset["name"], "version": asset["version"]}
        existing = next(
            (
                a
                for a in self.store.list("asset")
                if a["kind"] == kind and a.get("legacy_ref") == ref
            ),
            None,
        )
        if existing:
            return existing
        return self.store.create(
            "asset",
            {
                "name": asset["name"],
                "kind": kind,
                "path": asset["path"],
                "files": asset["files"],
                "checksum": asset.get("checksum") or manifest_hash(asset["files"]),
                "revision": asset["version"],
                "legacy_ref": {"name": asset["name"], "version": asset["version"]},
                "source_id": None,
                "repo_id": None,
                "source_run_id": asset.get("metadata", {}).get("source_run_id"),
            },
            "registered:" + asset["id"],
            "index_registered",
        )

    def source(self, source_id):
        source = self.store.get("source", source_id)
        if not source["enabled"]:
            raise ValueError("该托管平台已停用；已下载的本地资产仍可使用。")
        return source

    def token(self, source):
        if source.get("legacy_credentials"):
            # The migrated address is pinned; never send the secret to an edited endpoint.
            previous = self.platform.integrations.read()["hub"]
            if previous["endpoint"].rstrip("/") == source["endpoint"]:
                return previous.get("token") or False
        key = source.get("token_env")
        if key and not os.environ.get(key):
            raise ValueError(f"平台部署环境缺少凭据变量 {key}。")
        return os.environ.get(key) if key else False

    def api(self, source):
        return HfApi(endpoint=source["endpoint"], token=self.token(source))

    def source_status(self, source_id):
        source = self.store.get("source", source_id)
        if not source["enabled"]:
            return {"status": "DISABLED"}
        try:
            next(iter(self.api(source).list_models(limit=1)), None)
            return {"status": "CONNECTED", "checked_at": now()}
        except Exception:
            return {
                "status": "UNAVAILABLE",
                "checked_at": now(),
                "error": "无法连接，请检查平台地址和部署侧凭据。",
            }

    def browse(self, source_id, kind, query, offset, limit):
        api = self.api(self.source(source_id))
        loader = api.list_models if kind == "model" else api.list_datasets
        # SDK iterators paginate upstream; bounded offset avoids claiming a complete catalog.
        import itertools

        values = list(itertools.islice(loader(search=query or None), offset, offset + limit + 1))
        local = self.store.list("asset")
        items = []
        for row in values[:limit]:
            copies = [
                self.describe(a["id"])
                for a in local
                if a.get("source_id") == source_id
                and a.get("repo_id") == row.id
                and a["kind"] == kind
            ]
            items.append(
                {
                    "source_id": source_id,
                    "kind": kind,
                    "repo_id": row.id,
                    "revision": row.sha,
                    "private": row.private,
                    "local_revisions": copies,
                }
            )
        return {"items": items, "next_offset": offset + limit if len(values) > limit else None}

    def describe(self, key, verify=False):
        asset = self.store.get("asset", key)
        root = Path(asset["path"])
        state = "DOWNLOADED"
        if not root.is_dir() or any(not safe_path(root, name).is_file() for name in asset["files"]):
            state = "MISSING"
        elif verify and payload_manifest(root) != asset["files"]:
            state = "CORRUPT"
        return {
            **asset,
            "local_status": state,
            "compatibility": "NOT_CHECKED",
            "command_path": "/assets/" + root.name
            if root.parent == self.service.root / "assets"
            else None,
        }

    def acquire(self, job):
        request = job["payload"]
        staging = self.service.root / "downloads" / job["id"]
        staging.mkdir(parents=True, exist_ok=True)
        provenance = {"source_id": request.get("source_id"), "repo_id": request.get("repo_id")}
        if request.get("source_id"):
            source = self.source(request["source_id"])
            if not request.get("repo_id"):
                raise ValueError("托管平台下载需要 repo_id。")
            api = self.api(source)
            info = api.repo_info(
                request["repo_id"], repo_type=request["kind"], revision=request["revision"]
            )
            if not info.sha:
                raise ValueError("远端没有提供固定 commit。")
            provenance.update(revision=info.sha, endpoint=source["endpoint"])
            snapshot_download(
                repo_id=request["repo_id"],
                repo_type=request["kind"],
                revision=info.sha,
                endpoint=source["endpoint"],
                token=self.token(source),
                local_dir=staging,
            )
            shutil.rmtree(staging / ".cache", ignore_errors=True)
        elif request.get("url"):
            url = http_url(request["url"])
            if urlsplit(url).query:
                raise ValueError("请使用不含查询凭据的稳定下载地址。")
            name = PurePosixPath(urlsplit(url).path).name or "download"
            with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
                response.raise_for_status()
                with safe_path(staging, name).open("wb") as output:
                    for chunk in response.iter_bytes():
                        output.write(chunk)
                provenance.update(url=url, etag=response.headers.get("etag"))
        elif request.get("local_path"):
            source = Path(request["local_path"]).resolve()
            self.platform.settings.host_path(source)
            if source.is_dir():
                if staging.resolve().is_relative_to(source):
                    raise ValueError("导入目录不能包含平台的下载暂存目录。")
                payload_manifest(source)
                shutil.copytree(source, staging, dirs_exist_ok=True)
            elif source.is_file():
                shutil.copyfile(source, staging / source.name)
            else:
                raise ValueError("本地导入路径不存在。")
            provenance["imported_from"] = str(source)
        else:
            raise ValueError("选择一个 source_id、url 或 local_path。")
        return self.adopt(staging, request, provenance)

    def adopt(self, staging, request, provenance):
        files = payload_manifest(staging)
        checksum = manifest_hash(files)
        target = self.service.root / "assets" / checksum
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if payload_manifest(target) != files:
                raise ValueError("已有本地副本损坏，不能复用。")
        else:
            staging.rename(target)
        identity = digest({"kind": request["kind"], "provenance": provenance, "checksum": checksum})
        asset = self.store.create(
            "asset",
            {
                "name": request["name"],
                "kind": request["kind"],
                "path": str(target),
                "files": files,
                "checksum": checksum,
                "revision": provenance.get("revision", checksum),
                "size": sum((target / name).stat().st_size for name in files),
                **provenance,
            },
            "asset:" + identity,
            "adopt",
        )
        return self.describe(asset["id"])

    def bind(self, asset_id, metadata):
        asset = self.describe(asset_id, verify=True)
        if asset["local_status"] != "DOWNLOADED":
            raise ValueError("资产文件不完整，请先重新获取。")
        # Binding records only describe a payload; compatibility is checked per run plan.
        if asset["kind"] == "dataset":
            required = {"train_split", "test_split"}
        else:
            required = {"architecture", "initialization", "parameter_count"}
        if not required <= metadata.keys():
            raise ValueError("缺少训练元数据：" + ", ".join(sorted(required - metadata.keys())))
        forbidden = {"id", "name", "version", "path", "files", "checksum"}
        if forbidden & metadata.keys():
            raise ValueError("元数据不能替换资产身份或文件清单。")
        name = asset_id
        version = "binding-" + digest(metadata)[:16]
        registered = self.platform.repo.register(
            asset["kind"],
            {
                **metadata,
                "name": name,
                "version": version,
                "path": asset["path"],
                "files": asset["files"],
                "checksum": asset["checksum"],
            },
        )
        binding = {
            "id": asset_id,
            "created_at": now(),
            "ref": {"name": registered["name"], "version": registered["version"]},
            "metadata": metadata,
        }
        self.store.put("binding", binding)
        return binding

    def resolve(self, asset_id):
        asset = self.describe(asset_id, verify=True)
        if asset["local_status"] != "DOWNLOADED":
            raise ValueError(f"资产 {asset_id} 的本地文件不可用。")
        if asset.get("legacy_ref"):
            return asset["kind"], asset["legacy_ref"]
        try:
            return asset["kind"], self.store.get("binding", asset_id)["ref"]
        except KeyError:
            # Standard layouts can be bound without a Ninna manifest; inspect metadata only.
            import json

            root = Path(asset["path"])
            card = root / "ninna-asset.json"
            if card.is_file():
                doc = json.loads(card.read_text())
                metadata = {
                    k: v
                    for k, v in doc["asset"].items()
                    if k not in {"id", "name", "version", "path", "files", "checksum"}
                }
            elif asset["kind"] == "model" and (root / "config.json").is_file():
                config = json.loads((root / "config.json").read_text())
                metadata = {
                    "architecture": config.get("model_type", "unknown"),
                    "initialization": {"source": asset_id},
                    "parameter_count": None,
                    "metadata": {"format": "huggingface.PreTrainedModel"},
                }
            else:
                raise ValueError(
                    f"资产 {asset_id} 已下载；请先补充 split 或模型加载元数据。"
                ) from None
            bound = self.bind(asset_id, metadata)
            return asset["kind"], bound["ref"]

    def publish(self, job):
        value = job["payload"]
        asset = self.describe(value["asset_id"], verify=True)
        if asset["local_status"] != "DOWNLOADED":
            raise ValueError("本地资产不可用。")
        source = self.source(value["source_id"])
        # Keep HF_ENDPOINT process-local, as in the existing uploader.
        import json
        import subprocess
        import sys

        process = subprocess.run(
            [sys.executable, "-m", "ninna.services.hub_upload"],
            input=json.dumps(
                {
                    "endpoint": source["endpoint"],
                    "token": self.token(source),
                    "repo_id": value["repo_id"],
                    "kind": asset["kind"],
                    "private": value["private"],
                    "folder": asset["path"],
                    "message": "Ninna asset " + asset["checksum"],
                }
            ),
            text=True,
            capture_output=True,
            timeout=3600,
            env={
                **os.environ,
                "HF_ENDPOINT": source["endpoint"],
                "HF_HUB_DISABLE_PROGRESS_BARS": "1",
            },
        )
        if process.returncode:
            raise ValueError("发布失败，请检查目标仓库和平台凭据。")
        receipt = json.loads(process.stdout.strip().splitlines()[-1])
        return {
            "source_id": source["id"],
            "repo_id": value["repo_id"],
            "revision": receipt["revision"],
            "asset_id": asset["id"],
        }
