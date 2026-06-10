"""
HIVE v4.1 — Session 持久化管理器（SQLite）

职责:
- session CRUD（创建 / 读取 / 更新 / 删除）
- 项目去重（同名项目的 active session 只允许一个）
- 成本日志记录 / 查询
- 状态持久化（跨进程可用）

Schema:

CREATE TABLE sessions (
    session_id      TEXT PRIMARY KEY,
    project_name    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'idle',
    state           TEXT NOT NULL DEFAULT 'idle',
    current_version INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    brief_json      TEXT,
    dag_json        TEXT,
    total_cost_usd  REAL DEFAULT 0.0
);

CREATE TABLE versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    version         INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    summary         TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE cost_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    version         INTEGER,
    phase           TEXT NOT NULL,
    tokens_in       INTEGER DEFAULT 0,
    tokens_out      INTEGER DEFAULT 0,
    cost_usd        REAL DEFAULT 0.0,
    logged_at       TEXT NOT NULL
);
"""

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── 路径 ──

_HIVE_DIR = Path.home() / ".hermes" / "hive-v4"
_DB_PATH = _HIVE_DIR / "sessions.db"

# ── 并发写锁（协程/线程安全） ──

_write_lock = threading.Lock()


@contextmanager
def _write_conn():
    """获取写连接（自动加锁 + 关闭）。"""
    with _write_lock:
        conn = sqlite3.connect(str(_DB_PATH))
        try:
            yield conn
        finally:
            conn.close()


def _ensure_db():
    """确保数据库目录和表存在。"""
    _HIVE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id      TEXT PRIMARY KEY,
            project_name    TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'idle',
            state           TEXT NOT NULL DEFAULT 'idle',
            current_version INTEGER DEFAULT 0,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            brief_json      TEXT,
            dag_json        TEXT,
            total_cost_usd  REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS versions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            version         INTEGER NOT NULL,
            status          TEXT NOT NULL DEFAULT 'active',
            summary         TEXT,
            created_at      TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS cost_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            version         INTEGER,
            phase           TEXT NOT NULL,
            tokens_in       INTEGER DEFAULT 0,
            tokens_out      INTEGER DEFAULT 0,
            cost_usd        REAL DEFAULT 0.0,
            logged_at       TEXT NOT NULL
        );
    """)
    conn.commit()
    # 清理旧版 _schema_version 表（原无 UNIQUE 约束导致每次 INSERT 一行）
    try:
        conn.execute("DROP TABLE IF EXISTS _schema_version")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    # 确保 error_message 列存在（兼容新旧数据库）
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN error_message TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 列已存在
    # 再次清理 _schema_version（某些并发场景下前一次 DROP 可能未生效）
    try:
        conn.execute("DROP TABLE IF EXISTS _schema_version")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()


# ── Session CRUD ──


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_session_id(project_name: str) -> str:
    """生成唯一 session ID。"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rand = time.time_ns() % 1000000
    safe_name = "".join(c for c in project_name if c.isalnum() or c in "_")[:8]
    return f"v4_{stamp}_{rand}_{safe_name}"


