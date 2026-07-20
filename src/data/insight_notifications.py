"""洞察通知查重数据模型

负责洞察通知记录的 CRUD 操作。
表结构：
- id: 自增主键
- target_user: 接收人工号
- title: 洞察标题
- content: 洞察内容
- summary: AI总结（20字以内）
- insight_level: 洞察级别
- insight_org: 组织名称
- insight_type: 洞察类型
- company: 公司名称
- created_at: 创建时间
- expires_at: 过期时间（15天后）
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent.parent.parent / "data" / "auth.db"


def init_insight_notifications_table(conn):
    """初始化洞察通知记录表"""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS insight_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_user TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            summary TEXT NOT NULL,
            insight_level TEXT,
            insight_org TEXT,
            insight_type TEXT,
            company TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            UNIQUE(target_user, title, content, created_at)
        )
    """)
    conn.commit()


def save_insight_notification(
    conn,
    target_user,
    title,
    content,
    summary,
    insight_level="",
    insight_org="",
    insight_type="",
    company="",
):
    """保存洞察通知记录，返回记录ID"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    expires = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d %H:%M:%S")

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO insight_notifications
            (target_user, title, content, summary, insight_level, insight_org,
             insight_type, company, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            target_user,
            title,
            content,
            summary,
            insight_level,
            insight_org,
            insight_type,
            company,
            now,
            expires,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_recent_notifications(conn, target_user):
    """获取指定用户最近15天的洞察通知记录

    注意：conn 必须是普通连接，函数内部会临时设置 row_factory
    """
    cutoff = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d %H:%M:%S")

    # 临时设置 row_factory 以支持字典访问
    old_factory = conn.row_factory
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, content, summary, insight_level, insight_org,
                   insight_type, company, created_at
            FROM insight_notifications
            WHERE target_user = ? AND expires_at > ?
            ORDER BY created_at DESC
        """,
            (target_user, cutoff),
        )
        rows = cursor.fetchall()
        result = []
        for row in rows:
            try:
                result.append(
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "content": row["content"],
                        "summary": row["summary"],
                        "insight_level": row["insight_level"],
                        "insight_org": row["insight_org"],
                        "insight_type": row["insight_type"],
                        "company": row["company"],
                        "created_at": row["created_at"],
                    }
                )
            except Exception as e:
                print(f"[查重数据] 转换记录失败: {e}")
                continue
        return result
    finally:
        conn.row_factory = old_factory


def cleanup_expired(conn):
    """清理过期记录，返回删除数量"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor = conn.cursor()
    cursor.execute("DELETE FROM insight_notifications WHERE expires_at <= ?", (now,))
    deleted = cursor.rowcount
    conn.commit()
    return deleted
