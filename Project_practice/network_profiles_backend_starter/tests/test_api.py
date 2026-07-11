import os
import time
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["NETWORK_CORE_MODE"] = "demo"

from app.main import app


VALID_PROFILE = {
    "name": "Demo profile",
    "host": "127.0.0.1",
    "port": 10808,
    "protocol": "socks",
    "description": "Profile for integration tests",
    "config": {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "listen": "127.0.0.1",
                "port": 10808,
                "protocol": "socks",
                "settings": {"udp": True},
            }
        ],
        "outbounds": [{"protocol": "freedom", "settings": {}}],
    },
}


@pytest.fixture
def database_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "test_profiles.db"
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("NETWORK_CORE_MODE", "demo")
    return path


@pytest.fixture
def client(database_path: Path):
    with TestClient(app) as test_client:
        yield test_client

    assert database_path.exists()
    database_path.unlink()
    assert not database_path.exists()


def create_profile(client: TestClient, **overrides):
    payload = {**VALID_PROFILE, **overrides}
    response = client.post("/api/profiles", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def assert_valid_profile_shape(profile: dict) -> None:
    expected_keys = {
        "id",
        "name",
        "host",
        "port",
        "protocol",
        "status",
        "description",
        "config",
        "created_at",
        "updated_at",
    }
    assert set(profile) == expected_keys
    assert isinstance(profile["id"], int)
    datetime.fromisoformat(profile["created_at"].replace("Z", "+00:00"))
    datetime.fromisoformat(profile["updated_at"].replace("Z", "+00:00"))


def test_health_and_openapi(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "core_mode": "demo"}

    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/profiles",
        "/api/profiles/{profile_id}",
        "/api/profiles/{profile_id}/validate",
        "/api/profiles/{profile_id}/activate",
        "/api/profiles/{profile_id}/deactivate",
        "/api/profiles/{profile_id}/restart",
        "/api/profiles/{profile_id}/runtime",
        "/api/profiles/{profile_id}/logs",
        "/api/actions",
    ):
        assert path in paths


def test_new_database_is_empty(client: TestClient) -> None:
    assert client.get("/api/profiles").json() == []
    assert client.get("/api/actions").json() == []


def test_create_and_get_profile(client: TestClient) -> None:
    created = create_profile(client)
    assert_valid_profile_shape(created)
    assert created["config"] == VALID_PROFILE["config"]
    assert created["status"] == "inactive"
    assert client.get(f"/api/profiles/{created['id']}").json() == created


def test_create_writes_action_log(client: TestClient) -> None:
    created = create_profile(client)
    actions = client.get("/api/actions").json()
    assert len(actions) == 1
    assert actions[0]["profile_id"] == created["id"]
    assert actions[0]["action"] == "create"
    assert actions[0]["result"] == "success"


def test_unicode_special_characters_and_nested_json(client: TestClient) -> None:
    created = create_profile(
        client,
        name="Профиль №1 — Việt Nam 'test'",
        description="Русский текст, tiếng Việt и кавычки: ' \"",
        config={
            "unicode": "Привет — Xin chào",
            "boolean": False,
            "number": 12.5,
            "null_value": None,
            "list": [1, "two", {"three": 3}],
        },
    )
    assert client.get(f"/api/profiles/{created['id']}").json() == created


def test_list_profiles_newest_first(client: TestClient) -> None:
    first = create_profile(client, name="First")
    second = create_profile(client, name="Second")
    profiles = client.get("/api/profiles").json()
    assert [profile["id"] for profile in profiles] == [second["id"], first["id"]]


