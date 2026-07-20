"""
任务分派器（Task Dispatcher）—— 下行脊髓的核心引擎

将大脑的结构化决策转化为具体操作：
1. 创建CLI任务（分派给角色CLI Agent）
2. 创建工单（通过工单系统）
3. 创建通知（推送到门户）
4. 结果反馈给上行脊髓

大脑输出的结构化指令格式：
{
  "actions": [
    {
      "type": "create_ticket",
      "target_role": "员工关系专员",
      "title": "...",
      "description": "...",
      "priority": "normal",
      "context": {}
    },
    {
      "type": "dispatch_cli_task",
      "target_role": "HR_SSC学科经理",
      "title": "...",
      "description": "...",
      "skill_name": "employment_certificate",
      "skill_params": {"employee_name": "张三"},
      "priority": "high",
      "context": {}
    },
    {
      "type": "create_notification",
      "target_user": "all_ssc",
      "title": "...",
      "content": "...",
      "priority": "normal"
    },
    {
      "type": "reply_employee",
      "message": "您的请求已受理..."
    }
  ]
}
"""

import uuid
import json
from datetime import datetime

from src.data.cli_tasks import create_cli_task
from src.api.services import create_ticket, create_notification


def generate_dispatch_id(prefix="DS"):
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    return f"{prefix}-{ts}-{short_uuid}"


# 角色映射：从数据库 role_departments 表读取（支持运行时配置）
# 如果数据库不可用，回退到硬编码默认值
def _load_role_mappings() -> tuple[dict, dict, dict, set]:
    """加载角色映射（优先从数据库读取，回退到默认值）"""
    # 默认映射（数据库不可用时的回退）
    _default_assignee = {
        "员工关系专员": "guanxi_spec",
        "员工关系主管": "guanxi_mgr",
        "薪酬专员": "xinchou_spec",
        "薪酬主管": "xinchou_mgr",
        "考勤专员": "kaoqin_spec",
        "招聘专员": "zhaopin_spec",
        "招聘主管": "zhaopin_mgr",
        "HRIS工程师": "hris_eng",
        "HR_SSC经理": "ssc_mgr",
        "HR_SSC学科经理": "ssc_subject_mgr",
        "高级HRIS工程师": "hris_senior",
    }
    _default_dept = {
        "员工关系专员": "DEPT_EMPLOYEE_RELATIONS",
        "员工关系主管": "DEPT_EMPLOYEE_RELATIONS",
        "薪酬专员": "DEPT_PAYROLL",
        "薪酬主管": "DEPT_PAYROLL",
        "考勤专员": "DEPT_ATTENDANCE",
        "招聘专员": "DEPT_RECRUITMENT",
        "招聘主管": "DEPT_RECRUITMENT",
        "HRIS工程师": "DEPT_HRIS",
        "HR_SSC经理": "DEPT_MANAGEMENT",
        "HR_SSC学科经理": "DEPT_MANAGEMENT",
        "高级HRIS工程师": "DEPT_HRIS",
    }
    try:
        from src.security.auth import get_role_department_mapping

        mapping = get_role_department_mapping()
        role_to_dept = mapping.get("role_to_dept", {})
        role_to_assignee = mapping.get("role_to_assignee", {})
        # 用数据库数据覆盖默认值（数据库为主，默认为兜底）
        merged_dept = {**_default_dept, **role_to_dept}
        merged_assignee = {**_default_assignee, **role_to_assignee}
        return (
            merged_dept,
            merged_assignee,
            {v: k for k, v in merged_assignee.items()},
            set(merged_assignee.keys()),
        )
    except Exception as e:
        print(f"[分派器] 加载角色映射失败，使用默认值: {e}")
        return (
            _default_dept,
            _default_assignee,
            {v: k for k, v in _default_assignee.items()},
            set(_default_assignee.keys()),
        )


# 启动时加载一次，后续可通过 reload_role_mappings() 刷新
ROLE_TO_DEPT, ROLE_TO_ASSIGNEE, ASSIGNEE_TO_ROLE, VALID_ROLES = _load_role_mappings()


