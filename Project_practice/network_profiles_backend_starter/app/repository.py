import json
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

from app.database import get_connection
from app.schemas import NetworkProfileCreate, NetworkProfileUpdate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_profile(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "host": row["host"],
        "port": row["port"],
        "protocol": row["protocol"],
        "status": row["status"],
        "description": row["description"],
        "config": json.loads(row["config_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_action(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "profile_id": row["profile_id"],
        "action": row["action"],
        "result": row["result"],
        "message": row["message"],
        "created_at": row["created_at"],
    }


def list_profiles() -> list[dict[str, Any]]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM network_profiles ORDER BY id DESC"
        ).fetchall()
    return [_row_to_profile(row) for row in rows]


def get_profile(profile_id: int) -> dict[str, Any] | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM network_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
    return _row_to_profile(row) if row else None


def create_profile(data: NetworkProfileCreate) -> dict[str, Any]:
    timestamp = _now()
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO network_profiles
            (name, host, port, protocol, status, description, config_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'inactive', ?, ?, ?, ?)
            """,
            (
                data.name,
                data.host,
                data.port,
                data.protocol,
                data.description,
                json.dumps(data.config, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
        connection.commit()
        profile_id = int(cursor.lastrowid)

    profile = get_profile(profile_id)
    if profile is None:
        raise RuntimeError("Created profile could not be read back")
    return profile


def update_profile(profile_id: int, data: NetworkProfileUpdate) -> dict[str, Any] | None:
    existing = get_profile(profile_id)
    if existing is None:
        return None

    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return existing

    column_map = {
        "name": "name",
        "host": "host",
        "port": "port",
        "protocol": "protocol",
        "description": "description",
        "config": "config_json",
    }

    assignments: list[str] = []
    values: list[Any] = []

    for field, value in changes.items():
        assignments.append(f"{column_map[field]} = ?")
        if field == "config":
            value = json.dumps(value, ensure_ascii=False)
        values.append(value)

    assignments.append("updated_at = ?")
    values.extend([_now(), profile_id])

    with closing(get_connection()) as connection:
        connection.execute(
            f"UPDATE network_profiles SET {', '.join(assignments)} WHERE id = ?",
            values,
        )
        connection.commit()

    return get_profile(profile_id)


def delete_profile(profile_id: int) -> bool:
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            "DELETE FROM network_profiles WHERE id = ?",
            (profile_id,),
        )
        connection.commit()
    return cursor.rowcount > 0


def set_profile_status(profile_id: int, status: str) -> dict[str, Any] | None:
    if get_profile(profile_id) is None:
        return None

    with closing(get_connection()) as connection:
        connection.execute(
            """
            UPDATE network_profiles
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, _now(), profile_id),
        )
        connection.commit()
    return get_profile(profile_id)


def reset_active_statuses() -> None:
    """Avoid stale 'active' values after backend restart."""
    with closing(get_connection()) as connection:
        connection.execute(
            """
            UPDATE network_profiles
            SET status = 'inactive', updated_at = ?
            WHERE status = 'active'
            """,
            (_now(),),
        )
        connection.commit()


def add_action_log(
    profile_id: int | None,
    action: str,
    result: str,
    message: str,
) -> dict[str, Any]:
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO action_logs (profile_id, action, result, message, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (profile_id, action, result, message[:4000], _now()),
        )
        connection.commit()
        action_id = int(cursor.lastrowid)
        row = connection.execute(
            "SELECT * FROM action_logs WHERE id = ?",
            (action_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("Created action log could not be read back")
    return _row_to_action(row)


def list_action_logs(
    profile_id: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 500))
    with closing(get_connection()) as connection:
        if profile_id is None:
            rows = connection.execute(
                "SELECT * FROM action_logs ORDER BY id DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM action_logs
                WHERE profile_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (profile_id, safe_limit),
            ).fetchall()
    return [_row_to_action(row) for row in rows]
