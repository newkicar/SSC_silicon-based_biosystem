"""
上下文池（Context Pool）—— 按事务ID组织的全景案件视图

核心功能：
- 按事务ID（case_id）组织所有相关信息
- 事务摘要自动生成并持续更新
- 关联信息自动缝合（员工档案+政策+历史工单）
- 处理时间线
- 决策记录
"""
import json
import sqlite3
from datetime import datetime
from src.data.task_queue import get_connection


def init_context_pool():
    """初始化上下文池表"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS context_pool (
            case_id       VARCHAR(64) PRIMARY KEY,
            summary       TEXT,
            related_info  TEXT,
            timeline      TEXT,
            decisions     TEXT,
            visibility    TEXT,
            status        TEXT DEFAULT 'open',
            created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def create_case(
    case_id: str,
    summary: dict = None,
    related_info: dict = None,
    visibility: dict = None,
) -> str:
    """创建新事务"""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        """INSERT OR REPLACE INTO context_pool
           (case_id, summary, related_info, timeline, decisions, visibility, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            case_id,
            json.dumps(summary, ensure_ascii=False) if summary else None,
            json.dumps(related_info, ensure_ascii=False) if related_info else None,
            json.dumps([], ensure_ascii=False),
            json.dumps([], ensure_ascii=False),
            json.dumps(visibility, ensure_ascii=False) if visibility else None,
            now, now,
        ),
    )
    conn.commit()
    conn.close()
    return case_id


def update_case_summary(case_id: str, summary: dict):
    """更新事务摘要"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE context_pool SET summary = ?, updated_at = ?
           WHERE case_id = ?""",
        (json.dumps(summary, ensure_ascii=False), datetime.now().isoformat(), case_id),
    )
    conn.commit()
    conn.close()


def append_timeline(case_id: str, event: dict):
    """向时间线追加事件"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT timeline FROM context_pool WHERE case_id = ?", (case_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return
    timeline = json.loads(row["timeline"]) if row["timeline"] else []
    event["timestamp"] = datetime.now().isoformat()
    timeline.append(event)
    cursor.execute(
        """UPDATE context_pool SET timeline = ?, updated_at = ?
           WHERE case_id = ?""",
        (json.dumps(timeline, ensure_ascii=False), datetime.now().isoformat(), case_id),
    )
    conn.commit()
    conn.close()


def append_decision(case_id: str, decision: dict):
    """向决策记录追加"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT decisions FROM context_pool WHERE case_id = ?", (case_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return
    decisions = json.loads(row["decisions"]) if row["decisions"] else []
    decision["timestamp"] = datetime.now().isoformat()
    decisions.append(decision)
    cursor.execute(
        """UPDATE context_pool SET decisions = ?, updated_at = ?
           WHERE case_id = ?""",
        (json.dumps(decisions, ensure_ascii=False), datetime.now().isoformat(), case_id),
    )
    conn.commit()
    conn.close()


def get_case(case_id: str) -> dict | None:
    """获取完整事务上下文"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM context_pool WHERE case_id = ?", (case_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    case = dict(row)
    for field in ["summary", "related_info", "timeline", "decisions", "visibility"]:
        if case.get(field):
            case[field] = json.loads(case[field])
    return case


def close_case(case_id: str):
    """关闭事务"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE context_pool SET status = 'closed', updated_at = ? WHERE case_id = ?",
        (datetime.now().isoformat(), case_id),
    )
    conn.commit()
    conn.close()


def list_open_cases(role: str = None) -> list[dict]:
    """列出所有未关闭的事务"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT case_id, summary, status, created_at, updated_at FROM context_pool WHERE status = 'open' ORDER BY updated_at DESC"
    )
    rows = [dict(row) for row in cursor.fetchall()]
    for row in rows:
        if row.get("summary"):
            row["summary"] = json.loads(row["summary"])
    conn.close()
    return rows