def reload_role_mappings():
    """刷新角色映射（角色配置变更后调用）"""
    global ROLE_TO_DEPT, ROLE_TO_ASSIGNEE, ASSIGNEE_TO_ROLE, VALID_ROLES
    ROLE_TO_DEPT, ROLE_TO_ASSIGNEE, ASSIGNEE_TO_ROLE, VALID_ROLES = (
        _load_role_mappings()
    )
    print(f"[分派器] 角色映射已刷新，共 {len(VALID_ROLES)} 个角色")


def _strip_system_prefixes(text: str) -> str:
    """从文本中剥离系统路由前缀（防御性清理）。

    处理以下前缀（都是代码注入的死格式）：
    - [渠道:web] / [渠道:cli]
    - [安全规则]
    - [Marathon执行]
    - 我是{role}（{name}），
    """
    cleaned = text.strip()
    # 移除 [渠道:xxx]
    if cleaned.startswith("[渠道:"):
        idx = cleaned.find("]")
        if idx >= 0:
            cleaned = cleaned[idx + 1 :].strip()
    # 移除 [安全规则]
    if cleaned.startswith("[安全规则]"):
        cleaned = cleaned[len("[安全规则]") :].strip()
    # 移除 [Marathon执行]
    if cleaned.startswith("[Marathon执行]"):
        cleaned = cleaned[len("[Marathon执行]") :].strip()
    # 移除 "我是{role}（{name}），"
    if cleaned.startswith("我是"):
        paren_open = cleaned.find("（")
        paren_close = cleaned.find("）")
        if paren_open > 0 and paren_close > paren_open:
            rest = cleaned[paren_close + 1 :]
            if rest.startswith("，") or rest.startswith(","):
                rest = rest[1:]
            cleaned = rest.strip()
    # 清理残留 [xxx] 标记
    while cleaned.startswith("["):
        idx = cleaned.find("]")
        if idx >= 0:
            cleaned = cleaned[idx + 1 :].strip()
        else:
            break
    return cleaned if cleaned else text


def _normalize_role_name(raw_role: str, max_retries: int = 3) -> tuple:
    """规范化角色名称（三级容错机制）

    1. 先尝试反向映射（内部代码 → 人类可读名称）
    2. 如果映射失败，返回 (None, None) 表示需要大脑重新输出
    3. 如果超过 max_retries 次仍无法匹配，返回 ("HRIS工程师", "⚠️ 大脑输出错误，请优化")

    Returns:
        (normalized_role, error_tag) - normalized_role 为规范化后的角色名，
        error_tag 为错误标注（如果有的话）
    """
    # 第一步：检查是否已经是有效角色名
    if raw_role in VALID_ROLES:
        return raw_role, ""

    # 第二步：尝试反向映射（内部代码 → 人类可读名称）
    mapped_role = ASSIGNEE_TO_ROLE.get(raw_role)
    if mapped_role and mapped_role in VALID_ROLES:
        return mapped_role, ""

    # 第三步：映射失败，返回 None 让调用方决定如何处理
    # 调用方应该让大脑重新输出，最多重试 max_retries 次
    return None, ""


def _resolve_assignee_name(target_role: str, target_username: str = "") -> str:
    """根据角色名和用户名查询数据库中对应的具体处理人姓名。

    优先用 target_username 精确匹配（大脑通过 specialization 判断后的指定）。
    如果未指定 target_username，且角色只有1人，返回该人姓名。
    如果角色有多人且无精确指定，返回空字符串（由调用方用角色名兜底）。
    """
    try:
        from src.security.auth import get_all_ssc_specializations

        specs = get_all_ssc_specializations()

        # 优先：target_username 精确匹配
        if target_username:
            for s in specs:
                if s.get("username") == target_username:
                    return s["display_name"]

        # 次选：角色只有1人时直接返回
        names = [s["display_name"] for s in specs if s.get("role") == target_role]
        if len(names) == 1:
            return names[0]

        # 多人同角色且无精确指定：返回空，让调用方用角色名兜底
        return ""
    except Exception:
        return ""


