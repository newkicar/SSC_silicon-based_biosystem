"""
权限控制（RBAC）—— 基于角色的信息可见性

核心原则：
- 排除法：默认可查看所有字段，通过 deny_fields 定义不可查看的字段
- 范围限制：中心总监只看本中心，部门经理只看本部门
- 一人多角色：同一用户可兼多个角色，权限取并集（最大权限）
- 审计日志：所有数据访问可追溯
"""
import re
from datetime import datetime
from typing import Optional
from src.data.task_queue import get_connection


# ==================== 角色权限配置（排除法） ====================
# deny_fields: 该角色不可查看的字段列表
# scope_restricted: 是否有数据范围限制（True=只能看自己管辖范围内的数据）
# scope_level: 范围级别（company/center/department/none）
# approval_level: 审批等级

ROLE_PERMISSIONS = {
    # ==================== 组织管理层角色 ====================
    "总经理": {
        "deny_fields": [],
        "scope_restricted": False,
        "scope_level": "company",
        "approval_level": 5,
    },
    "副总经理": {
        "deny_fields": [],
        "scope_restricted": False,
        "scope_level": "company",
        "approval_level": 4,
    },
    "总监": {
        "deny_fields": [],
        "scope_restricted": True,
        "scope_level": "per_role",   # 按每条user_role记录的org确定范围
        "approval_level": 3,
    },
    "经理": {
        "deny_fields": [],
        "scope_restricted": True,
        "scope_level": "per_role",
        "approval_level": 2,
    },
    "HRBP": {
        "deny_fields": ["岗级", "薪资等级", "薪酬信息"],
        "scope_restricted": True,
        "scope_level": "per_role",
        "approval_level": 2,
    },
    # ==================== SSC操作层角色 ====================
    "HR_SSC经理": {
        "deny_fields": [],
        "scope_restricted": False,
        "scope_level": "company",
        "approval_level": 4,
    },
    "HR_SSC经理": {
        "deny_fields": [],
        "scope_restricted": False,
        "scope_level": "company",
        "approval_level": 4,
    },
    "HRIS工程师": {
        "deny_fields": [],
        "scope_restricted": False,
        "scope_level": "company",
        "approval_level": 0,
    },
    "薪酬主管": {
        "deny_fields": [],           # 无限制，最高查看权限
        "scope_restricted": False,
        "scope_level": "company",
        "approval_level": 2,
    },
    "薪酬专员": {
        "deny_fields": [],           # 无限制，最高查看权限
        "scope_restricted": False,
        "scope_level": "company",
        "approval_level": 0,
    },
    "考勤专员": {
        "deny_fields": ["薪资等级", "薪酬信息"],  # 不可查看员工薪酬信息
        "scope_restricted": False,
        "scope_level": "company",
        "approval_level": 0,
    },
    "招聘主管": {
        "deny_fields": ["岗级", "薪资等级", "薪酬信息"],  # 不可查看岗级、薪酬信息
        "scope_restricted": False,
        "scope_level": "company",
        "approval_level": 2,
    },
    "招聘专员": {
        "deny_fields": ["岗级", "薪资等级", "薪酬信息"],
        "scope_restricted": False,
        "scope_level": "company",
        "approval_level": 0,
    },
    "员工关系主管": {
        "deny_fields": ["岗级", "薪资等级", "薪酬信息"],
        "scope_restricted": False,
        "scope_level": "company",
        "approval_level": 2,
    },
    "员工关系专员": {
        "deny_fields": ["岗级", "薪资等级", "薪酬信息"],
        "scope_restricted": False,
        "scope_level": "company",
        "approval_level": 0,
    },
    "中心总监": {
        "deny_fields": [],            # 可查看所有字段（含岗级、薪酬），但仅限本中心
        "scope_restricted": True,
        "scope_level": "center",      # 范围：本中心
        "approval_level": 3,
    },
    "部门经理": {
        "deny_fields": [],            # 可查看所有字段（含岗级、薪酬），但仅限本部门
        "scope_restricted": True,
        "scope_level": "department",  # 范围：本部门
        "approval_level": 2,
    },
}


# ==================== 字段敏感性标记 ====================
# 标记哪些字段属于"岗级"或"薪酬"类，用于排除法过滤
# 花名册Excel列名映射中对应的敏感字段
GRADE_FIELDS = {"岗级", "发展通道"}        # 岗级相关
SALARY_FIELDS = {"薪资等级", "薪酬信息", "工资"}  # 薪酬相关


def get_deny_fields_for_role(role: str) -> set:
    """获取某角色被禁止查看的字段集合"""
    perms = ROLE_PERMISSIONS.get(role, {})
    deny = set(perms.get("deny_fields", []))
    return deny


def get_denied_fields_for_roles(roles: list) -> set:
    """
    获取多角色的禁止字段（取交集）。
    只有当用户的所有角色都不能看某个字段时，才禁止。
    如果用户有任意一个角色可以看该字段，则允许。
    这是"兼岗"场景的合理逻辑：兼了薪酬主管的招聘主管可以看到薪酬信息。
    
    roles: 角色名列表（字符串），如 ["招聘主管", "员工关系主管"]
    """
    if not roles:
        return set()

    # 兼容：roles可能是字符串列表或字典列表
    role_names = []
    for r in roles:
        if isinstance(r, dict):
            role_names.append(r.get("role", ""))
        else:
            role_names.append(r)

    deny_sets = [get_deny_fields_for_role(r) for r in role_names]
    # 取交集：只有所有角色都被禁止的字段才真正禁止
    result = deny_sets[0]
    for s in deny_sets[1:]:
        result = result & s
    return result


