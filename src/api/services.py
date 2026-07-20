"""
工单系统 + 通知推送 + 个人中心 后端服务

数据库表：
- tickets: 工单
- notifications: 通知
- notification_reads: 通知已读记录（按用户维度）
"""

import sqlite3
import os
from datetime import datetime
from pathlib import Path

DB_PATH = str(Path(__file__).resolve().parent.parent.parent / "data" / "auth.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


_TARGET_USER_ALIASES = {"all_ssc", "all", "all_users", "*"}


def _normalize_target_user(value: str) -> str:
    """将 target_user 别名统一为 'all'，确保通知可见性逻辑一致。"""
    if not value:
        return "all"
    return "all" if value.strip().lower() in _TARGET_USER_ALIASES else value


def init_ticket_tables():
    """初始化工单和通知表"""
    conn = _get_conn()
    cursor = conn.cursor()

    # 工单表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_no TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            category TEXT DEFAULT '一般',
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            priority TEXT DEFAULT 'normal',
            submitter TEXT NOT NULL,
            assignee TEXT DEFAULT '',
            department TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT DEFAULT NULL
        )
    """)

    # 通知表（不再使用全局 is_read 字段，改用 notification_reads 关联表）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            type TEXT DEFAULT 'info',
            icon TEXT DEFAULT '🔔',
            target_user TEXT DEFAULT 'all',
            created_at TEXT NOT NULL
        )
    """)

    # 通知已读记录表（每个用户独立标记已读，替代全局 is_read 字段）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_reads (
            notification_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            read_at TEXT NOT NULL,
            PRIMARY KEY (notification_id, user_id),
            FOREIGN KEY (notification_id) REFERENCES notifications(id)
        )
    """)

    # 工单转办记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_no TEXT NOT NULL,
            from_user TEXT NOT NULL,
            to_user TEXT NOT NULL,
            reason TEXT DEFAULT '',
            transferred_at TEXT NOT NULL,
            FOREIGN KEY (ticket_no) REFERENCES tickets(ticket_no)
        )
    """)

    conn.commit()
    conn.close()


# ==================== 工单服务 ====================