def _create_hris_escalation_for_failed_notification(
    title: str, content: str, insight_type: str, insight_level: str, insight_org: str
):
    """通知精准路由无匹配用户时，创建HRIS工单升级处理。

    将异常信息告知HRIS工程师，避免悄悄丢失。
    """
    task_id = generate_dispatch_id("ESC-NOTIF")
    description = (
        f"通知路由异常：无法找到合适的接收人。\n\n"
        f"洞察类型：{insight_type}\n"
        f"洞察级别：{insight_level}\n"
        f"组织：{insight_org}\n\n"
        f"标题：{title}\n"
        f"内容：{content}\n\n"
        f"请检查：\n"
        f"1. 用户-角色配置是否完整\n"
        f"2. resolve_notification_targets 逻辑是否正常\n"
        f"3. 是否需要手动补充接收人或调整路由规则"
    )
    task_data = {
        "task_id": task_id,
        "source": "dispatcher",
        "event_type": "notification_routing_failure",
        "target_role": "HRIS工程师",
        "target_username": "",
        "title": f"[通知路由异常]{title}",
        "description": description,
        "context": {},
        "skill_name": "",
        "skill_params": {},
        "priority": "urgent",
        "linked_ticket_id": "",
    }
    create_cli_task(task_data)
    print(f"[分派器] 通知路由异常，已创建HRIS升级工单: {task_id}")


def dispatch_actions(
    actions: list, session_id: str = None, cross_round_seen: set = None
) -> dict:
    """
    执行一系列分派动作。返回执行结果摘要。

    Args:
        actions: 分派动作列表
        session_id: 会话ID
        cross_round_seen: 跨轮次通知去重集合（外部传入，生命周期长于单次调用）
    """
    _notif_seen: set = cross_round_seen if cross_round_seen is not None else set()
    results = []

    for action in actions:
        action_type = action.get("type", "")

        if action_type == "create_ticket":
            result = _dispatch_ticket(action)
            results.append(result)

        elif action_type == "dispatch_cli_task":
            result = _dispatch_cli_task(action)
            results.append(result)

        elif action_type == "create_notification":
            result = _dispatch_notification(action, _notif_seen)
            results.append(result)

        elif action_type == "reply_employee":
            # 回复员工（通过上行脊髓最终返回）
            results.append({"type": "reply", "message": action.get("message", "")})

        else:
            print(f"[分派器] 未知动作类型: {action_type}")
            results.append(
                {"type": action_type, "success": False, "error": "未知动作类型"}
            )

    summary = {
        "total_actions": len(actions),
        "executed": len(results),
        "ticket_created": sum(1 for r in results if r.get("type") == "ticket"),
        "cli_tasks_dispatched": sum(1 for r in results if r.get("type") == "cli_task"),
        "notifications_created": sum(
            1 for r in results if r.get("type") == "notification"
        ),
        "results": results,
    }

    print(
        f"[分派器] 分派完成: {summary['ticket_created']}个工单, "
        f"{summary['cli_tasks_dispatched']}个CLI任务, "
        f"{summary['notifications_created']}个通知"
    )

    return summary


