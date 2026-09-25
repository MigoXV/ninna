from __future__ import annotations

import logging
import time
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
def certify(
    quick: bool = typer.Option(False),
    url: str = typer.Option("http://127.0.0.1:8000", envvar="NINNA_API_URL"),
):
    try:
        record = request(url + "/api/certifications", {"quick": quick})
        typer.echo("MNIST Platform Certification\n")
        seen = 0
        deadline = time.monotonic() + 4000
        while True:
            record = request(url + "/api/certifications/" + record["id"])
            for check in record["checks"][seen:]:
                typer.echo(
                    f"{check['name']:<44} {check['status']}"
                    + (f"  {check['evidence']}" if "accuracy" in check["name"] else "")
                )
            seen = len(record["checks"])
            if record["status"] != "RUNNING":
                break
            if time.monotonic() > deadline:
                raise TimeoutError("Certification timed out")
            time.sleep(2)
        typer.echo(f"\nReport: {record['id']}\nRuns: {', '.join(record['run_ids'])}")
        typer.echo(f"\nOVERALL {record['status']}")
        if record["status"] != "PASS":
            typer.echo(record["failure_reason"])
            raise typer.Exit(1)
    except (urllib.error.URLError, TimeoutError) as exc:
        typer.echo(f"OVERALL FAIL\n{exc}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
