"""
用户认证与权限管理系统

数据库结构：
- users表：用户名、密码哈希、身份、状态
- 角色与权限的关联通过permissions.py的RBAC实现

功能：
- 用户注册/登录（密码bcrypt哈希）
- 身份管理（与RBAC角色关联）
- 登录会话管理（JWT token）
"""

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from src.config.settings import DATA_DIR

# 认证数据库路径
AUTH_DB_PATH = DATA_DIR / "auth.db"


def _get_auth_connection() -> sqlite3.Connection:
    """获取认证数据库连接"""
    conn = sqlite3.connect(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_auth_db():
    """初始化认证数据库"""
    conn = _get_auth_connection()
    cursor = conn.cursor()

    # 用户表（role字段保留主角色，兼容旧代码）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      VARCHAR(64) UNIQUE NOT NULL,
            password_hash VARCHAR(128) NOT NULL,
            salt          VARCHAR(32) NOT NULL,
            display_name  VARCHAR(64) NOT NULL,
            role          VARCHAR(32) NOT NULL,
            department    VARCHAR(64),
            center        VARCHAR(64),
            company       VARCHAR(32),
            channels      VARCHAR(32) DEFAULT 'web',
            employee_id   VARCHAR(32),
            status        VARCHAR(16) DEFAULT 'active',
            created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_login    DATETIME
        )
    """)

    # 兼岗角色表（一人多角色，含组织范围）
    # 注意：UNIQUE约束为(user_id, role, org)，允许同一角色不同组织
    # 如果旧表存在（约束为user_id, role），先备份数据再重建
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='user_roles'"
    )
    old_table_exists = cursor.fetchone() is not None
    if old_table_exists:
        try:
            # 检查旧表是否有org字段
            try:
                cursor.execute("SELECT org FROM user_roles LIMIT 1")
                has_org = True
            except sqlite3.OperationalError:
                has_org = False

            if has_org:
                # 旧表已有org字段，检查UNIQUE约束是否需要更新
                # 查询sqlite_master看约束是否已经是(user_id, role, org)
                cursor.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='user_roles'"
                )
                table_sql = cursor.fetchone()
                if table_sql and "user_id, role, org" in (table_sql[0] or ""):
                    # 约束已是最新的，无需重建
                    old_data = []
                else:
                    cursor.execute("SELECT * FROM user_roles")
                    old_data = cursor.fetchall()
                    cursor.execute("DROP TABLE user_roles")
                    print("[认证系统] 正在重建 user_roles 表（更新UNIQUE约束）...")
            else:
                # 旧表没有org字段
                cursor.execute("SELECT id, user_id, role FROM user_roles")
                old_data = [dict(row) for row in cursor.fetchall()]
                cursor.execute("DROP TABLE user_roles")
                print("[认证系统] 正在重建 user_roles 表（添加org字段+更新约束）...")
        except sqlite3.OperationalError:
            # 多Worker竞争：表已被其他worker删除，跳过迁移
            old_data = []
            print("[认证系统] user_roles 表已被其他进程重建，跳过迁移")
    else:
        old_data = []

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER NOT NULL,
            role      VARCHAR(32) NOT NULL,
            org       VARCHAR(64) DEFAULT '',
            org_level VARCHAR(16) DEFAULT '',
            UNIQUE(user_id, role, org),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 恢复旧数据（如果有的话）
    if old_data:
        migrated = 0
        for row in old_data:
            try:
                r = dict(row) if not isinstance(row, dict) else row
                uid = r.get("user_id", r.get("id"))
                role = r.get("role", "")
                org = r.get("org", "")
                org_level = r.get("org_level", "")
                if uid and role:
                    cursor.execute(
                        "INSERT OR IGNORE INTO user_roles (user_id, role, org, org_level) VALUES (?, ?, ?, ?)",
                        (uid, role, org, org_level),
                    )
                    migrated += 1
            except Exception:
                pass
        print(f"[认证系统] 已迁移 {migrated} 条旧角色数据")

    # 兼容旧表：如果users表没有company字段，自动添加
    try:
        cursor.execute("SELECT company FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE users ADD COLUMN company VARCHAR(32)")
        print("[认证系统] 已为 users 表添加 company 字段")

    # 兼容旧表：如果users表没有channels字段，自动添加
    try:
        cursor.execute("SELECT channels FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN channels VARCHAR(32) DEFAULT 'web'"
        )
        print("[认证系统] 已为 users 表添加 channels 字段")

    # 兼容旧表：如果users表没有specialization字段，自动添加
    try:
        cursor.execute("SELECT specialization FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE users ADD COLUMN specialization TEXT DEFAULT ''")
        print("[认证系统] 已为 users 表添加 specialization 字段")

    # 登录会话表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token       VARCHAR(128) PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at  DATETIME NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 审计日志表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auth_audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            username    VARCHAR(64),
            action      VARCHAR(32) NOT NULL,
            detail      TEXT,
            ip_address  VARCHAR(45),
            created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 角色-部门映射表（用于工单分派时的角色规范化）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS role_departments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            role_name   VARCHAR(64) UNIQUE NOT NULL,
            department  VARCHAR(64) NOT NULL,
            assignee_code VARCHAR(32),
            created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 初始化默认角色-部门映射（如果表为空）
    cursor.execute("SELECT COUNT(*) FROM role_departments")
    if cursor.fetchone()[0] == 0:
        default_mappings = [
            ("员工关系专员", "DEPT_EMPLOYEE_RELATIONS", "guanxi_spec"),
            ("员工关系主管", "DEPT_EMPLOYEE_RELATIONS", "guanxi_mgr"),
            ("薪酬专员", "DEPT_PAYROLL", "xinchou_spec"),
            ("薪酬主管", "DEPT_PAYROLL", "xinchou_mgr"),
            ("考勤专员", "DEPT_ATTENDANCE", "kaoqin_spec"),
            ("招聘专员", "DEPT_RECRUITMENT", "zhaopin_spec"),
            ("招聘主管", "DEPT_RECRUITMENT", "zhaopin_mgr"),
            ("HRIS工程师", "DEPT_HRIS", "hris_eng"),
            ("HR_SSC经理", "DEPT_MANAGEMENT", "ssc_mgr"),
        ]
        cursor.executemany(
            """INSERT INTO role_departments (role_name, department, assignee_code)
               VALUES (?, ?, ?)""",
            default_mappings,
        )
        print("[认证系统] 已初始化角色-部门映射表")

    conn.commit()
    conn.close()


def _hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """密码哈希（SHA256 + salt）"""
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return hashed, salt


def register_user(
    username: str,
    password: str,
    display_name: str,
    role: str,
    department: str = None,
    employee_id: str = None,
    company: str = None,
    channels: str = "web",
    specialization: str = None,
) -> dict:
    """
    注册新用户。

    Args:
        username: 登录用户名（通常为工号）
        password: 明文密码（内部自动哈希）
        display_name: 显示名称
        role: 主角色（对应RBAC：总经理/总监/经理/HRBP/HR_SSC经理等）
        department: 所属部门
        employee_id: 员工工号
        company: 所属公司（虚拟公司A/虚拟公司B）
        channels: 允许的登录渠道，逗号分隔（"web" / "web,cli"）
        specialization: 岗位职责描述，用于工单智能分派

    Returns:
        {"success": bool, "message": str, "user_id": int}
    """
    # 验证角色合法性
    valid_roles = _get_valid_roles()
    if role not in valid_roles:
        return {"success": False, "message": f"无效角色: {role}，可选: {valid_roles}"}

    conn = _get_auth_connection()
    cursor = conn.cursor()

    # 检查用户名是否已存在
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return {"success": False, "message": f"用户名 '{username}' 已存在"}

    # 哈希密码
    password_hash, salt = _hash_password(password)

    # 插入用户
    cursor.execute(
        """INSERT INTO users (username, password_hash, salt, display_name, role, department, employee_id, company, channels, specialization)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            username,
            password_hash,
            salt,
            display_name,
            role,
            department,
            employee_id,
            company,
            channels,
            specialization or "",
        ),
    )
    user_id = cursor.lastrowid

    # 同时写入兼岗角色表（主角色自动加入，无组织范围）
    cursor.execute(
        "INSERT INTO user_roles (user_id, role, org, org_level) VALUES (?, ?, '', '')",
        (user_id, role),
    )
    conn.commit()

    # 审计日志
    cursor.execute(
        "INSERT INTO auth_audit_log (user_id, username, action, detail) VALUES (?, ?, ?, ?)",
        (user_id, username, "register", f"新用户注册: {display_name}, 角色: {role}"),
    )
    conn.commit()
    conn.close()

    return {"success": True, "message": "注册成功", "user_id": user_id}


