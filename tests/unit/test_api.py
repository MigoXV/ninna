from fastapi.testclient import TestClient
from ninna.config import Settings
from ninna.web.app import create_app


def test_api_errors_and_static_routes(tmp_path):
    dist = tmp_path / "src/web/dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>ninna frontend</html>")
    (dist / "app.js").write_text('console.log("asset")')
    app = create_app(Settings(tmp_path, tmp_path, tmp_path / "state"))
    client = TestClient(app)
    assert client.get("/api/assets/dataset").json() == []
    assert client.get("/api/runs/missing").status_code == 404
    for accept in ["text/html", "application/json"]:
        response = client.get("/api/unknown", headers={"accept": accept})
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"
    assert "ninna frontend" in client.get("/runs/nested", headers={"accept": "text/html"}).text
    assert "console.log" in client.get("/app.js").text
    assert client.get("/openapi.json").status_code == 200


def test_missing_frontend_fails_clearly(tmp_path):
    import pytest

    with pytest.raises(RuntimeError, match="Frontend missing"):
        create_app(Settings(tmp_path, tmp_path, tmp_path / "state"))