def get_tickets(username=None, role=None, status=None, view=None):
    """
    获取工单列表
    view=None/submitter: 我提出的（默认）
    view=receiver: 交给我的（按角色匹配 assignee 字段）
    """
    conn = _get_conn()
    cursor = conn.cursor()

    if view == "receiver":
        # 交给我的工单：assignee 字段包含当前用户的角色或姓名
        # SSC操作层可看到所有"交给我的"工单，管理层只能看到分配给自己的
        is_ssc = role and role in (
            "HR_SSC经理",
            "HRIS工程师",
            "HR_SSC学科经理",
            "高级HRIS工程师",
            "招聘主管",
            "招聘专员",
            "员工关系专员",
            "员工关系主管",
            "薪酬主管",
            "薪酬专员",
            "考勤专员",
        )
        if is_ssc:
            # SSC操作层：看到 assignee 包含自己角色的工单
            cursor.execute(
                "SELECT display_name FROM users WHERE username = ?", (username,)
            )
            user_row = cursor.fetchone()
            my_name = user_row["display_name"] if user_row else ""

            query = "SELECT * FROM tickets WHERE (assignee LIKE ? OR assignee LIKE ? OR assignee LIKE ?)"
            params = [f"%{role}%", f"%{my_name}%", f"%{username}%"]
        else:
            # 管理层：只看到 assignee 包含自己姓名的工单
            cursor.execute(
                "SELECT display_name FROM users WHERE username = ?", (username,)
            )
            user_row = cursor.fetchone()
            my_name = user_row["display_name"] if user_row else ""
            query = "SELECT * FROM tickets WHERE (assignee LIKE ? OR assignee LIKE ?)"
            params = [f"%{my_name}%", f"%{username}%"]

        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
    else:
        # 我提出的工单（默认）
        query = "SELECT * FROM tickets WHERE 1=1"
        params = []

        # 非管理员只能看自己提交的工单
        if role and role not in ("HR_SSC经理", "HRIS工程师"):
            query += " AND submitter = ?"
            params.append(username)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)

    rows = cursor.fetchall()
    conn.close()

    # 自动归档：done/cancelled 超过3天的工单从默认列表中隐藏
    from datetime import timedelta

    archive_threshold = (datetime.now() - timedelta(days=3)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    result = []
    for r in rows:
        row = dict(r)
        # 如果是已完成/已撤销的工单，且 resolved_at 超过3天，则跳过（不显示）
        if row.get("status") in ("done", "cancelled") and row.get("resolved_at"):
            if row["resolved_at"] < archive_threshold:
                continue
        result.append(row)

    return result


def get_ticket_detail(ticket_no, username, role):
    """获取单个工单详情（提交人或接收人可查看）"""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tickets WHERE ticket_no = ?", (ticket_no,))
    row = cursor.fetchone()

    # 获取当前用户的 display_name（用于姓名匹配）
    cursor.execute("SELECT display_name FROM users WHERE username = ?", (username,))
    user_row = cursor.fetchone()
    display_name = user_row["display_name"] if user_row else ""
    conn.close()

    if not row:
        return None
    ticket = dict(row)
    assignee_str = ticket.get("assignee") or ""

    # 权限检查：提交人、接收人（用户名/姓名/角色名匹配）、管理员可查看
    is_submitter = (
        ticket.get("submitter") == username or ticket.get("submitter") == display_name
    )
    is_assignee = (
        username in assignee_str or display_name in assignee_str or role in assignee_str
    )
    is_admin = role in ("admin", "HR_SSC经理", "HRIS工程师", "HR_SSC学科经理")
    if not (is_submitter or is_assignee or is_admin):
        return {"error": "无权查看此工单"}
    return ticket


def create_ticket(data, username, display_name, skip_dispatch=False):
    """创建工单"""
    conn = _get_conn()
    cursor = conn.cursor()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 生成工单号
    cursor.execute("SELECT COUNT(*) FROM tickets")
    count = cursor.fetchone()[0]
    ticket_no = f"TK{datetime.now().strftime('%Y%m%d')}{count + 1:03d}"

    cursor.execute(
        """
        INSERT INTO tickets (ticket_no, title, category, description, status, priority, 
                            submitter, assignee, department, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)
    """,
        (
            ticket_no,
            data.get("title", ""),
            data.get("category", "一般"),
            data.get("description", ""),
            data.get("priority", "normal"),
            username,
            data.get("assignee", ""),
            data.get("department", ""),
            now,
            now,
        ),
    )

    conn.commit()
    ticket_id = cursor.lastrowid
    conn.close()

    result = {"id": ticket_id, "ticket_no": ticket_no, "created_at": now}

    # skip_dispatch=True 时跳过大脑分析（由分派器创建的子工单，避免无限循环）
    if skip_dispatch:
        return result

    # 在后台线程中通知大脑分析工单并分派任务（不阻塞API响应）
    import threading

    try:
        dispatch_thread = threading.Thread(
            target=_dispatch_ticket_via_brain,
            kwargs={
                "ticket_no": ticket_no,
                "title": data.get("title", ""),
                "category": data.get("category", "一般"),
                "description": data.get("description", ""),
                "priority": data.get("priority", "normal"),
                "submitter": username,
                "submitter_name": display_name,
            },
            daemon=True,
        )
        dispatch_thread.start()
        print(f"[工单分派] 大脑分析已在后台启动（工单: {ticket_no}）")
    except Exception as e:
        print(f"[工单分派] 启动后台分析失败（不影响工单创建）: {e}")

    return result


def _dispatch_ticket_via_brain(
    ticket_no: str,
    title: str,
    category: str,
    description: str,
    priority: str,
    submitter: str,
    submitter_name: str,
):
    """
    将新工单送给大脑分析，由大脑决定分派给哪个角色处理。
    大脑的分析和分派决策会保存到 conversations 表，确保数据可追溯。
    分派完成后，自动更新工单的 assignee 字段（处理人）。
    """
    from src.main import process_message

    # 构造工单分析消息，让大脑理解工单内容并输出分派指令
    ticket_msg = (
        f"[渠道:cli][系统工单通知] 新工单已创建，需要分析并分派处理：\n"
        f"- 工单号: {ticket_no}\n"
        f"- 标题: {title}\n"
        f"- 分类: {category}\n"
        f"- 内容描述: {description}\n"
        f"- 优先级: {priority}\n"
        f"- 提交人: {submitter_name}（{submitter}）\n\n"
        f"请分析此工单内容，判断应该分派给哪个角色处理，并输出 dispatch_actions 指令。\n"
        f"如果工单内容简单明确（如薪酬→薪酬专员，社保→员工关系专员），直接分派即可。\n"
        f"如果工单内容复杂，需要拆分为多个子任务，请一并处理。"
    )

    session_id = f"ticket-dispatch-{ticket_no}"

    # 记录时间戳，用于追踪大脑创建的 CLI 任务
    before_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 调用大脑处理（会经过完整的上行脊髓→中枢神经节→秘书→大脑→分派 流程）
    response = process_message(ticket_msg, session_id)

    # ---- 分派完成后，更新工单的 assignee（处理人） ----
    try:
        conn = _get_conn()
        cursor = conn.cursor()

        # 查找大脑分派后新创建的 CLI 任务（获取目标角色）
        cursor.execute(
            """
            SELECT DISTINCT target_role FROM cli_tasks 
            WHERE created_at >= ? ORDER BY id ASC
        """,
            (before_time,),
        )
        new_tasks = cursor.fetchall()

        if new_tasks:
            target_roles = [t["target_role"] for t in new_tasks]

            # 查找每个目标角色对应的员工姓名（支持模糊匹配）
            assignee_parts = []
            for tr in target_roles:
                # 先精确匹配
                cursor.execute("SELECT display_name FROM users WHERE role = ?", (tr,))
                users_with_role = cursor.fetchall()

                if not users_with_role:
                    # 模糊匹配：用角色名的前2个字搜索包含该关键词的角色
                    prefix = tr[:2]
                    cursor.execute(
                        "SELECT display_name, role FROM users WHERE role LIKE ?",
                        (f"%{prefix}%",),
                    )
                    fuzzy_users = cursor.fetchall()
                    if fuzzy_users:
                        users_with_role = fuzzy_users
                        actual_roles = set(u["role"] for u in fuzzy_users)
                        actual_role_str = "/".join(actual_roles)
                        names = ", ".join([u["display_name"] for u in fuzzy_users])
                        assignee_parts.append(f"{names}（{actual_role_str}）")
                        print(
                            f"[工单分派] 角色 '{tr}' 无精确匹配，模糊匹配到: {names}（{actual_role_str}）"
                        )
                        continue

                if users_with_role:
                    names = ", ".join([u["display_name"] for u in users_with_role])
                    assignee_parts.append(f"{names}（{tr}）")
                else:
                    assignee_parts.append(tr)

            assignee_display = "; ".join(assignee_parts)

            # 更新工单的 assignee 和 department
            cursor.execute(
                """
                UPDATE tickets SET assignee = ?, updated_at = ? WHERE ticket_no = ?
            """,
                (
                    assignee_display,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ticket_no,
                ),
            )
            conn.commit()
            print(f"[工单分派] 工单 {ticket_no} 已分派给: {assignee_display}")
        else:
            print(f"[工单分派] 工单 {ticket_no} 未检测到分派任务（大脑可能直接回复了）")

        conn.close()
    except Exception as e:
        print(f"[工单分派] 更新工单处理人失败（不影响分派）: {e}")

    print(f"[工单分派] 大脑已分析工单 {ticket_no}，分派流程完成。")

    return response


def _get_ticket_by_no(ticket_no):
    """根据工单号查询工单"""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tickets WHERE ticket_no = ?", (ticket_no,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def _get_ticket_owner_info(ticket):
    """获取工单的提交人和接收人信息（用于通知）"""
    conn = _get_conn()
    cursor = conn.cursor()
    info = {}
    # 提交人姓名
    cursor.execute(
        "SELECT display_name FROM users WHERE username = ?",
        (ticket.get("submitter", ""),),
    )
    row = cursor.fetchone()
    info["submitter_name"] = row["display_name"] if row else ticket.get("submitter", "")
    # 接收人姓名（从assignee字段解析）
    info["assignee_name"] = ticket.get("assignee", "")
    conn.close()
    return info


def update_ticket(ticket_id, data, username=None):
    """更新工单状态（支持数字ID或工单号如TK20260608119）"""
    conn = _get_conn()
    cursor = conn.cursor()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updates = []
    params = []

    for field in ["status", "assignee", "priority", "description"]:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])

    if data.get("status") in ("done", "cancelled"):
        updates.append("resolved_at = ?")
        params.append(now)

    updates.append("updated_at = ?")
    params.append(now)

    # 根据 ticket_id 的格式判断查询条件
    ticket_id_str = str(ticket_id).strip()
    if ticket_id_str.upper().startswith("TK"):
        params.append(ticket_id_str)
        cursor.execute(
            f"UPDATE tickets SET {', '.join(updates)} WHERE ticket_no = ?", params
        )
    else:
        params.append(int(ticket_id_str))
        cursor.execute(f"UPDATE tickets SET {', '.join(updates)} WHERE id = ?", params)

    affected = cursor.rowcount
    conn.commit()
    conn.close()

    if affected == 0:
        return {"success": False, "error": f"工单 {ticket_id} 不存在"}

    return {"success": True, "updated_at": now}