def login(username: str, password: str) -> dict:
    """
    用户登录。

    Returns:
        {"success": bool, "token": str, "user": dict, "message": str}
    """
    conn = _get_auth_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE username = ? AND status = 'active'", (username,)
    )
    user = cursor.fetchone()

    if not user:
        conn.close()
        return {"success": False, "message": "用户名或密码错误"}

    user = dict(user)

    # 验证密码
    password_hash, _ = _hash_password(password, user["salt"])
    if password_hash != user["password_hash"]:
        conn.close()
        return {"success": False, "message": "用户名或密码错误"}

    # 生成会话token
    token = secrets.token_hex(32)
    expires_at = (datetime.now() + timedelta(hours=8)).isoformat()

    cursor.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user["id"], expires_at),
    )

    # 更新最后登录时间
    cursor.execute(
        "UPDATE users SET last_login = ? WHERE id = ?",
        (datetime.now().isoformat(), user["id"]),
    )

    # 审计日志
    cursor.execute(
        "INSERT INTO auth_audit_log (user_id, username, action) VALUES (?, ?, ?)",
        (user["id"], username, "login"),
    )
    conn.commit()
    conn.close()

    # 获取用户所有角色（含兼岗及组织）
    all_roles = get_user_roles(user["id"])
    role_names = [r["role"] if isinstance(r, dict) else r for r in all_roles]

    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
            "roles": role_names,
            "role_details": all_roles,
            "department": user["department"],
            "company": user.get("company", ""),
            "channels": user.get("channels", "web"),
            "employee_id": user["employee_id"],
        },
        "message": "登录成功",
    }


