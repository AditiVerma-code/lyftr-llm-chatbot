import sqlite3
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from app.config import settings


def parse_db_path(url: str) -> str:
    """
    Parses SQLite connection string into an actual filesystem path.
    Handles:
      sqlite:////data/app.db -> /data/app.db (absolute path)
      sqlite:///data/app.db  -> data/app.db (relative path)
      sqlite:///./app.db     -> ./app.db
      sqlite://:memory:      -> :memory:
    """
    if url == "sqlite://:memory:":
        return ":memory:"
    if url.startswith("sqlite:////"):
        path = "/" + url[len("sqlite:////"):]
    elif url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
    elif url.startswith("sqlite://"):
        path = url[len("sqlite://"):]
    else:
        path = url

    if path != ":memory:":
        dir_name = os.path.dirname(os.path.abspath(path))
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
    return path


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    target_path = db_path or parse_db_path(settings.DATABASE_URL)
    conn = sqlite3.connect(target_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(database_url: Optional[str] = None) -> None:
    path = parse_db_path(database_url or settings.DATABASE_URL)
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, id);
        """)
        conn.commit()


def check_db_health(database_url: Optional[str] = None) -> bool:
    try:
        path = parse_db_path(database_url or settings.DATABASE_URL)
        with sqlite3.connect(path, timeout=2.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            return cursor.fetchone() is not None
    except Exception:
        return False


def add_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
    created_at: Optional[str] = None,
    db_path: Optional[str] = None
) -> int:
    path = db_path or parse_db_path(settings.DATABASE_URL)
    iso_time = created_at or datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata) if metadata is not None else None

    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO messages (session_id, role, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, role, content, meta_json, iso_time)
        )
        conn.commit()
        return cursor.lastrowid


def session_exists(session_id: str, db_path: Optional[str] = None) -> bool:
    path = db_path or parse_db_path(settings.DATABASE_URL)
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM messages WHERE session_id = ? LIMIT 1", (session_id,))
        return cursor.fetchone() is not None


def get_session_messages(session_id: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns the stored history of one session from SQLite, oldest first, without the system prompt.
    """
    path = db_path or parse_db_path(settings.DATABASE_URL)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, session_id, role, content, metadata, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,)
        )
        rows = cursor.fetchall()

    result = []
    for row in rows:
        item = {
            "role": row["role"],
            "content": row["content"]
        }
        if row["metadata"]:
            try:
                item["metadata"] = json.loads(row["metadata"])
            except Exception:
                item["metadata"] = {}
        result.append(item)
    return result
