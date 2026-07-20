"""
第二层记忆：Database记忆（中期/对话记录）
存储在SQLite中，包含is_memorized标记，每天凌晨2:00清理无价值记录。
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path

from src.config.settings import DB_PATH, DATA_DIR


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表结构（含统一数据层的任务队列表+上下文池）"""
    # 先初始化统一数据层的表
    from src.data.task_queue import init_task_tables
    from src.data.context_pool import init_context_pool
    init_task_tables()
    init_context_pool()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            timestamp   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            role        TEXT NOT NULL,          -- 'user' / 'assistant' / 'system'
            content     TEXT NOT NULL,
            source      TEXT DEFAULT 'unknown', -- 'employee_chat' / 'internal' / 'brain_initiated'
            employee_id TEXT,
            task_id     TEXT,
            importance_score REAL DEFAULT 0.5,  -- 0.0 ~ 1.0
            is_memorized    BOOLEAN DEFAULT 0,  -- 是否已提炼到MD记忆
            created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversations_session 
        ON conversations(session_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversations_memorized 
        ON conversations(is_memorized)
    """)
    conn.commit()
    conn.close()


def save_conversation(
    session_id: str,
    role: str,
    content: str,
    source: str = "unknown",
    employee_id: str = None,
    task_id: str = None,
    importance_score: float = 0.5,
):
    """保存一条对话记录"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO conversations 
           (session_id, role, content, source, employee_id, task_id, importance_score)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, role, content, source, employee_id, task_id, importance_score),
    )
    conn.commit()
    conn.close()


def get_unmemorized_records() -> list[dict]:
    """获取尚未提炼到MD记忆的记录"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM conversations WHERE is_memorized = 0 ORDER BY timestamp"
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def mark_as_memorized(record_ids: list[int]):
    """将指定记录标记为已提炼"""
    if not record_ids:
        return
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(record_ids))
    cursor.execute(
        f"UPDATE conversations SET is_memorized = 1 WHERE id IN ({placeholders})",
        record_ids,
    )
    conn.commit()
    conn.close()


def cleanup_low_value_records(importance_threshold: float = 0.3):
    """
    每日清理：删除低价值记录。
    保留条件（满足任一即保留）：importance_score >= 0.5
    删除条件（满足全部即删除）：importance_score < threshold
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM conversations WHERE importance_score < ? AND is_memorized = 1",
        (importance_threshold,),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted