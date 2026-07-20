"""
统一数据层 - 数据库队列表（Database Queue）

核心通信机制：
- 写入即释放：发出方INSERT任务后立即返回
- 轮询即认领：接收方SELECT + UPDATE（乐观锁）认领任务
- 状态可追溯：完整状态流、时间戳、父子关系
- 异常自升级：超时未认领或执行失败，按策略自动处理

包含两张任务表：
- task_bs：大脑↔脊髓通信
- task_st：脊髓↔终端通信
- event_bus：全局事件总线
"""
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

from src.config.settings import DB_PATH, DATA_DIR


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_task_tables():
    """初始化任务队列表和事件总线表"""
    conn = get_connection()
    cursor = conn.cursor()

    # ---- 大脑↔脊髓任务表 ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_bs (
            task_id       VARCHAR(64) PRIMARY KEY,
            direction     TEXT NOT NULL CHECK(direction IN ('DOWN', 'UP')),
            task_type     TEXT NOT NULL DEFAULT 'decision',
            status        TEXT NOT NULL DEFAULT 'ISSUED'
                          CHECK(status IN ('ISSUED','ACCEPTED','IN_PROGRESS',
                                'COMPLETED','FAILED','ESCALATED','CANCELLED')),
            priority      TEXT NOT NULL DEFAULT 'normal'
                          CHECK(priority IN ('low','normal','high','urgent')),
            from_layer    TEXT NOT NULL,
            accepted_by   TEXT,
            issued_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            accepted_at   DATETIME,
            completed_at  DATETIME,
            timeout_at    DATETIME,
            retry_count   INTEGER DEFAULT 0,
            payload       TEXT,
            result        TEXT,
            context_ref   VARCHAR(64)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_task_bs_status
        ON task_bs(status, direction)
    """)

    # ---- 脊髓↔终端任务表 ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_st (
            task_id              VARCHAR(64) PRIMARY KEY,
            parent_task_id       VARCHAR(64),
            status               TEXT NOT NULL DEFAULT 'ISSUED'
                                 CHECK(status IN ('ISSUED','ACCEPTED','IN_PROGRESS',
                                       'COMPLETED','FAILED','RETRYING',
                                       'FAILED_FINAL','CANCELLED')),
            target_terminal_type TEXT NOT NULL,
            accepted_by          TEXT,
            issued_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            accepted_at          DATETIME,
            completed_at         DATETIME,
            timeout_at           DATETIME,
            retry_count          INTEGER DEFAULT 0,
            max_retries          INTEGER DEFAULT 3,
            payload              TEXT,
            result               TEXT
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_task_st_status
        ON task_st(status, target_terminal_type)
    """)

    # ---- 事件总线表 ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_bus (
            event_id         VARCHAR(64) PRIMARY KEY,
            event_type       TEXT NOT NULL,
            source           TEXT NOT NULL,
            timestamp        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            payload          TEXT,
            parent_event_id  VARCHAR(64),
            consumed         INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_event_bus_type
        ON event_bus(event_type, consumed)
    """)

    conn.commit()
    conn.close()


# ==================== task_bs 操作 ====================

def insert_task_bs(
    task_id: str,
    direction: str,
    task_type: str = "decision",
    priority: str = "normal",
    from_layer: str = "brain",
    payload: dict = None,
    context_ref: str = None,
    timeout_seconds: int = 300,
) -> str:
    """
    写入大脑↔脊髓任务（写入即释放）
    返回 task_id
    """
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now()
    timeout_at = now + timedelta(seconds=timeout_seconds)

    cursor.execute(
        """INSERT INTO task_bs
           (task_id, direction, task_type, status, priority, from_layer,
            payload, context_ref, issued_at, timeout_at)
           VALUES (?, ?, ?, 'ISSUED', ?, ?, ?, ?, ?, ?)""",
        (task_id, direction, task_type, priority, from_layer,
         json.dumps(payload, ensure_ascii=False) if payload else None,
         context_ref, now.isoformat(), timeout_at.isoformat()),
    )
    conn.commit()
    conn.close()
    return task_id


def claim_task_bs(direction: str, claimed_by: str = "spine") -> dict | None:
    """
    认领一个待处理的脑脊髓任务（乐观锁）
    direction: 'DOWN'=大脑下发(脊髓领取), 'UP'=脊髓上报(大脑领取)
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 查找最早的待认领任务
    cursor.execute(
        """SELECT * FROM task_bs
           WHERE direction = ? AND status = 'ISSUED'
           ORDER BY
             CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1
                           WHEN 'normal' THEN 2 ELSE 3 END,
             issued_at ASC
           LIMIT 1""",
        (direction,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    task = dict(row)
    now = datetime.now().isoformat()

    # 乐观锁认领
    cursor.execute(
        """UPDATE task_bs
           SET status = 'ACCEPTED', accepted_by = ?, accepted_at = ?
           WHERE task_id = ? AND status = 'ISSUED'""",
        (claimed_by, now, task["task_id"]),
    )

    if cursor.rowcount == 0:
        # 被其他实例抢先认领
        conn.close()
        return None

    conn.commit()
    conn.close()

    task["status"] = "ACCEPTED"
    task["accepted_by"] = claimed_by
    task["accepted_at"] = now
    if task.get("payload"):
        task["payload"] = json.loads(task["payload"])
    return task


def update_task_bs_status(
    task_id: str,
    status: str,
    result: dict = None,
) -> None:
    """更新大脑↔脊髓任务状态"""
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()
    if status in ("COMPLETED", "FAILED", "ESCALATED"):
        cursor.execute(
            """UPDATE task_bs
               SET status = ?, result = ?, completed_at = ?
               WHERE task_id = ?""",
            (status,
             json.dumps(result, ensure_ascii=False) if result else None,
             now, task_id),
        )
    else:
        cursor.execute(
            "UPDATE task_bs SET status = ? WHERE task_id = ?",
            (status, task_id),
        )

    conn.commit()
    conn.close()


# ==================== task_st 操作 ====================

def insert_task_st(
    task_id: str,
    parent_task_id: str,
    target_terminal_type: str,
    payload: dict,
    timeout_seconds: int = 300,
    max_retries: int = 3,
) -> str:
    """写入脊髓↔终端任务（写入即释放）"""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now()
    timeout_at = now + timedelta(seconds=timeout_seconds)

    cursor.execute(
        """INSERT INTO task_st
           (task_id, parent_task_id, status, target_terminal_type,
            payload, issued_at, timeout_at, max_retries)
           VALUES (?, ?, 'ISSUED', ?, ?, ?, ?, ?)""",
        (task_id, parent_task_id, target_terminal_type,
         json.dumps(payload, ensure_ascii=False),
         now.isoformat(), timeout_at.isoformat(), max_retries),
    )
    conn.commit()
    conn.close()
    return task_id


def claim_task_st(terminal_type: str, claimed_by: str = "terminal") -> dict | None:
    """
    认领一个待处理的脊髓↔终端任务（乐观锁）
    terminal_type: 终端类型，如 'rpa', 'api', 'wecom', 'human'
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """SELECT * FROM task_st
           WHERE target_terminal_type = ? AND status = 'ISSUED'
           ORDER BY issued_at ASC LIMIT 1""",
        (terminal_type,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    task = dict(row)
    now = datetime.now().isoformat()

    cursor.execute(
        """UPDATE task_st
           SET status = 'ACCEPTED', accepted_by = ?, accepted_at = ?
           WHERE task_id = ? AND status = 'ISSUED'""",
        (claimed_by, now, task["task_id"]),
    )

    if cursor.rowcount == 0:
        conn.close()
        return None

    conn.commit()
    conn.close()

    task["status"] = "ACCEPTED"
    task["accepted_by"] = claimed_by
    task["accepted_at"] = now
    if task.get("payload"):
        task["payload"] = json.loads(task["payload"])
    return task


def update_task_st_status(
    task_id: str,
    status: str,
    result: dict = None,
) -> None:
    """更新脊髓↔终端任务状态"""
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()
    if status in ("COMPLETED", "FAILED", "FAILED_FINAL", "CANCELLED"):
        cursor.execute(
            """UPDATE task_st
               SET status = ?, result = ?, completed_at = ?
               WHERE task_id = ?""",
            (status,
             json.dumps(result, ensure_ascii=False) if result else None,
             now, task_id),
        )
    else:
        cursor.execute(
            "UPDATE task_st SET status = ? WHERE task_id = ?",
            (status, task_id),
        )

    conn.commit()
    conn.close()


def get_child_tasks(parent_task_id: str) -> list[dict]:
    """获取某个大脑指令下的所有子任务"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM task_st WHERE parent_task_id = ? ORDER BY issued_at",
        (parent_task_id,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    for row in rows:
        if row.get("payload"):
            row["payload"] = json.loads(row["payload"])
        if row.get("result"):
            row["result"] = json.loads(row["result"])
    conn.close()
    return rows


def are_all_child_tasks_completed(parent_task_id: str) -> bool:
    """检查某个大脑指令下的所有子任务是否都已完成"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT COUNT(*) as total,
                  SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed
           FROM task_st WHERE parent_task_id = ?""",
        (parent_task_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return True
    return row["total"] == row["completed"]


# ==================== event_bus 操作 ====================

def insert_event(
    event_id: str,
    event_type: str,
    source: str,
    payload: dict = None,
    parent_event_id: str = None,
) -> str:
    """发布事件到事件总线"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT OR IGNORE INTO event_bus
           (event_id, event_type, source, payload, parent_event_id)
           VALUES (?, ?, ?, ?, ?)""",
        (event_id, event_type, source,
         json.dumps(payload, ensure_ascii=False) if payload else None,
         parent_event_id),
    )
    conn.commit()
    conn.close()
    return event_id


def get_unconsumed_events(event_type: str = None) -> list[dict]:
    """获取未消费的事件"""
    conn = get_connection()
    cursor = conn.cursor()

    if event_type:
        cursor.execute(
            """SELECT * FROM event_bus
               WHERE event_type = ? AND consumed = 0
               ORDER BY timestamp ASC""",
            (event_type,),
        )
    else:
        cursor.execute(
            """SELECT * FROM event_bus
               WHERE consumed = 0
               ORDER BY timestamp ASC""",
        )

    rows = [dict(row) for row in cursor.fetchall()]
    for row in rows:
        if row.get("payload"):
            row["payload"] = json.loads(row["payload"])
    conn.close()
    return rows


def mark_events_consumed(event_ids: list[str]) -> None:
    """标记事件为已消费"""
    if not event_ids:
        return
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(event_ids))
    cursor.execute(
        f"UPDATE event_bus SET consumed = 1 WHERE event_id IN ({placeholders})",
        event_ids,
    )
    conn.commit()
    conn.close()