class SessionManager:
    """纯函数式 Session 管理，无状态（所有数据持久化到 SQLite）。"""

    @classmethod
    def create_session(
        cls,
        project_name: str,
        brief: Optional[dict] = None,
    ) -> dict:
        """
        创建新 session。

        去重规则:
        - 如果 project_name 已有一个 status != 'cancelled' 的 session，
          返回现有 session_id，不新建。
        - 用户必须显式 hive_delete_project 才能清除。

        返回: {"session_id": str, "project_name": str, "status": str, "created": bool}
        """
        _ensure_db()

        # 读检查（WAL 模式安全，不需要写锁）
        conn = sqlite3.connect(str(_DB_PATH))
        existing = conn.execute(
            "SELECT session_id, status FROM sessions WHERE project_name = ? AND status NOT IN ('cancelled', 'deleted')",
            (project_name,),
        ).fetchone()
        conn.close()

        if existing:
            return {
                "session_id": existing[0],
                "project_name": project_name,
                "status": existing[1],
                "created": False,
            }

        # 写操作（加锁）
        session_id = _gen_session_id(project_name)
        now = _now()
        brief_str = json.dumps(brief, ensure_ascii=False) if brief else ""

        with _write_conn() as conn:
            conn.execute(
                """INSERT INTO sessions (session_id, project_name, status, state, created_at, updated_at, brief_json)
                   VALUES (?, ?, 'idle', 'idle', ?, ?, ?)""",
                (session_id, project_name, now, now, brief_str),
            )
            conn.commit()

        return {
            "session_id": session_id,
            "project_name": project_name,
            "status": "idle",
            "created": True,
        }

    @classmethod
    def get_session(cls, session_id: str) -> Optional[dict]:
        """获取 session 详情。"""
        _ensure_db()
        conn = sqlite3.connect(str(_DB_PATH))
        row = conn.execute(
            "SELECT session_id, project_name, status, state, current_version, created_at, updated_at, brief_json, dag_json, total_cost_usd "
            "FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        conn.close()

        if not row:
            return None

        return {
            "session_id": row[0],
            "project_name": row[1],
            "status": row[2],
            "state": row[3],
            "current_version": row[4],
            "created_at": row[5],
            "updated_at": row[6],
            "brief": json.loads(row[7]) if row[7] else None,
            "dag": json.loads(row[8]) if row[8] else None,
            "total_cost_usd": row[9],
        }

    @classmethod
    def update_state(cls, session_id: str, status: str, state: str):
        """更新 session 状态。"""
        _ensure_db()
        with _write_conn() as conn:
            conn.execute(
                "UPDATE sessions SET status = ?, state = ?, updated_at = ? WHERE session_id = ?",
                (status, state, _now(), session_id),
            )
            conn.commit()

    @classmethod
    def update_brief(cls, session_id: str, brief: dict):
        """保存 brief.json 到 session。"""
        _ensure_db()
        with _write_conn() as conn:
            conn.execute(
                "UPDATE sessions SET brief_json = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(brief, ensure_ascii=False), _now(), session_id),
            )
            conn.commit()

    @classmethod
    def update_dag(cls, session_id: str, dag: dict):
        """保存 dag.json 到 session。"""
        _ensure_db()
        with _write_conn() as conn:
            conn.execute(
                "UPDATE sessions SET dag_json = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(dag, ensure_ascii=False), _now(), session_id),
            )
            conn.commit()

    @classmethod
    def update_error(cls, session_id: str, error_message: str):
        """保存错误信息到 session。"""
        _ensure_db()
        with _write_conn() as conn:
            # 动态添加 error_message 列（兼容旧库）
            try:
                conn.execute("ALTER TABLE sessions ADD COLUMN error_message TEXT")
            except sqlite3.OperationalError:
                pass  # 列已存在
            conn.execute(
                "UPDATE sessions SET error_message = ?, updated_at = ? WHERE session_id = ?",
                (error_message[:1000], _now(), session_id),
            )
            conn.commit()

    @classmethod
    def get_error(cls, session_id: str) -> str:
        """获取 session 的错误信息。"""
        _ensure_db()
        conn = sqlite3.connect(str(_DB_PATH))
        row = conn.execute(
            "SELECT error_message FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        conn.close()
        return row[0] if row and row[0] else ""

    @classmethod
    def get_all_sessions(cls) -> list[dict]:
        """获取所有 session 列表。"""
        _ensure_db()
        conn = sqlite3.connect(str(_DB_PATH))
        rows = conn.execute(
            "SELECT session_id, project_name, status, state, current_version, updated_at, total_cost_usd "
            "FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
        conn.close()

        return [
            {
                "session_id": r[0],
                "project_name": r[1],
                "status": r[2],
                "state": r[3],
                "current_version": r[4],
                "updated_at": r[5],
                "total_cost_usd": r[6],
            }
            for r in rows
        ]

    @classmethod
    def delete_project(cls, project_name: str) -> bool:
        """删除项目（标记为 deleted，实际保留数据）。"""
        _ensure_db()
        with _write_conn() as conn:
            cursor = conn.execute(
                "UPDATE sessions SET status = 'deleted', updated_at = ? WHERE project_name = ?",
                (_now(), project_name),
            )
            affected = cursor.rowcount
            conn.commit()
        return affected > 0

    # ── 版本管理 ──

    @classmethod
    def create_version(cls, session_id: str, version: int, summary: str = ""):
        """记录版本。"""
        _ensure_db()
        with _write_conn() as conn:
            conn.execute(
                "INSERT INTO versions (session_id, version, summary, created_at) VALUES (?, ?, ?, ?)",
                (session_id, version, summary, _now()),
            )
            conn.execute(
                "UPDATE sessions SET current_version = ?, updated_at = ? WHERE session_id = ?",
                (version, _now(), session_id),
            )
            conn.commit()

    @classmethod
    def get_versions(cls, session_id: str) -> list[dict]:
        """获取 session 的版本列表。"""
        _ensure_db()
        conn = sqlite3.connect(str(_DB_PATH))
        rows = conn.execute(
            "SELECT version, status, summary, created_at FROM versions WHERE session_id = ? ORDER BY version DESC",
            (session_id,),
        ).fetchall()
        conn.close()
        return [
            {"version": r[0], "status": r[1], "summary": r[2], "created_at": r[3]}
            for r in rows
        ]

    @classmethod
    def rollback_version(cls, session_id: str, target_version: int) -> bool:
        """标记版本为 rolled_back，返回 True。实际文件回滚由 VersionManager 处理。"""
        _ensure_db()
        with _write_conn() as conn:
            # 把所有 >= target_version 的 active 版本标记为 rolled_back
            conn.execute(
                "UPDATE versions SET status = 'rolled_back' WHERE session_id = ? AND version >= ? AND status = 'active'",
                (session_id, target_version),
            )
            # 把 target_version - 1 标记回 active
            if target_version > 1:
                conn.execute(
                    "UPDATE versions SET status = 'active' WHERE session_id = ? AND version = ?",
                    (session_id, target_version - 1),
                )
            conn.execute(
                "UPDATE sessions SET current_version = MAX(1, ? - 1), updated_at = ? WHERE session_id = ?",
                (target_version, _now(), session_id),
            )
            conn.commit()
        return True

    # ── 成本跟踪 ──

    @classmethod
    def log_cost(
        cls,
        session_id: str,
        phase: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        version: Optional[int] = None,
    ):
        """记录一次成本消耗。"""
        _ensure_db()
        with _write_conn() as conn:
            conn.execute(
                "INSERT INTO cost_log (session_id, version, phase, tokens_in, tokens_out, cost_usd, logged_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, version, phase, tokens_in, tokens_out, cost_usd, _now()),
            )
            # 更新 session 总成本
            total = conn.execute(
                "SELECT SUM(cost_usd) FROM cost_log WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0] or 0.0
            conn.execute(
                "UPDATE sessions SET total_cost_usd = ?, updated_at = ? WHERE session_id = ?",
                (total, _now(), session_id),
            )
            conn.commit()
