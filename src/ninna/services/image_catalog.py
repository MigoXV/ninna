"""Read-only image directory derived from immutable registration evidence."""

from __future__ import annotations

from collections import defaultdict


def parse_reference(source: str) -> dict:
    repository, separator, digest = source.partition("@")
    tag = None
    if not separator and ":" in repository.rsplit("/", 1)[-1]:
        repository, tag = repository.rsplit(":", 1)
    parts = repository.split("/")
    if any(not part for part in parts) or tag == "":
        raise ValueError("镜像引用缺少名称或版本。")
    if len(parts) > 1 and ("." in parts[0] or ":" in parts[0] or parts[0] == "localhost"):
        registry, parts = parts[0].lower(), parts[1:]
    else:
        registry = "docker.io"
    if registry in {"index.docker.io", "registry-1.docker.io"}:
        registry = "docker.io"
    namespace = "/".join(parts[:-1]) or ("library" if registry == "docker.io" else "_")
    return {
        "registry": registry,
        "namespace": namespace,
        "repository": parts[-1],
        "reference": digest if separator else tag or "latest",
    }


def location(asset: dict) -> dict:
    source = asset["source_reference"]
    if not source.startswith("sha256:"):
        return parse_reference(source)
    candidates = [parse_reference(tag) for tag in asset.get("tags", [])]
    repositories = {(c["registry"], c["namespace"], c["repository"]) for c in candidates}
    if len(repositories) == 1:
        value = candidates[0]
        references = {c["reference"] for c in candidates}
        return {
            **value,
            "registry": "local",
            "reference": next(iter(references)) if len(references) == 1 else source,
        }
    return {
        "registry": "local",
        "namespace": "_",
        "repository": "unclassified",
        "reference": source,
    }


def browse(assets: list[dict], registry=None, namespace=None, repository=None, q="") -> dict:
    if (namespace is not None and registry is None) or (
        repository is not None and namespace is None
    ):
        raise ValueError("镜像目录必须按站点、命名空间、镜像顺序查询。")
    scope = {
        k: v
        for k, v in {"registry": registry, "namespace": namespace, "repository": repository}.items()
        if v is not None
    }
    versions = {}
    for asset in assets:
        loc = location(asset)
        if any(loc[k] != v for k, v in scope.items()):
            continue
        if (
            q
            and q.casefold()
            not in " ".join(
                [
                    asset["name"],
                    asset["version"],
                    asset["source_reference"],
                    *asset.get("tags", []),
                    "/".join(loc.values()),
                ]
            ).casefold()
        ):
            continue
        key = (
            *[loc[k] for k in ("registry", "namespace", "repository", "reference")],
            asset["image_id"],
        )
        if key not in versions:
            versions[key] = {
                **loc,
                "image_id": asset["image_id"],
                "platform": "/".join(
                    filter(None, [asset.get("os"), asset.get("architecture"), asset.get("variant")])
                ),
                "size": asset.get("size", 0),
                "created_at": asset.get("created_at", ""),
                "assets": [],
            }
        row = versions[key]
        row["created_at"] = max(row["created_at"], asset.get("created_at", ""))
        row["assets"].append({k: asset[k] for k in ("id", "name", "version")})
    values = list(versions.values())
    for row in values:
        row["assets"].sort(key=lambda a: (a["name"], a["version"]))
    level = (
        "versions"
        if q or repository is not None
        else "repositories"
        if namespace is not None
        else "namespaces"
        if registry is not None
        else "registries"
    )
    if level == "versions":
        items = sorted(
            values, key=lambda r: (r["created_at"], r["reference"], r["image_id"]), reverse=True
        )
    else:
        field = {"registries": "registry", "namespaces": "namespace", "repositories": "repository"}[
            level
        ]
        grouped = defaultdict(list)
        for row in values:
            grouped[row[field]].append(row)
        items = []
        for name, rows in sorted(grouped.items()):
            items.append(
                {
                    "name": name,
                    "scope": {**scope, field: name},
                    "namespace_count": len({r["namespace"] for r in rows}),
                    "repository_count": len({(r["namespace"], r["repository"]) for r in rows}),
                    "version_count": len(rows),
                    "asset_count": sum(len(r["assets"]) for r in rows),
                    "platforms": sorted({r["platform"] for r in rows}),
                    "created_at": max(r["created_at"] for r in rows),
                }
            )
    return {
        "level": level,
        "scope": scope,
        "query": q,
        "items": items,
        "version_count": len(values),
        "asset_count": sum(len(r["assets"]) for r in values),
    }