def cancel_ticket(ticket_no, operator_username):
    """
    提交人撤销工单。
    返回操作结果，自动通知接收人。
    """
    ticket = _get_ticket_by_no(ticket_no)
    if not ticket:
        return {"success": False, "error": f"工单 {ticket_no} 不存在"}

    # 权限检查：只有提交人可以撤销
    if ticket["submitter"] != operator_username:
        return {"success": False, "error": "只有工单提交人可以撤销"}

    # 已经完成或已撤销的不能操作
    if ticket["status"] in ("done", "cancelled"):
        status_label = "已完成" if ticket["status"] == "done" else "已撤销"
        return {"success": False, "error": f"工单已{status_label}，无法撤销"}

    # 更新状态
    result = update_ticket(ticket_no, {"status": "cancelled"}, operator_username)
    if not result.get("success"):
        return result

    # 通知接收人
    try:
        owner_info = _get_ticket_owner_info(ticket)
        create_notification(
            {
                "title": f"工单已撤销 - {ticket_no}",
                "content": f"工单「{ticket['title']}」已被提交人撤销。",
                "type": "warning",
                "icon": "🚫",
                "target_user": "all_ssc",
            }
        )
    except Exception as e:
        print(f"[工单撤销] 通知创建失败（不影响撤销）: {e}")

    return {"success": True, "message": "工单已撤销"}


def transfer_ticket(ticket_no, from_username, to_username, reason, from_role):
    """
    工单转办。
    - 当前 assignee 可以将工单转办给其他人
    - Admin/HR_SSC经理 可以转办任意工单
    返回操作结果，自动通知新接收人。
    """
    ticket = _get_ticket_by_no(ticket_no)
    if not ticket:
        return {"success": False, "error": f"工单 {ticket_no} 不存在"}

    # 权限检查
    is_admin = from_role in ("HR_SSC经理", "HRIS工程师", "HR_SSC学科经理")
    assignee_str = ticket.get("assignee") or ""
    is_assignee = (
        from_username in assignee_str or ticket.get("submitter") == from_username
    )

    if not is_admin and not is_assignee:
        return {"success": False, "error": "无权转办此工单"}

    # 已经完成或已撤销的不能转办
    if ticket["status"] in ("done", "cancelled"):
        status_label = "已完成" if ticket["status"] == "done" else "已撤销"
        return {"success": False, "error": f"工单已{status_label}，无法转办"}

    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 获取目标用户姓名
    cursor.execute("SELECT display_name FROM users WHERE username = ?", (to_username,))
    target_row = cursor.fetchone()
    if not target_row:
        conn.close()
        return {"success": False, "error": f"目标用户 {to_username} 不存在"}
    to_display_name = target_row["display_name"]

    # 更新工单 assignee
    cursor.execute(
        """
        UPDATE tickets SET assignee = ?, updated_at = ? WHERE ticket_no = ?
    """,
        (to_display_name, now, ticket_no),
    )

    # 记录转办历史
    cursor.execute(
        """
        INSERT INTO ticket_transfers (ticket_no, from_user, to_user, reason, transferred_at)
        VALUES (?, ?, ?, ?, ?)
    """,
        (ticket_no, from_username, to_username, reason or "", now),
    )

    conn.commit()
    conn.close()

    # 通知新接收人
    try:
        create_notification(
            {
                "title": f"工单转办 - {ticket_no}",
                "content": f"工单「{ticket['title']}」已从 {from_username} 转交给您处理。",
                "type": "info",
                "icon": "🔄",
                "target_user": to_username,
            }
        )
    except Exception as e:
        print(f"[工单转办] 通知创建失败（不影响转办）: {e}")

    return {
        "success": True,
        "message": f"工单已转办给 {to_display_name}（{to_username}）",
        "ticket_no": ticket_no,
        "new_assignee": to_username,
    }


def get_ticket_transfers(ticket_no):
    """获取工单的转办历史记录"""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT t.*, u1.display_name as from_name, u2.display_name as to_name
        FROM ticket_transfers t
        LEFT JOIN users u1 ON t.from_user = u1.username
        LEFT JOIN users u2 ON t.to_user = u2.username
        WHERE t.ticket_no = ?
        ORDER BY t.transferred_at DESC
    """,
        (ticket_no,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def done_ticket(ticket_no, operator_username):
    """
    接收人完成工单。
    返回操作结果，自动通知提交人。
    """
    ticket = _get_ticket_by_no(ticket_no)
    if not ticket:
        return {"success": False, "error": f"工单 {ticket_no} 不存在"}

    # 已经完成或已撤销的不能操作
    if ticket["status"] in ("done", "cancelled"):
        status_label = "已完成" if ticket["status"] == "done" else "已撤销"
        return {"success": False, "error": f"工单已{status_label}，无法重复操作"}

    # 更新状态
    result = update_ticket(ticket_no, {"status": "done"}, operator_username)
    if not result.get("success"):
        return result

    # 通知提交人
    try:
        owner_info = _get_ticket_owner_info(ticket)
        cursor_sql = None
        create_notification(
            {
                "title": f"工单已完成 - {ticket_no}",
                "content": f"您提交的工单「{ticket['title']}」已被处理完成。",
                "type": "success",
                "icon": "✅",
                "target_user": ticket["submitter"],
            }
        )
    except Exception as e:
        print(f"[工单完成] 通知创建失败（不影响完成）: {e}")

    return {"success": True, "message": "工单已标记完成"}


# ==================== 通知服务 ====================


def get_notifications(username=None, limit=50, filter_by="all", cursor=None):
    """获取通知列表（支持游标分页）

    每个用户独立维护已读状态（存储在 notification_reads 关联表），
    不再使用 notifications.is_read 全局字段。

    filter_by: 'all' 全部, 'unread' 未读, 'read' 已读
    cursor: 游标（上一页最后一条通知的 id），用于分页加载
    """
    conn = _get_conn()
    cur = conn.cursor()

    user = username or ""
    cols = "n.id, n.title, n.content, n.type, n.icon, n.target_user, n.created_at"

    # target_user 可能是逗号分隔的用户列表，需要匹配当前用户是否在其中
    target_match = (
        "n.target_user = 'all' "
        "OR n.target_user = ? "
        "OR ',' || n.target_user || ',' LIKE '%,' || ? || ',%'"
    )
    params = [user, user]

    # 额外查询一条用于判断是否有更多数据
    extra_limit = limit + 1
    params.append(extra_limit)

    if filter_by == "unread":
        if cursor:
            cur.execute(
                f"""
                SELECT {cols},
                       0 AS is_read
                FROM notifications n
                LEFT JOIN notification_reads nr 
                  ON nr.notification_id = n.id AND nr.user_id = ?
                WHERE ({target_match})
                  AND nr.notification_id IS NULL
                  AND n.id < ?
                ORDER BY n.created_at DESC LIMIT ?
                """,
                (*params[:2], user, cursor, extra_limit),
            )
        else:
            cur.execute(
                f"""
                SELECT {cols},
                       0 AS is_read
                FROM notifications n
                LEFT JOIN notification_reads nr 
                  ON nr.notification_id = n.id AND nr.user_id = ?
                WHERE ({target_match})
                  AND nr.notification_id IS NULL
                ORDER BY n.created_at DESC LIMIT ?
                """,
                (*params[:2], user, extra_limit),
            )
    elif filter_by == "read":
        if cursor:
            cur.execute(
                f"""
                SELECT {cols},
                       1 AS is_read
                FROM notifications n
                WHERE ({target_match})
                  AND n.id IN (
                      SELECT nr2.notification_id FROM notification_reads nr2 WHERE nr2.user_id = ?
                  )
                  AND n.id < ?
                ORDER BY n.created_at DESC LIMIT ?
                """,
                (*params[:2], user, cursor, extra_limit),
            )
        else:
            cur.execute(
                f"""
                SELECT {cols},
                       1 AS is_read
                FROM notifications n
                WHERE ({target_match})
                  AND n.id IN (
                      SELECT nr2.notification_id FROM notification_reads nr2 WHERE nr2.user_id = ?
                  )
                ORDER BY n.created_at DESC LIMIT ?
                """,
                (*params[:2], user, extra_limit),
            )
    else:  # "all"
        if cursor:
            cur.execute(
                f"""
                SELECT {cols},
                       CASE WHEN nr.notification_id IS NOT NULL THEN 1 ELSE 0 END AS is_read
                FROM notifications n
                LEFT JOIN notification_reads nr 
                  ON nr.notification_id = n.id AND nr.user_id = ?
                WHERE ({target_match})
                  AND n.id < ?
                ORDER BY n.created_at DESC LIMIT ?
                """,
                (*params[:2], user, cursor, extra_limit),
            )
        else:
            cur.execute(
                f"""
                SELECT {cols},
                       CASE WHEN nr.notification_id IS NOT NULL THEN 1 ELSE 0 END AS is_read
                FROM notifications n
                LEFT JOIN notification_reads nr 
                  ON nr.notification_id = n.id AND nr.user_id = ?
                WHERE ({target_match})
                ORDER BY n.created_at DESC LIMIT ?
                """,
                (*params[:2], user, extra_limit),
            )

    rows = cur.fetchall()

    # 判断是否有更多数据
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    # 获取最后一页的 id 作为下一个游标
    next_cursor = rows[-1]["id"] if rows else None

    conn.close()
    result = [dict(r) for r in rows]
    return result, has_more, next_cursor


def mark_notification_read(notif_id, user_id):
    """标记单条通知已读（按用户维度插入 notification_reads 记录）"""
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 使用 INSERT OR IGNORE 避免重复标记
    cursor.execute(
        """
        INSERT OR IGNORE INTO notification_reads (notification_id, user_id, read_at)
        VALUES (?, ?, ?)
    """,
        (notif_id, user_id, now),
    )

    conn.commit()
    conn.close()
    return {"success": True}


def mark_notification_unread(notif_id, user_id):
    """标记单条通知未读（按用户维度删除 notification_reads 记录）"""
    conn = _get_conn()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM notification_reads 
        WHERE notification_id = ? AND user_id = ?
    """,
        (notif_id, user_id),
    )

    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return {"success": True, "deleted": affected > 0}


def mark_all_notifications_read(user_id):
    """标记当前用户所有可见通知为已读"""
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute(
        """
        INSERT OR IGNORE INTO notification_reads (notification_id, user_id, read_at)
        SELECT n.id, ?, ?
        FROM notifications n
        WHERE n.target_user = 'all' OR n.target_user = ?
    """,
        (user_id, now, user_id),
    )

    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return {"success": True, "marked": affected}