def _dispatch_ticket(action: dict) -> dict:
    """创建工单（带角色规范化）"""
    raw_role = action.get("target_role", "")

    # 角色规范化：内部代码 → 人类可读名称
    target_role, error_tag = _normalize_role_name(raw_role)
    if not target_role:
        target_role = "HRIS工程师"
        error_tag = error_tag or "⚠️ 大脑输出错误，请优化"

    assignee = ROLE_TO_ASSIGNEE.get(target_role, "")
    department = ROLE_TO_DEPT.get(target_role, "SSC")

    # 清理 title/description 中可能残留的系统路由前缀（防御性措施）
    title = _strip_system_prefixes(action.get("title", ""))
    description = _strip_system_prefixes(action.get("description", ""))

    # 系统自动生成的工单，submitter 固定为 "SSC系统"，避免员工端重复显示
    submitter_name = action.get("submitter_name", "")
    submitter_username = action.get("submitter", "")
    submitter_display = "SSC系统"

    # 工单标题添加提交人信息，让处理人知道是谁提问的
    if submitter_name and submitter_username:
        title = f"{title} - 提交人: {submitter_name}({submitter_username})"

    ticket_data = {
        "title": title,
        "category": action.get("category", "一般"),
        "description": description,
        "priority": action.get("priority", "normal"),
        "assignee": assignee,
        "department": department,
    }

    # 解析具体处理人姓名（优先用大脑指定的 target_username）
    assignee_name = _resolve_assignee_name(
        target_role, action.get("target_username", "")
    )

    # 工单 assignee 字段必须使用人名或角色名（中文），因为
    # get_tickets(receiver) 查询的是 LIKE '%角色名%' 或 LIKE '%姓名%'
    # 使用 ROLE_TO_ASSIGNEE 的系统编码（如 guanxi_spec）会导致工单对处理人不可见
    human_assignee = assignee_name if assignee_name else target_role
    if error_tag:
        human_assignee += f" {error_tag}"
    ticket_data["assignee"] = human_assignee

    result = create_ticket(
        ticket_data, submitter_display, submitter_display, skip_dispatch=True
    )

    print(
        f"[分派器] 工单已创建: {result.get('ticket_no', '')} → {target_role}({human_assignee})"
    )

    return {
        "type": "ticket",
        "success": True,
        "ticket_no": result.get("ticket_no", ""),
        "ticket_id": result.get("id", ""),
        "target_role": target_role,
        "assignee": human_assignee,
        "assignee_name": assignee_name,
    }


def _dispatch_cli_task(action: dict) -> dict:
    """分派CLI任务（带角色规范化）"""
    raw_role = action.get("target_role", "")

    # 角色规范化：内部代码 → 人类可读名称
    target_role, error_tag = _normalize_role_name(raw_role)
    if not target_role:
        target_role = "HRIS工程师"
        error_tag = error_tag or "⚠️ 大脑输出错误，请优化"

    task_id = generate_dispatch_id("CT")
    # 清理 title/description 中可能残留的系统路由前缀
    task_data = {
        "task_id": task_id,
        "source": "brain",
        "event_type": action.get("event_type", ""),
        "target_role": target_role,
        "target_username": action.get("target_username", ""),
        "title": _strip_system_prefixes(action.get("title", "")),
        "description": _strip_system_prefixes(action.get("description", "")),
        "context": action.get("context", {}),
        "skill_name": action.get("skill_name", ""),
        "skill_params": action.get("skill_params", {}),
        "priority": action.get("priority", "normal"),
        "linked_ticket_id": action.get("linked_ticket_id", ""),
    }

    result = create_cli_task(task_data)

    # 解析具体处理人姓名（优先用大脑指定的 target_username）
    assignee_name = _resolve_assignee_name(
        target_role, action.get("target_username", "")
    )

    print(f"[分派器] CLI任务已分派: {task_id} → {target_role} {assignee_name}")

    return {
        "type": "cli_task",
        "success": True,
        "task_id": task_id,
        "target_role": target_role,
        "assignee_name": assignee_name,
        "skill_name": action.get("skill_name", ""),
    }


