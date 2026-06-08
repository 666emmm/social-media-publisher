"""_record_publish 接受 account_configs 参数并写入 publish_tasks.account_configs。"""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def test_record_publish_writes_account_configs():
    """_record_publish 接受 account_configs 形参并 JSON 序列化写入列。"""
    from app import _record_publish
    import sqlite3

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE publish_tasks (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            account_name TEXT NOT NULL,
            video_path TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            error_message TEXT DEFAULT '',
            publish_url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            thumbnail_path TEXT DEFAULT '',
            account_configs TEXT DEFAULT '{}'
        );
    """)
    conn.commit()
    conn.close()

    with patch("app.DB_PATH", db_path):
        _record_publish(
            task_id="uuid-1",
            platform="douyin",
            account_name="测试账号",
            video_path="/tmp/v.mp4",
            title="t",
            description="d",
            tags=["a"],
            status="running",
            started_at="2026-06-08T10:00:00",
            account_configs={"douyin": {"title": "per-platform title", "tags": ["x"]}},
        )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT account_configs FROM publish_tasks WHERE id = ?", ("uuid-1",)
    ).fetchone()
    stored = json.loads(row[0])
    assert stored == {"douyin": {"title": "per-platform title", "tags": ["x"]}}
    conn.close()


def test_record_publish_default_account_configs():
    """不传 account_configs 时默认写 '{}'。"""
    from app import _record_publish
    import sqlite3

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE publish_tasks (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            account_name TEXT NOT NULL,
            video_path TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            error_message TEXT DEFAULT '',
            publish_url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            thumbnail_path TEXT DEFAULT '',
            account_configs TEXT DEFAULT '{}'
        );
    """)
    conn.commit()
    conn.close()

    with patch("app.DB_PATH", db_path):
        _record_publish(
            task_id="uuid-2",
            platform="douyin",
            account_name="x",
            video_path="/v",
            title="t",
            description="",
            tags=[],
            status="running",
            started_at="2026-06-08T10:00:00",
        )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT account_configs FROM publish_tasks WHERE id = ?", ("uuid-2",)
    ).fetchone()
    assert row[0] == "{}"
    conn.close()