# ==================== 通知路由 ====================

# 洞察类型 -> 职责关键词映射（用于按 specialization 粗匹配）
_INSIGHT_TO_SPEC_KEYWORDS = {
    "cost": ["薪酬", "人力成本", "薪资", "人工成本"],
    "attendance": ["考勤", "加班", "出勤", "打卡", "排班"],
    "headcount": ["招聘", "入离职", "HC", "编制", "人数", "离职率"],
    "er": ["员工关系", "合同", "社保", "公积金", "劳动关系"],
    "hris": ["HRIS", "数据", "系统", "信息化"],
}


def _match_spec_to_insight(specialization: str) -> str | None:
    """根据 specialization 文本判断该岗位最关心的洞察类型。"""
    if not specialization:
        return None
    text = specialization.lower()
    for insight_type, keywords in _INSIGHT_TO_SPEC_KEYWORDS.items():
        if any(kw.lower() in text for kw in keywords):
            return insight_type
    return None


def resolve_notification_targets(
    insight_type: str = "",
    insight_level: str = "",
    insight_org: str = "",
    user_context: dict | None = None,
    company: str = "",
) -> list[str]:
    """根据洞察类型、级别、管辖范围和用户上下文，返回应接收该通知的 target_user 列表。

    规则（完全精准，无 all 兜底）：

    管理者路由：
    - 公司级洞察 → 总经理、副总经理
    - 中心级洞察 → 该中心总监
    - 部门级洞察 → 该部门经理

    SSC 路由：
    - 工单/系统类 → SSC 经理
    - 招聘信息 → 招聘专员 + 招聘主管
    - 成本/薪酬信息 → 薪酬专员 + 薪酬主管
    - 考勤信息 → 考勤专员 + 考勤主管
    - 员工关系信息 → 对应职责的员工关系专员 + 员工关系主管
    """
    ctx = user_context or {}
    username = ctx.get("username", "")
    specialization = ctx.get("specialization", "")

    # === 1. 公司级高管：只接收公司级洞察，且必须匹配公司 ===
    if not user_context.get("_all_orgs"):
        # 无兼岗信息，退回单记录匹配逻辑
        role = ctx.get("role", "")
        org = ctx.get("org", "")
        org_level = ctx.get("org_level", "")

        if role in ("总经理", "副总经理"):
            if insight_level == "company":
                try:
                    from src.security.auth import _get_auth_connection

                    conn = _get_auth_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT org FROM user_roles WHERE user_id = (SELECT id FROM users WHERE username = ?) AND org != ''",
                        (username,),
                    )
                    user_companies = [r["org"] for r in cursor.fetchall()]
                    conn.close()
                    if company and company in user_companies:
                        return [username] if username else []
                except Exception:
                    pass
            return []

        if (
            org
            and org_level in ("center", "department")
            and role in ("总监", "经理", "HRBP")
        ):
            if insight_level == org_level and insight_org == org:
                return [username] if username else []
            return []

        if role == "HR_SSC经理":
            if username == "admin":
                return []
            if insight_type in ("hris", "headcount", "cost", "attendance", "er", ""):
                if insight_level == "company":
                    return [username] if username else []
                if insight_level in ("center", "department") and insight_org == org:
                    return [username] if username else []
            return []

        if role == "HR_SSC学科经理":
            if insight_type in ("hris", "headcount", "cost", "attendance", "er", ""):
                if insight_level == "company":
                    return [username] if username else []
                if insight_level in ("center", "department") and insight_org == org:
                    return [username] if username else []
            return []

        if "HRIS" in role:
            if insight_type == "hris":
                return [username] if username else []
            return []

        spec_to_type_map = {
            "招聘": ["headcount"],
            "薪酬": ["cost"],
            "考勤": ["attendance"],
            "员工关系": ["er"],
            "合同": ["er"],
            "社保": ["er"],
            "离职": ["er"],
        }
        if specialization:
            for spec_keyword, allowed_types in spec_to_type_map.items():
                if spec_keyword.lower() in specialization.lower():
                    if insight_type in allowed_types:
                        return [username] if username else []
        return []

    # === 有新兼岗信息：遍历所有兼岗记录匹配 ===
    all_orgs = user_context.get("_all_orgs", [])  # list of (role, org, org_level)

    # 1. 先检查是否是公司级高管
    all_roles = [o[0] for o in all_orgs]
    if "总经理" in all_roles or "副总经理" in all_roles:
        if insight_level == "company":
            try:
                from src.security.auth import _get_auth_connection

                conn = _get_auth_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT org FROM user_roles WHERE user_id = (SELECT id FROM users WHERE username = ?) AND org != ''",
                    (username,),
                )
                user_companies = [r["org"] for r in cursor.fetchall()]
                conn.close()
                if company and company in user_companies:
                    return [username] if username else []
            except Exception:
                pass
            return []

    # 2. 检查管理层（总监/经理/HRBP）的 org 匹配
    for role, org, org_level in all_orgs:
        if (
            org
            and org_level in ("center", "department")
            and role in ("总监", "经理", "HRBP")
        ):
            if insight_level == org_level and insight_org == org:
                return [username] if username else []

    # 3. SSC 经理
    if "HR_SSC经理" in all_roles:
        if username == "admin":
            return []
        if insight_type in ("hris", "headcount", "cost", "attendance", "er", ""):
            if insight_level == "company":
                return [username] if username else []
            # 检查是否有匹配的 org
            for _, org, org_level in all_orgs:
                if insight_level in ("center", "department") and insight_org == org:
                    return [username] if username else []
            return []

    # 4. SSC 学科经理
    if "HR_SSC学科经理" in all_roles:
        if insight_type in ("hris", "headcount", "cost", "attendance", "er", ""):
            if insight_level == "company":
                return [username] if username else []
            for _, org, org_level in all_orgs:
                if insight_level in ("center", "department") and insight_org == org:
                    return [username] if username else []
            return []

    # 5. HRIS 工程师
    if any("HRIS" in r for r in all_roles):
        if insight_type == "hris":
            return [username] if username else []
        return []

    # 6. SSC 操作层员工：按 specialization 匹配
    spec_to_type_map = {
        "招聘": ["headcount"],
        "薪酬": ["cost"],
        "考勤": ["attendance"],
        "员工关系": ["er"],
        "合同": ["er"],
        "社保": ["er"],
        "离职": ["er"],
    }
    if specialization:
        for spec_keyword, allowed_types in spec_to_type_map.items():
            if spec_keyword.lower() in specialization.lower():
                if insight_type in allowed_types:
                    return [username] if username else []

    return []


