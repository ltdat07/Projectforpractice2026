import os
import sqlite3
from contextlib import closing
from pathlib import Path


def get_database_path() -> Path:
    default_path = Path(__file__).resolve().parent.parent / "profiles.db"
    return Path(os.getenv("DATABASE_PATH", str(default_path)))


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(get_database_path())
    connection.row_factory = sqlite3.Row
    return connection


def init_database() -> None:
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with closing(get_connection()) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS network_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL CHECK (port BETWEEN 1 AND 65535),
                protocol TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'inactive',
                description TEXT,
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS action_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER,
                action TEXT NOT NULL,
                result TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_action_logs_profile_id ON action_logs(profile_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_action_logs_created_at ON action_logs(created_at)"
        )
        connection.commit()
