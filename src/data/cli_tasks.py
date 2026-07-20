"""
CLI任务队列 —— 大脑与角色CLI Agent之间的通信桥梁

任务生命周期：
  CREATED → DISPATCHED → CLAIMED → EXECUTING → COMPLETED / FAILED / ESCALATED
  - CREATED: 大脑创建任务
  - DISPATCHED: 已分派到目标角色队列
  - CLAIMED: 角色CLI Agent已认领
  - EXECUTING: 正在执行（AI自动执行或人类手动处理）
  - COMPLETED: 任务完成
  - FAILED: 执行失败
  - ESCALATED: 升级人工
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = str(Path(__file__).resolve().parent.parent.parent / "data" / "auth.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_cli_task_table():
    """初始化CLI任务表"""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cli_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE NOT NULL,
            source TEXT DEFAULT 'brain',
            event_type TEXT DEFAULT '',
            target_role TEXT NOT NULL,
            target_username TEXT DEFAULT '',
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            context TEXT DEFAULT '{}',
            skill_name TEXT DEFAULT '',
            skill_params TEXT DEFAULT '{}',
            priority TEXT DEFAULT 'normal',
            status TEXT DEFAULT 'dispatched',
            result TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            claimed_at TEXT DEFAULT NULL,
            completed_at TEXT DEFAULT NULL,
            linked_ticket_id TEXT DEFAULT NULL,
            linked_notification_id TEXT DEFAULT NULL
        )
    """)
    conn.commit()
    conn.close()


def create_cli_task(task_data: dict) -> dict:
    """
    创建一个CLI任务（由大脑/下行脊髓调用）
    
    task_data = {
        "task_id": "CT-20260604-xxx",
        "source": "brain",
        "event_type": "arbitration_inquiry",  # 可选
        "target_role": "员工关系专员",
        "target_username": "",  # 可选，指定具体用户
        "title": "为XXX开具在职证明",
        "description": "员工XXX申请开具在职证明，用途：银行贷款",
        "context": {"employee_name": "XXX", "department": "..."},
        "skill_name": "employment_certificate",  # 可选
        "skill_params": {"employee_name": "XXX", "purpose": "银行贷款"},  # 可选
        "priority": "normal",
        "linked_ticket_id": "123",  # 可选
    }
    """
    conn = _get_conn()
    cursor = conn.cursor()
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute("""
        INSERT INTO cli_tasks (task_id, source, event_type, target_role, target_username,
                              title, description, context, skill_name, skill_params,
                              priority, status, created_at, linked_ticket_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'dispatched', ?, ?)
    """, (
        task_data.get("task_id", ""),
        task_data.get("source", "brain"),
        task_data.get("event_type", ""),
        task_data.get("target_role", ""),
        task_data.get("target_username", ""),
        task_data.get("title", ""),
        task_data.get("description", ""),
        json.dumps(task_data.get("context", {}), ensure_ascii=False),
        task_data.get("skill_name", ""),
        json.dumps(task_data.get("skill_params", {}), ensure_ascii=False),
        task_data.get("priority", "normal"),
        now,
        task_data.get("linked_ticket_id"),
    ))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "task_id": task_data.get("task_id"), "created_at": now}


def get_pending_tasks_for_role(role_name: str, username: str = None) -> list:
    """获取某个角色的待处理任务"""
    conn = _get_conn()
    cursor = conn.cursor()
    
    if username:
        cursor.execute("""
            SELECT * FROM cli_tasks 
            WHERE (target_role = ? OR target_username = ?) 
            AND status IN ('dispatched', 'claimed')
            ORDER BY 
                CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 ELSE 3 END,
                created_at ASC
        """, (role_name, username))
    else:
        cursor.execute("""
            SELECT * FROM cli_tasks 
            WHERE target_role = ? AND status IN ('dispatched', 'claimed')
            ORDER BY 
                CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 ELSE 3 END,
                created_at ASC
        """, (role_name,))
    
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        task = dict(row)
        task['context'] = json.loads(task.get('context', '{}'))
        task['skill_params'] = json.loads(task.get('skill_params', '{}'))
        result.append(task)
    
    return result


def claim_cli_task(task_id: str, username: str) -> dict:
    """认领任务"""
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute("""
        UPDATE cli_tasks SET status = 'claimed', claimed_at = ?, target_username = ?
        WHERE task_id = ? AND status = 'dispatched'
    """, (now, username, task_id))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return {"success": affected > 0, "claimed_at": now}


def update_cli_task_status(task_id: str, status: str, result: str = "") -> dict:
    """更新任务状态（完成后自动关闭关联工单）"""
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 先获取任务信息（用于关联工单处理）
    cursor.execute("SELECT linked_ticket_id FROM cli_tasks WHERE task_id = ?", (task_id,))
    task_row = cursor.fetchone()
    
    updates = ["status = ?"]
    params = [status]
    
    if result:
        updates.append("result = ?")
        params.append(result)
    
    if status == 'completed':
        updates.append("completed_at = ?")
        params.append(now)
    
    params.append(task_id)
    cursor.execute(f"UPDATE cli_tasks SET {', '.join(updates)} WHERE task_id = ?", params)
    affected = cursor.rowcount
    
    # CLI任务完成后，自动关闭关联的工单
    if status == 'completed' and task_row and task_row['linked_ticket_id']:
        linked_ticket = task_row['linked_ticket_id']
        cursor.execute("""
            UPDATE tickets SET status = 'done', resolved_at = ?, updated_at = ? 
            WHERE (ticket_no = ? OR id = ?) AND status NOT IN ('done', 'cancelled')
        """, (now, now, linked_ticket, linked_ticket))
        if cursor.rowcount > 0:
            print(f"[CLI任务完成] 已自动关闭关联工单: {linked_ticket}")
    
    conn.commit()
    conn.close()
    
    return {"success": affected > 0, "updated_at": now}


def get_task_by_id(task_id: str) -> dict:
    """获取单个任务详情"""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cli_tasks WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    task = dict(row)
    task['context'] = json.loads(task.get('context', '{}'))
    task['skill_params'] = json.loads(task.get('skill_params', '{}'))
    return task