def create_notification(data):
    """创建通知"""
    conn = _get_conn()
    cursor = conn.cursor()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO notifications (title, content, type, icon, target_user, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            data.get("title", ""),
            data.get("content", ""),
            data.get("type", "info"),
            data.get("icon", "🔔"),
            _normalize_target_user(data.get("target_user", "all")),
            now,
        ),
    )

    conn.commit()
    notif_id = cursor.lastrowid
    conn.close()
    return {"id": notif_id, "created_at": now}


# ==================== 个人中心服务 ====================


def get_user_profile(username):
    """获取用户个人信息"""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT username, display_name, role, department, employee_id, created_at
        FROM users WHERE username = ?
    """,
        (username,),
    )
    row = cursor.fetchone()

    # 获取兼岗角色
    cursor.execute(
        "SELECT ur.role FROM user_roles ur JOIN users u ON ur.user_id = u.id WHERE u.username = ?",
        (username,),
    )
    extra_roles = [r["role"] for r in cursor.fetchall()]

    conn.close()

    if not row:
        return None

    profile = dict(row)
    profile["extra_roles"] = extra_roles
    return profile


def update_user_profile(username, data):
    """更新用户个人信息"""
    conn = _get_conn()
    cursor = conn.cursor()

    updates = []
    params = []

    if "display_name" in data:
        updates.append("display_name = ?")
        params.append(data["display_name"])
    if "department" in data:
        updates.append("department = ?")
        params.append(data["department"])

    if not updates:
        conn.close()
        return {"success": False, "message": "没有需要更新的字段"}

    params.append(username)
    cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE username = ?", params)
    conn.commit()
    conn.close()
    return {"success": True, "message": "个人信息已更新"}


def change_password(username, old_password, new_password):
    """修改密码"""
    from src.security.auth import _hash_password

    conn = _get_conn()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT password_hash, salt FROM users WHERE username = ?", (username,)
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"success": False, "message": "用户不存在"}

    old_h, _ = _hash_password(old_password, row["salt"])
    if old_h != row["password_hash"]:
        conn.close()
        return {"success": False, "message": "原密码错误"}

    new_hash, new_salt = _hash_password(new_password)
    cursor.execute(
        "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
        (new_hash, new_salt, username),
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": "密码已修改"}


def init_chat_tables():
    """初始化即时通讯表"""
    conn = _get_conn()
    cursor = conn.cursor()

    # 对话会话表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            user1 TEXT NOT NULL,
            user2 TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL,
            closed_at TEXT DEFAULT NULL
        )
    """)

    # 聊天消息表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
        )
    """)

    conn.commit()
    conn.close()


def start_chat_session(user1, target):
    """
    发起一个即时对话。
    user1: 发起人用户名（如 "lis"）
    target: 对方的用户名或显示名（如 "liunannan" 或 "刘南南"）
    """
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 将target（可能是显示名）解析为用户名
    cursor.execute(
        "SELECT username FROM users WHERE username = ? OR display_name = ?",
        (target, target),
    )
    target_row = cursor.fetchone()
    if target_row:
        user2 = target_row["username"]
    else:
        user2 = target  # 找不到就原样存储

    # 检查是否已有活跃会话（用用户名比较）
    cursor.execute(
        "SELECT session_id FROM chat_sessions WHERE status='active' AND ((user1=? AND user2=?) OR (user1=? AND user2=?))",
        (user1, user2, user2, user1),
    )
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return {
            "success": True,
            "session_id": existing["session_id"],
            "message": "已有活跃会话",
        }

    session_id = f"chat-{user1}-{user2}-{int(datetime.now().timestamp())}"
    cursor.execute(
        "INSERT INTO chat_sessions (session_id, user1, user2, status, created_at) VALUES (?, ?, ?, 'active', ?)",
        (session_id, user1, user2, now),
    )
    conn.commit()
    conn.close()
    return {"success": True, "session_id": session_id}


def send_chat_message(session_id, sender, content):
    """发送一条聊天消息（默认 delivery_status='pending'，接收方登录后标记为 delivered）"""
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 确保 delivery_status 列存在（兼容旧表）
    try:
        cursor.execute(
            "INSERT INTO chat_messages (session_id, sender, content, created_at, delivery_status) VALUES (?, ?, ?, ?, 'pending')",
            (session_id, sender, content, now),
        )
    except sqlite3.OperationalError:
        # 列不存在，先添加
        cursor.execute(
            "ALTER TABLE chat_messages ADD COLUMN delivery_status TEXT DEFAULT 'delivered'"
        )
        cursor.execute(
            "INSERT INTO chat_messages (session_id, sender, content, created_at, delivery_status) VALUES (?, ?, ?, ?, 'pending')",
            (session_id, sender, content, now),
        )
    message_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"success": True, "message_id": message_id, "created_at": now}


def poll_chat_messages(session_id, last_id=0, limit=50):
    """拉取新消息（轮询用）"""
    conn = _get_conn()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM chat_messages WHERE session_id = ? AND id > ? ORDER BY id ASC LIMIT ?",
        (session_id, last_id, limit),
    )
    messages = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"success": True, "messages": messages}


def get_pending_messages(session_id, receiver):
    """获取待推送给指定接收方的消息（只返回 pending 状态的消息）"""
    conn = _get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT * FROM chat_messages WHERE session_id = ? AND sender != ? AND (delivery_status = 'pending' OR delivery_status IS NULL) ORDER BY id ASC",
            (session_id, receiver),
        )
    except sqlite3.OperationalError:
        # delivery_status 列不存在，退化为返回所有消息
        cursor.execute(
            "SELECT * FROM chat_messages WHERE session_id = ? AND sender != ? ORDER BY id ASC",
            (session_id, receiver),
        )
    messages = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"success": True, "messages": messages}


def mark_messages_delivered(session_id, receiver):
    """将指定会话中发送给 receiver 的消息标记为已推送"""
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        cursor.execute(
            "UPDATE chat_messages SET delivery_status = 'delivered' WHERE session_id = ? AND sender != ? AND (delivery_status = 'pending' OR delivery_status IS NULL)",
            (session_id, receiver),
        )
        affected = cursor.rowcount
        conn.commit()
    except sqlite3.OperationalError:
        # delivery_status 列不存在，跳过
        affected = 0
    conn.close()
    return {"success": True, "marked": affected}


def has_pending_messages(username):
    """检查用户是否有待推送的聊天消息（用于登录时判断是否需要加载历史会话）"""
    conn = _get_conn()
    cursor = conn.cursor()

    # 查找用户参与的所有活跃会话
    cursor.execute(
        "SELECT session_id FROM chat_sessions WHERE status='active' AND (user1=? OR user2=?)",
        (username, username),
    )
    sessions = cursor.fetchall()

    for s in sessions:
        sid = s["session_id"]
        try:
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM chat_messages WHERE session_id = ? AND sender != ? AND (delivery_status = 'pending' OR delivery_status IS NULL)",
                (sid, username),
            )
            row = cursor.fetchone()
            if row and row["cnt"] > 0:
                conn.close()
                return True
        except sqlite3.OperationalError:
            # delivery_status 列不存在，有活跃会话就返回 True
            conn.close()
            return True

    conn.close()
    return False


def close_chat_session(session_id):
    """关闭对话"""
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute(
        "UPDATE chat_sessions SET status = 'closed', closed_at = ? WHERE session_id = ?",
        (now, session_id),
    )
    conn.commit()
    conn.close()
    return {"success": True}


def get_active_chat(username):
    """获取用户的活跃对话"""
    conn = _get_conn()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM chat_sessions WHERE status='active' AND (user1=? OR user2=?)",
        (username, username),
    )
    session = cursor.fetchone()
    conn.close()

    if session:
        return {"success": True, "session": dict(session)}
    return {"success": False}