def verify_token(token: str) -> dict:
    """
    验证会话token。

    Returns:
        {"valid": bool, "user": dict} or {"valid": bool}
    """
    if not token:
        return {"valid": False}

    conn = _get_auth_connection()
    cursor = conn.cursor()

    cursor.execute(
        """SELECT s.*, u.username, u.display_name, u.role, u.department, u.employee_id, u.status
           FROM sessions s JOIN users u ON s.user_id = u.id
           WHERE s.token = ? AND s.expires_at > ? AND u.status = 'active'""",
        (token, datetime.now().isoformat()),
    )
    session = cursor.fetchone()
    conn.close()

    if not session:
        return {"valid": False}

    # 获取用户所有角色（含兼岗及组织）
    all_roles = get_user_roles(session["user_id"])
    role_names = [r["role"] if isinstance(r, dict) else r for r in all_roles]

    # 获取company字段
    try:
        company = session["company"] if "company" in session.keys() else ""
    except (KeyError, IndexError):
        company = ""

    return {
        "valid": True,
        "user": {
            "id": session["user_id"],
            "username": session["username"],
            "display_name": session["display_name"],
            "role": session["role"],
            "roles": role_names,
            "role_details": all_roles,
            "department": session["department"],
            "company": company,
            "employee_id": session["employee_id"],
        },
    }


def logout(token: str) -> dict:
    """用户登出"""
    conn = _get_auth_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "已登出"}


def list_users() -> list[dict]:
    """列出所有用户（含兼岗组织信息）

    返回的用户字典额外包含 org 和 org_level 字段，
    来源于 user_roles 表（取该用户的第一个兼岗记录；
    若无兼岗则返回空字符串）。
    """
    conn = _get_auth_connection()
    cursor = conn.cursor()

    # 先查所有兼岗记录
    cursor.execute("""
        SELECT user_id, role, org, org_level
        FROM user_roles
        ORDER BY user_id, id
    """)
    # 按 user_id 聚合，取第一条（优先有 org 的记录）
    role_map: dict[int, dict] = {}
    for row in cursor.fetchall():
        uid = row["user_id"]
        if uid not in role_map:
            role_map[uid] = {
                "role": row["role"],
                "org": row["org"] or "",
                "org_level": row["org_level"] or "",
            }
        elif row["org"] and not role_map[uid]["org"]:
            # 之前是空 org，现在有值则替换
            role_map[uid] = {
                "role": row["role"],
                "org": row["org"] or "",
                "org_level": row["org_level"] or "",
            }

    # 再查用户主表
    cursor.execute(
        "SELECT id, username, display_name, role, department, employee_id, "
        "status, created_at, last_login, specialization FROM users ORDER BY id"
    )
    users = []
    for row in cursor.fetchall():
        u = dict(row)
        uid = u["id"]
        if uid in role_map:
            u["org"] = role_map[uid]["org"]
            u["org_level"] = role_map[uid]["org_level"]
            # 如果有兼岗的 role，优先用兼岗的 role
            if role_map[uid]["role"] and role_map[uid]["role"] != u["role"]:
                u["primary_role"] = u["role"]
                u["role"] = role_map[uid]["role"]
        else:
            u["org"] = ""
            u["org_level"] = ""
        users.append(u)

    conn.close()
    return users