def test_partial_update_and_null_description(client: TestClient) -> None:
    created = create_profile(client)
    old_updated_at = created["updated_at"]
    time.sleep(0.002)
    response = client.patch(
        f"/api/profiles/{created['id']}",
        json={
            "name": "Updated profile",
            "port": 8443,
            "description": None,
            "config": {"replaced": True},
        },
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Updated profile"
    assert updated["port"] == 8443
    assert updated["description"] is None
    assert updated["config"] == {"replaced": True}
    assert updated["updated_at"] != old_updated_at


def test_empty_patch_keeps_profile_unchanged(client: TestClient) -> None:
    created = create_profile(client)
    response = client.patch(f"/api/profiles/{created['id']}", json={})
    assert response.status_code == 200
    assert response.json() == created


def test_validate_config_in_demo_mode_writes_file(
    client: TestClient,
    tmp_path: Path,
) -> None:
    created = create_profile(client)
    response = client.post(f"/api/profiles/{created['id']}/validate")
    assert response.status_code == 200
    result = response.json()
    assert result["valid"] is True
    assert result["mode"] == "demo"
    assert Path(result["config_path"]).exists()


def test_empty_config_validation_returns_422(client: TestClient) -> None:
    created = create_profile(client, config={})
    response = client.post(f"/api/profiles/{created['id']}/validate")
    assert response.status_code == 422
    assert "non-empty" in response.json()["detail"]
    assert client.get(f"/api/profiles/{created['id']}").json()["status"] == "error"


def test_activate_restart_and_deactivate(client: TestClient) -> None:
    created = create_profile(client)

    activated = client.post(f"/api/profiles/{created['id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"

    restarted = client.post(f"/api/profiles/{created['id']}/restart")
    assert restarted.status_code == 200
    assert restarted.json()["status"] == "active"

    deactivated = client.post(f"/api/profiles/{created['id']}/deactivate")
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "inactive"

    actions = client.get(f"/api/actions?profile_id={created['id']}").json()
    action_names = [item["action"] for item in actions]
    assert "activate" in action_names
    assert "restart" in action_names
    assert "deactivate" in action_names


def test_runtime_and_empty_logs(client: TestClient) -> None:
    created = create_profile(client)
    runtime = client.get(f"/api/profiles/{created['id']}/runtime")
    assert runtime.status_code == 200
    assert runtime.json() == {
        "profile_id": created["id"],
        "mode": "demo",
        "status": "inactive",
        "running": False,
        "pid": None,
        "message": "Demo profile is inactive",
    }
    logs = client.get(f"/api/profiles/{created['id']}/logs").json()
    assert logs == {"profile_id": created["id"], "lines": []}



def test_runtime_reflects_demo_activation_and_active_profile_is_locked(client: TestClient) -> None:
    created = create_profile(client)
    client.post(f"/api/profiles/{created['id']}/activate")

    runtime = client.get(f"/api/profiles/{created['id']}/runtime").json()
    assert runtime["running"] is True
    assert runtime["status"] == "active"
    assert runtime["message"] == "Demo profile is active"

    update = client.patch(
        f"/api/profiles/{created['id']}",
        json={"name": "Should not update while active"},
    )
    assert update.status_code == 409

    delete = client.delete(f"/api/profiles/{created['id']}")
    assert delete.status_code == 409

    client.post(f"/api/profiles/{created['id']}/deactivate")
    assert client.patch(
        f"/api/profiles/{created['id']}",
        json={"name": "Updated after stop"},
    ).status_code == 200

def test_delete_profile(client: TestClient) -> None:
    created = create_profile(client)
    response = client.delete(f"/api/profiles/{created['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/api/profiles/{created['id']}").status_code == 404
    assert client.delete(f"/api/profiles/{created['id']}").status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("get", "/api/profiles/999999", None),
        ("patch", "/api/profiles/999999", {"name": "Missing"}),
        ("delete", "/api/profiles/999999", None),
        ("post", "/api/profiles/999999/validate", None),
        ("post", "/api/profiles/999999/activate", None),
        ("post", "/api/profiles/999999/deactivate", None),
        ("post", "/api/profiles/999999/restart", None),
        ("get", "/api/profiles/999999/runtime", None),
        ("get", "/api/profiles/999999/logs", None),
    ],
)
def test_missing_profile_returns_404(
    client: TestClient,
    method: str,
    path: str,
    json_body: dict | None,
) -> None:
    response = client.request(method, path, json=json_body)
    assert response.status_code == 404
    assert response.json() == {"detail": "Profile not found"}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**VALID_PROFILE, "name": ""},
        {**VALID_PROFILE, "host": ""},
        {**VALID_PROFILE, "protocol": ""},
        {**VALID_PROFILE, "port": 0},
        {**VALID_PROFILE, "port": 65536},
        {**VALID_PROFILE, "port": "not-a-number"},
        {**VALID_PROFILE, "config": ["must", "be", "an", "object"]},
        {**VALID_PROFILE, "name": "x" * 101},
        {**VALID_PROFILE, "description": "x" * 501},
    ],
)
def test_invalid_create_payload_returns_422(client: TestClient, payload: dict) -> None:
    assert client.post("/api/profiles", json=payload).status_code == 422


def test_invalid_update_payload_returns_422(client: TestClient) -> None:
    created = create_profile(client)
    for payload in (
        {"name": ""},
        {"host": ""},
        {"protocol": ""},
        {"port": 0},
        {"port": 65536},
        {"config": []},
    ):
        assert client.patch(
            f"/api/profiles/{created['id']}", json=payload
        ).status_code == 422


def test_invalid_path_parameter_returns_422(client: TestClient) -> None:
    assert client.get("/api/profiles/not-an-integer").status_code == 422


def test_malformed_json_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/profiles",
        content=b'{"name": "broken",',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422


def test_allowed_frontend_origin_has_cors_headers(client: TestClient) -> None:
    response = client.options(
        "/api/profiles",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unknown_origin_is_not_allowed_by_cors(client: TestClient) -> None:
    response = client.get(
        "/api/profiles",
        headers={"Origin": "https://unknown.example"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_action_limit_validation(client: TestClient) -> None:
    assert client.get("/api/actions?limit=0").status_code == 422
    assert client.get("/api/actions?limit=501").status_code == 422


def test_log_lines_validation(client: TestClient) -> None:
    created = create_profile(client)
    assert client.get(f"/api/profiles/{created['id']}/logs?lines=0").status_code == 422
    assert client.get(f"/api/profiles/{created['id']}/logs?lines=1001").status_code == 422


def test_data_survives_application_restart(database_path: Path) -> None:
    with TestClient(app) as first_client:
        created = create_profile(first_client, name="Persistent profile")
    with TestClient(app) as second_client:
        response = second_client.get(f"/api/profiles/{created['id']}")
        assert response.status_code == 200
        assert response.json()["name"] == "Persistent profile"
    database_path.unlink()
    assert not database_path.exists()