def filter_record_by_permissions(record: dict, roles: list) -> dict:
    """
    根据用户角色过滤单条记录中的字段。
    排除法：只删除 deny_fields 中定义的字段。
    """
    denied = get_denied_fields_for_roles(roles)
    if not denied:
        return record

    filtered = {}
    for key, value in record.items():
        # 检查字段名是否在禁止列表中
        # 也检查模糊匹配（如"薪酬"匹配"薪酬信息"）
        is_denied = False
        for deny_field in denied:
            if deny_field in key or key in deny_field:
                is_denied = True
                break
        if not is_denied:
            filtered[key] = value
    return filtered


def filter_records_by_scope(records: list, roles: list, user_info: dict) -> list:
    """
    根据用户角色的范围限制过滤记录。
    支持三种scope_level：
    - company: 不过滤，返回全部
    - per_role: 按user_roles中每条记录的org做范围匹配，取并集
    - center/department: 旧式兼容，从用户department推断
    
    roles: 可以是字符串列表 ["总监", "经理"] 
           或字典列表 [{"role":"总监","org":"长春研发中心","org_level":"center"}, ...]
    """
    # 分离角色名和角色详情
    role_names = []
    role_details = []  # 含org信息的角色列表
    for r in roles:
        if isinstance(r, dict):
            role_names.append(r.get("role", ""))
            role_details.append(r)
        else:
            role_names.append(r)

    # 1. 检查是否有company级别角色（直接放行）
    for rn in role_names:
        perms = ROLE_PERMISSIONS.get(rn, {})
        level = perms.get("scope_level", "none")
        if level == "company":
            return records

    # 2. 收集所有可见组织名称（per_role模式的并集）
    visible_orgs = set()
    has_per_role = False
    for rd in role_details:
        rn = rd.get("role", "")
        perms = ROLE_PERMISSIONS.get(rn, {})
        level = perms.get("scope_level", "none")
        org = rd.get("org", "")
        if level == "per_role" and org:
            has_per_role = True
            visible_orgs.add(org)

    # 如果有per_role角色且收集到了org，按org过滤
    if has_per_role and visible_orgs:
        filtered = []
        for record in records:
            record_dept = str(record.get("部门", record.get("department", ""))) or ""
            record_center = str(record.get("中心", record.get("center", ""))) or ""
            # 检查记录的部门或中心是否在可见组织集合中
            for org in visible_orgs:
                if org in record_dept or org in record_center or record_dept in org or record_center in org:
                    filtered.append(record)
                    break
        return filtered

    # 3. 兼容旧式center/department范围
    max_scope = "none"
    for rn in role_names:
        perms = ROLE_PERMISSIONS.get(rn, {})
        level = perms.get("scope_level", "none")
        if level == "center" and max_scope not in ("company",):
            max_scope = "center"
        elif level == "department" and max_scope not in ("company", "center"):
            max_scope = "department"

    if max_scope == "none":
        return records

    user_dept = user_info.get("department", "") or ""

    filtered = []
    for record in records:
        record_dept = str(record.get("部门", record.get("department", ""))) or ""
        record_center = str(record.get("中心", record.get("center", ""))) or ""

        if max_scope == "center":
            user_center = _extract_center(user_dept)
            if user_center and (user_center in record_dept or user_center in record_center or record_center in user_center):
                filtered.append(record)
            elif not user_center:
                filtered.append(record)
        elif max_scope == "department":
            if user_dept and (user_dept in record_dept or record_dept in user_dept):
                filtered.append(record)
            elif not user_dept:
                filtered.append(record)

    return filtered


def _extract_center(department: str) -> str:
    """
    从部门名中提取中心名称。
    例如：'制造一中心生产部' -> '制造一中心'
    """
    import re
    match = re.search(r'([\u4e00-\u9fff]+中心)', department)
    return match.group(1) if match else ""


def check_data_access(user_info: dict, records: list) -> list:
    """
    统一的数据访问控制入口。
    1. 根据角色范围过滤记录（scope filtering）
    2. 根据角色字段权限过滤字段（field filtering）
    3. 写审计日志
    
    Args:
        user_info: 当前用户信息，包含 role/roles/department 等
        records: 查询到的原始记录列表
    
    Returns:
        过滤后的记录列表
    """
    roles = user_info.get("roles", [])
    if not roles:
        # 兼容单角色场景
        single_role = user_info.get("role", "")
        roles = [single_role] if single_role else []

    # 1. 范围过滤
    scoped_records = filter_records_by_scope(records, roles, user_info)

    # 2. 字段过滤
    filtered_records = [filter_record_by_permissions(r, roles) for r in scoped_records]

    # 3. 审计日志
    log_data_access(
        actor=user_info.get("display_name", user_info.get("username", "unknown")),
        roles=roles,
        action="query",
        target=f"records:{len(records)}→{len(filtered_records)}",
        details=f"原始{len(records)}条，范围过滤后{len(filtered_records)}条",
    )

    return filtered_records


def log_data_access(actor: str, roles: list, action: str, target: str, details: str = ""):
    """
    数据访问审计日志。
    记录谁在什么时候用什么角色访问了什么数据。
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                roles TEXT,
                target TEXT NOT NULL,
                details TEXT,
                ip_address TEXT
            )
        """)
        cursor.execute(
            "INSERT INTO audit_log (action, actor, roles, target, details) VALUES (?, ?, ?, ?, ?)",
            (action, actor, ",".join(roles), target, details),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[审计日志] 写入失败: {e}")


def log_audit(action: str, actor: str, target: str, details: str = ""):
    """
    审计日志（兼容旧接口）
    """
    log_data_access(actor=actor, roles=[], action=action, target=target, details=details)