def update_user_role(username: str, new_role: str) -> dict:
    """更新用户主角色"""
    valid_roles = _get_valid_roles()
    if new_role not in valid_roles:
        return {
            "success": False,
            "message": f"无效角色: {new_role}，可选: {valid_roles}",
        }

    conn = _get_auth_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = ? WHERE username = ?", (new_role, username))
    if cursor.rowcount == 0:
        conn.close()
        return {"success": False, "message": f"用户 '{username}' 不存在"}
    conn.commit()
    conn.close()
    return {"success": True, "message": f"用户 '{username}' 角色已更新为 {new_role}"}


def delete_user(username: str) -> dict:
    """软删除用户（设置status为inactive）"""
    conn = _get_auth_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET status = 'inactive' WHERE username = ?", (username,)
    )
    if cursor.rowcount == 0:
        conn.close()
        return {"success": False, "message": f"用户 '{username}' 不存在"}
    # 同时清除会话
    cursor.execute(
        "DELETE FROM sessions WHERE user_id = (SELECT id FROM users WHERE username = ?)",
        (username,),
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": f"用户 '{username}' 已禁用"}


def get_user_by_username(username: str) -> dict | None:
    """按用户名查询用户"""
    conn = _get_auth_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, display_name, role, department, employee_id, status FROM users WHERE username = ?",
        (username,),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def _get_valid_roles() -> list:
    """获取所有合法角色列表（从permissions.py的ROLE_PERMISSIONS动态获取）"""
    from src.security.permissions import ROLE_PERMISSIONS

    return list(ROLE_PERMISSIONS.keys())


def get_user_roles(user_id: int) -> list:
    """
    获取用户的所有角色（含兼岗及组织范围）。
    返回角色详情列表，如:
    [
        {"role": "HRBP", "org": "长春研发中心", "org_level": "center"},
        {"role": "HRBP", "org": "德系业务中心", "org_level": "center"},
    ]
    """
    conn = _get_auth_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, org, org_level FROM user_roles WHERE user_id = ?", (user_id,)
    )
    roles = [dict(row) for row in cursor.fetchall()]
    conn.close()
    # 如果兼岗表为空，回退到users表的主角色
    if not roles:
        conn = _get_auth_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            roles = [{"role": row["role"], "org": "", "org_level": ""}]
    return roles


def get_user_role_names(user_id: int) -> list:
    """
    获取用户的所有角色名称列表（纯字符串，兼容旧接口）。
    返回如 ["招聘主管", "员工关系主管"]
    """
    roles = get_user_roles(user_id)
    return [r["role"] for r in roles]


def add_user_role(username: str, role: str, org: str = "", org_level: str = "") -> dict:
    """
    为用户添加兼岗角色。

    Args:
        username: 用户名（工号）
        role: 角色名
        org: 对应组织名称（如"长春研发中心"、"德系业务中心"、"预装部"）
        org_level: 组织层级（company/center/department）

    示例：
        add_user_role("110272", "HRBP", "长春研发中心", "center")
    """
    valid_roles = _get_valid_roles()
    if role not in valid_roles:
        return {"success": False, "message": f"无效角色: {role}，可选: {valid_roles}"}

    conn = _get_auth_connection()
    cursor = conn.cursor()

    # 查找用户
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return {"success": False, "message": f"用户 '{username}' 不存在"}

    user_id = user["id"]

    # 检查是否已有该角色+组织的组合
    cursor.execute(
        "SELECT id FROM user_roles WHERE user_id = ? AND role = ? AND org = ?",
        (user_id, role, org),
    )
    if cursor.fetchone():
        conn.close()
        return {
            "success": True,
            "message": f"用户 '{username}' 已拥有角色 {role}@{org or '全局'}",
        }

    # 添加兼岗
    cursor.execute(
        "INSERT INTO user_roles (user_id, role, org, org_level) VALUES (?, ?, ?, ?)",
        (user_id, role, org, org_level),
    )
    conn.commit()

    # 审计日志
    cursor.execute(
        "INSERT INTO auth_audit_log (user_id, username, action, detail) VALUES (?, ?, ?, ?)",
        (user_id, username, "add_role", f"添加兼岗角色: {role}@{org or '全局'}"),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"已为用户 '{username}' 添加角色 {role}@{org or '全局'}",
    }


