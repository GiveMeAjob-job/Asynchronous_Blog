def test_app_module_imports():
    import app.main  # noqa: F401


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert "timestamp" in payload


def test_openapi_contains_core_routes(client):
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/posts/" in paths
    assert "/api/v1/comments/post/{post_id}" in paths
