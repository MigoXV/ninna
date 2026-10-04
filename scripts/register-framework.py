"""将本地构建镜像、框架、Runtime 与示例配方注册到一个正在运行的 Ninna。"""

import argparse
from pathlib import Path
import json
import httpx
import yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repository", type=Path)
    parser.add_argument("--api", default="http://127.0.0.1:8011")
    parser.add_argument("--image", required=True)
    parser.add_argument("--version", default="ninna-v1")
    parser.add_argument("--workspace-name", help="Override the new editable workspace name")
    args = parser.parse_args()
    spec = yaml.safe_load((args.repository / "ninna-framework.yaml").read_text())
    name = spec["name"]
    framework = {k: spec[k] for k in ("name", "version")}
    with httpx.Client(base_url=args.api + "/api", timeout=300) as client:

        def post(path, body):
            response = client.post(path, json=body)
            if response.is_error:
                raise ValueError(f"{path}: {response.text}")
            return response.json()

        def register(kind, value):
            existing = client.get(f"/assets/{kind}/{value['name']}/{value['version']}")
            if existing.status_code == 200:
                return existing.json()["asset"]
            if existing.status_code not in (400, 404):
                existing.raise_for_status()
            return post(f"/assets/{kind}", value)

        image = register("image", {"name": name, "version": args.version, "source": args.image})
        image_ref = {k: image[k] for k in ("name", "version")}
        workspace_name = args.workspace_name or name + "-" + args.version
        if client.get(f"/assets/workspace/{workspace_name}/v1").status_code != 200:
            post("/frameworks/import", {"image": image_ref, "workspace_name": workspace_name})
        register(
            "runtime",
            {"name": name, "version": args.version, "image_ref": image_ref, "framework": framework},
        )
        for path in sorted((args.repository / "examples/ninna").glob("*.yaml")):
            task = next(
                (
                    task
                    for task in sorted(spec["tasks"], key=len, reverse=True)
                    if path.stem.startswith(task)
                ),
                None,
            )
            if task is None:
                raise ValueError(f"Recipe filename must begin with task: {path}")
            for operation in ("train", "evaluate"):
                if operation not in spec["tasks"][task]["operations"]:
                    continue
                register(
                    "recipe",
                    {
                        "name": f"{name}-{path.stem}-{operation}",
                        "version": args.version,
                        "framework": framework,
                        "task": task,
                        "operation": operation,
                        "config": yaml.safe_load(path.read_text()),
                        "metadata": {
                            "source": str(path.relative_to(args.repository)),
                            "purpose": "smoke",
                        },
                    },
                )
        for path in sorted((args.repository / "examples/ninna/operations").glob("*.yaml")):
            operation = yaml.safe_load(path.read_text())
            register(
                "recipe",
                {
                    "name": f"{name}-{path.stem}",
                    "version": args.version,
                    "framework": framework,
                    **operation,
                },
            )
        for task, definition in spec["tasks"].items():
            if "export" in definition["operations"]:
                register(
                    "recipe",
                    {
                        "name": f"{name}-{task}-export",
                        "version": args.version,
                        "framework": framework,
                        "task": task,
                        "operation": "export",
                        "config": {},
                    },
                )
        print(
            json.dumps(
                {
                    "framework": framework,
                    "runtime": {"name": name, "version": args.version},
                    "workspace": workspace_name,
                }
            )
        )


if __name__ == "__main__":
    main()
