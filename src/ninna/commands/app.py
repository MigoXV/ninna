from __future__ import annotations

import logging
import json
import urllib.request
import urllib.error

import typer

app = typer.Typer(no_args_is_help=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def request(url, body=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as response:
        return json.load(response)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", envvar="NINNA_BIND"),
    port: int = typer.Option(8000, envvar="NINNA_PORT"),
):
    import uvicorn
    from ninna.web.app import create_app

    uvicorn.run(create_app(), host=host, port=port)


@app.command()
def mcp(url: str = typer.Option("http://127.0.0.1:8000", envvar="NINNA_API_URL")):
    """启动 stdio MCP，连接已运行的平台；不创建第二个训练执行器。"""
    from ninna.agent.server import create_server

    create_server(url).run(transport="stdio")


@app.command()
def initialize(url: str = typer.Option("http://127.0.0.1:8000", envvar="NINNA_API_URL")):
    typer.echo(json.dumps(request(url + "/api/initialize", {}), ensure_ascii=False))


@app.command()
def migrate(
    apply: bool = typer.Option(False, "--apply", help="执行迁移；默认只读检查"),
    url: str = typer.Option("http://127.0.0.1:8000", envvar="NINNA_API_URL"),
):
    """检查或执行 v2 附加索引迁移，不改写历史 Run 和资产。"""
    import uuid

    value = request(url + "/api/v2/migration", {"request_id": uuid.uuid4().hex} if apply else None)
    typer.echo(json.dumps(value, ensure_ascii=False))


@app.command()
def upload(
    path: str = typer.Option(..., help="Codex 所在机器上的文件或目录"),
    kind: str = typer.Option(..., help="model 或 dataset"),
    name: str = typer.Option(...),
    request_id: str = typer.Option(..., help="重试时复用此 ID"),
    url: str = typer.Option("http://127.0.0.1:8000", envvar="NINNA_API_URL"),
):
    """流式上传本地文件至 Ninna，无需共享文件系统。"""
    from pathlib import Path
    import httpx
    from ninna.services.assets import checksum

    source = Path(path).resolve()
    if kind not in {"model", "dataset"} or not source.exists():
        raise typer.BadParameter("需要有效路径及 model/dataset 类型")
    files = sorted(source.rglob("*")) if source.is_dir() else [source]
    if any(p.is_symlink() for p in files):
        raise typer.BadParameter("上传目录不能包含符号链接")
    with httpx.Client(base_url=url, timeout=600) as client:
        response = client.post(
            "/api/v2/uploads", json={"kind": kind, "name": name, "request_id": request_id}
        )
        response.raise_for_status()
        value = response.json()
        if value.get("asset_id"):
            typer.echo(json.dumps(value, ensure_ascii=False))
            return
        key = value["id"]
        for item in files:
            if not item.is_file():
                continue
            relative = str(item.relative_to(source)) if source.is_dir() else item.name
            with item.open("rb") as stream:
                response = client.put(
                    f"/api/v2/uploads/{key}/files",
                    params={"path": relative, "sha256": checksum(item)},
                    content=iter(lambda: stream.read(1024 * 1024), b""),
                )
                response.raise_for_status()
        response = client.post(
            f"/api/v2/uploads/{key}/complete", json={"request_id": request_id + ":complete"}
        )
        response.raise_for_status()
        typer.echo(json.dumps(response.json(), ensure_ascii=False))


if __name__ == "__main__":
    app()