def _dispatch_notification(action: dict, seen: set) -> dict:
    """创建通知（按洞察元数据精准路由，只创建 1 条通知）"""
    title = action.get("title", "")
    content = action.get("content", "")
    insight_type = action.get("insight_type", "")
    insight_level = action.get("insight_level", "")
    insight_org = action.get("insight_org", "")

    # === 详细日志：用于调试 ===
    print(f"[分派器-调试] 通知详情:")
    print(f"  - title: {title}")
    print(f"  - insight_level: {insight_level}")
    print(f"  - insight_org: {insight_org}")
    print(f"  - insight_type: {insight_type}")
    print(f"  - raw action keys: {list(action.keys())}")

    # 去重键：基于洞察元数据 + 标题 + 内容
    dedup_key = (insight_level, insight_org, insight_type, title, content)
    if dedup_key in seen:
        return {
            "type": "notification",
            "success": True,
            "notification_id": "",
            "skipped": True,
        }
    seen.add(dedup_key)

    try:
        from src.api.services import resolve_notification_targets
        from src.security.auth import list_users

        # 获取所有用户
        users = list_users()

        # 收集所有应该接收此通知的用户名
        target_usernames = []
        for user_info in users:
            username = user_info.get("username", "")
            if not username:
                continue

            # 获取用户所有兼岗记录
            from src.security.auth import _get_auth_connection

            auth_conn = _get_auth_connection()
            auth_cursor = auth_conn.cursor()
            auth_cursor.execute(
                "SELECT role, org, org_level FROM user_roles WHERE user_id = (SELECT id FROM users WHERE username = ?)",
                (username,),
            )
            all_orgs_rows = auth_cursor.fetchall()
            auth_conn.close()

            all_orgs = []
            for r in all_orgs_rows:
                all_orgs.append((r["role"], r["org"] or "", r["org_level"] or ""))

            user_ctx = {
                "role": user_info.get("role", ""),
                "org": user_info.get("org", ""),
                "org_level": user_info.get("org_level", ""),
                "username": username,
                "specialization": user_info.get("specialization", ""),
                "_all_orgs": all_orgs,  # 所有兼岗记录
            }

            targets = resolve_notification_targets(
                insight_type=insight_type,
                insight_level=insight_level,
                insight_org=insight_org,
                user_context=user_ctx,
                company=action.get("company", ""),
            )

            if targets:
                # targets 返回的是用户名列表，可能有多个人
                # 禁止 "all" 广播：只保留具体用户名
                for t in targets:
                    if t.startswith("scope:"):
                        # scope:org 需要展开为具体用户
                        org = t[6:]
                        # 稍后统一展开
                        pass
                    else:
                        target_usernames.append(t)

        if not target_usernames:
            print(f"[分派器] 通知精准路由无匹配用户: {title}")
            # 无匹配用户时创建HRIS工单升级处理
            _create_hris_escalation_for_failed_notification(
                title, content, insight_type, insight_level, insight_org
            )
            return {
                "type": "notification",
                "success": True,
                "notification_id": 0,
                "targets_count": 0,
            }

        # 展开 scope:org 为目标用户列表
        final_targets = []
        for t in target_usernames:
            if t.startswith("scope:"):
                org = t[6:]
                from src.security.auth import _get_auth_connection

                conn = _get_auth_connection()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT u.username FROM users u
                    JOIN user_roles ur ON u.id = ur.user_id
                    WHERE ur.org = ?
                      AND ur.role IN (
                          'HR_SSC经理', 'HR_SSC学科经理',
                          'HRIS工程师', '高级HRIS工程师'
                      )
                      AND u.status = 'active'
                    """,
                    (org,),
                )
                rows = cursor.fetchall()
                conn.close()
                final_targets.extend([r["username"] for r in rows])
            else:
                final_targets.append(t)

        # 创建 1 条通知，target_user 设为实际接收用户列表
        notif_data = {
            "title": title,
            "content": content,
            "type": action.get("notif_type", "info"),
            "icon": action.get("icon", "🔔"),
            "target_user": ",".join(final_targets),
        }

        result = create_notification(notif_data)

        # 打印接收者详细信息
        from src.security.auth import _get_auth_connection

        conn = _get_auth_connection()
        cursor = conn.cursor()
        placeholders = ",".join(["?" for _ in final_targets])
        cursor.execute(
            f"SELECT username, display_name FROM users WHERE username IN ({placeholders})",
            final_targets,
        )
        user_rows = cursor.fetchall()
        conn.close()

        user_map = {r["username"]: r["display_name"] for r in user_rows}
        receiver_details = []
        for u in final_targets:
            name = user_map.get(u, "?")
            receiver_details.append(f"{u}-{name}")
        print(
            f"[分派器] 通知已创建: {title} → {len(final_targets)} 个接收者: {', '.join(receiver_details)}"
        )

        return {
            "type": "notification",
            "success": True,
            "notification_id": result.get("id", 0),
            "targets_count": len(final_targets),
        }

    except Exception as e:
        print(f"[分派器] 精准路由异常: {e}")
        import traceback

        traceback.print_exc()
        raise