def remove_user_role(username: str, role: str, org: str = "") -> dict:
    """
    移除用户的兼岗角色（不能移除主角色）。

    Args:
        username: 用户名
        role: 角色名
        org: 组织名称（可选，用于精确匹配同角色不同组织的兼岗）
    """
    conn = _get_auth_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, role FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return {"success": False, "message": f"用户 '{username}' 不存在"}

    # 不能移除主角色（当org为空时检查）
    if user["role"] == role and not org:
        conn.close()
        return {
            "success": False,
            "message": f"不能移除主角色 '{role}'，请先用 update_user_role 更换主角色",
        }

    if org:
        cursor.execute(
            "DELETE FROM user_roles WHERE user_id = ? AND role = ? AND org = ?",
            (user["id"], role, org),
        )
    else:
        cursor.execute(
            "DELETE FROM user_roles WHERE user_id = ? AND role = ?",
            (user["id"], role),
        )

    if cursor.rowcount == 0:
        conn.close()
        return {
            "success": True,
            "message": f"用户 '{username}' 没有角色 {role}@{org or '全局'}",
        }

    conn.commit()

    # 审计日志
    cursor.execute(
        "INSERT INTO auth_audit_log (user_id, username, action, detail) VALUES (?, ?, ?, ?)",
        (user["id"], username, "remove_role", f"移除兼岗角色: {role}@{org or '全局'}"),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"已移除用户 '{username}' 的角色 {role}@{org or '全局'}",
    }


def get_user_roles_by_username(username: str) -> list:
    """按用户名获取所有角色（返回详情列表）"""
    conn = _get_auth_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    if not user:
        return []
    return get_user_roles(user["id"])


def get_user_role_names_by_username(username: str) -> list:
    """按用户名获取所有角色名称（纯字符串，兼容旧接口）"""
    conn = _get_auth_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    if not user:
        return []
    return get_user_role_names(user["id"])


def get_all_ssc_specializations() -> list[dict]:
    """
    获取所有SSC操作层用户的岗位职责信息。
    供大脑在分派工单时参考，实现基于职责的精准分派。

    返回: [{"username": "110807", "display_name": "胡佳欣", "role": "员工关系专员", "specialization": "..."}, ...]
    """
    conn = _get_auth_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT username, display_name, role, specialization 
           FROM users 
           WHERE status = 'active' AND channels LIKE '%cli%' AND specialization != ''
           ORDER BY role, display_name""")
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def create_default_admin():
    """创建默认管理员账户（如果不存在）"""
    existing = get_user_by_username("admin")
    if not existing:
        result = register_user(
            username="admin",
            password="{{ADMIN_PASSWORD}}",
            display_name="系统管理员",
            role="HR_SSC经理",
            department="SSC",
        )
        if result["success"]:
            print("[认证系统] 已创建默认管理员账户: admin / {{ADMIN_PASSWORD}}")
        return result
    return {"success": True, "message": "管理员账户已存在"}


def get_role_department_mapping() -> dict:
    """
    从数据库读取角色-部门映射和角色-处理人编码映射。

    Returns:
        {
            "role_to_dept": {"员工关系专员": "DEPT_EMPLOYEE_RELATIONS", ...},
            "role_to_assignee": {"员工关系专员": "guanxi_spec", ...},
        }
    """
    conn = _get_auth_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role_name, department, assignee_code FROM role_departments")
    rows = cursor.fetchall()
    conn.close()

    role_to_dept = {}
    role_to_assignee = {}
    for row in rows:
        role_name = row["role_name"]
        role_to_dept[role_name] = row["department"]
        if row["assignee_code"]:
            role_to_assignee[role_name] = row["assignee_code"]

    return {
        "role_to_dept": role_to_dept,
        "role_to_assignee": role_to_assignee,
    }


def update_role_department(
    role_name: str, department: str, assignee_code: str = ""
) -> dict:
    """
    更新或新增角色-部门映射。

    Args:
        role_name: 角色名
        department: 部门标签
        assignee_code: 处理人编码（可选）
    """
    conn = _get_auth_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO role_departments (role_name, department, assignee_code)
           VALUES (?, ?, ?)
           ON CONFLICT(role_name) DO UPDATE SET department=excluded.department, assignee_code=excluded.assignee_code""",
        (role_name, department, assignee_code),
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": f"已更新角色映射: {role_name} -> {department}"}


def delete_role_department(role_name: str) -> dict:
    """删除角色-部门映射"""
    conn = _get_auth_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM role_departments WHERE role_name = ?", (role_name,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    if deleted == 0:
        return {"success": False, "message": f"角色 '{role_name}' 不存在"}
    return {"success": True, "message": f"已删除角色映射: {role_name}"}


def list_role_departments() -> list[dict]:
    """列出所有角色-部门映射"""
    conn = _get_auth_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role_name, department, assignee_code FROM role_departments ORDER BY id"
    )
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results
