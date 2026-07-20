"""
Skill Registry（技能注册中心）—— 服务端技能管理数据库

功能：
- 管理所有已上传的 Skill（元数据 + zip包存储）
- 提供版本管理、角色分配、启停控制
- 支持 CLI 端检查更新

表结构：
  skills_registry  — 技能元数据表
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = str(Path(__file__).resolve().parent.parent.parent / "data" / "auth.db")
SKILL_PACKAGES_DIR = str(Path(__file__).resolve().parent.parent.parent / "data" / "skill_packages")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_skill_registry():
    """初始化技能注册中心表和存储目录"""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skills_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name TEXT UNIQUE NOT NULL,
            display_name TEXT DEFAULT '',
            description TEXT DEFAULT '',
            version TEXT DEFAULT '1.0.0',
            target_roles TEXT DEFAULT '[]',
            status TEXT DEFAULT 'active',
            file_list TEXT DEFAULT '[]',
            zip_path TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    
    # 确保存储目录存在
    Path(SKILL_PACKAGES_DIR).mkdir(parents=True, exist_ok=True)
    print(f"[Skill Registry] 数据库表已初始化，存储目录: {SKILL_PACKAGES_DIR}")


def register_skill(skill_data: dict) -> dict:
    """
    注册一个新 Skill（或更新已有的）
    
    skill_data = {
        "skill_name": "outlook-controller",
        "display_name": "Outlook邮件控制器",
        "description": "控制Outlook读取和发送邮件",
        "version": "1.0.0",
        "target_roles": ["人事专员", "SSC主管"],
        "file_list": ["SKILL.md", "scripts/read.py", "scripts/send.py"],
        "zip_path": "data/skill_packages/outlook-controller.zip",
        "created_by": "admin",
    }
    """
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    skill_name = skill_data.get("skill_name", "")
    if not skill_name:
        return {"success": False, "message": "skill_name 不能为空"}
    
    # 检查是否已存在
    cursor.execute("SELECT id FROM skills_registry WHERE skill_name = ?", (skill_name,))
    existing = cursor.fetchone()
    
    target_roles = skill_data.get("target_roles", [])
    if isinstance(target_roles, list):
        target_roles_json = json.dumps(target_roles, ensure_ascii=False)
    elif isinstance(target_roles, str):
        # 尝试 JSON 解析，失败则按逗号分隔
        try:
            parsed = json.loads(target_roles)
            if isinstance(parsed, list):
                target_roles_json = json.dumps(parsed, ensure_ascii=False)
            else:
                target_roles_json = json.dumps([target_roles], ensure_ascii=False)
        except (json.JSONDecodeError, ValueError):
            # 逗号分隔字符串 → 列表
            roles = [r.strip() for r in target_roles.split(",") if r.strip()]
            target_roles_json = json.dumps(roles, ensure_ascii=False)
    else:
        target_roles_json = json.dumps([str(target_roles)], ensure_ascii=False)
    
    file_list = skill_data.get("file_list", [])
    if isinstance(file_list, list):
        file_list_json = json.dumps(file_list, ensure_ascii=False)
    else:
        file_list_json = str(file_list)
    
    if existing:
        # 更新
        cursor.execute("""
            UPDATE skills_registry SET
                display_name = ?, description = ?, version = ?,
                target_roles = ?, file_list = ?, zip_path = ?,
                updated_at = ?
            WHERE skill_name = ?
        """, (
            skill_data.get("display_name", ""),
            skill_data.get("description", ""),
            skill_data.get("version", "1.0.0"),
            target_roles_json,
            file_list_json,
            skill_data.get("zip_path", ""),
            now,
            skill_name,
        ))
        action = "updated"
    else:
        # 新增
        cursor.execute("""
            INSERT INTO skills_registry 
            (skill_name, display_name, description, version, target_roles, status,
             file_list, zip_path, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
        """, (
            skill_name,
            skill_data.get("display_name", ""),
            skill_data.get("description", ""),
            skill_data.get("version", "1.0.0"),
            target_roles_json,
            file_list_json,
            skill_data.get("zip_path", ""),
            skill_data.get("created_by", "admin"),
            now, now,
        ))
        action = "created"
    
    conn.commit()
    conn.close()
    
    return {"success": True, "action": action, "skill_name": skill_name}


def get_all_skills() -> list:
    """获取所有已注册的 Skill"""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM skills_registry ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        skill = dict(row)
        skill['target_roles'] = json.loads(skill.get('target_roles', '[]'))
        skill['file_list'] = json.loads(skill.get('file_list', '[]'))
        result.append(skill)
    return result


def get_skill_by_name(skill_name: str) -> dict:
    """获取单个 Skill 详情"""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM skills_registry WHERE skill_name = ?", (skill_name,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    skill = dict(row)
    skill['target_roles'] = json.loads(skill.get('target_roles', '[]'))
    skill['file_list'] = json.loads(skill.get('file_list', '[]'))
    return skill


def update_skill_status(skill_name: str, status: str) -> dict:
    """更新 Skill 状态（active / disabled）"""
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute("""
        UPDATE skills_registry SET status = ?, updated_at = ?
        WHERE skill_name = ?
    """, (status, now, skill_name))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return {"success": affected > 0, "skill_name": skill_name, "status": status}


def update_skill_roles(skill_name: str, target_roles: list) -> dict:
    """更新 Skill 的目标角色"""
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute("""
        UPDATE skills_registry SET target_roles = ?, updated_at = ?
        WHERE skill_name = ?
    """, (json.dumps(target_roles, ensure_ascii=False), now, skill_name))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return {"success": affected > 0, "skill_name": skill_name}


def delete_skill(skill_name: str) -> dict:
    """删除 Skill 记录和 zip 包"""
    skill = get_skill_by_name(skill_name)
    if not skill:
        return {"success": False, "message": f"Skill '{skill_name}' 不存在"}
    
    # 删除 zip 文件
    zip_path = skill.get("zip_path", "")
    if zip_path:
        zip_file = Path(zip_path)
        if zip_file.exists():
            zip_file.unlink()
    
    # 删除数据库记录
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM skills_registry WHERE skill_name = ?", (skill_name,))
    conn.commit()
    conn.close()
    
    return {"success": True, "skill_name": skill_name, "action": "deleted"}


def get_skills_for_role(role_name: str) -> list:
    """获取某个角色可用的所有活跃 Skill"""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM skills_registry WHERE status = 'active'")
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        skill = dict(row)
        target_roles = json.loads(skill.get('target_roles', '[]'))
        if role_name in target_roles:
            skill['target_roles'] = target_roles
            skill['file_list'] = json.loads(skill.get('file_list', '[]'))
            result.append(skill)
    return result


def get_all_active_skills_summary() -> list:
    """获取所有活跃 Skill 的摘要（供 CLI 检查更新使用）"""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT skill_name, display_name, description, version, target_roles, status, updated_at FROM skills_registry WHERE status = 'active'")
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        skill = dict(row)
        skill['target_roles'] = json.loads(skill.get('target_roles', '[]'))
        result.append(skill)
    return result


def check_updates(local_versions: dict) -> dict:
    """
    CLI 检查 Skill 更新
    
    local_versions: {"outlook-controller": "1.0.0", "employment-certificate": "1.0.0"}
    
    返回：
    {
        "update": [{"skill_name": "...", "version": "...", "action": "update"}],
        "new": [{"skill_name": "...", "version": "...", "action": "new"}],
        "delete": [{"skill_name": "...", "reason": "已禁用"}],
    }
    """
    all_active = get_all_active_skills_summary()
    active_names = {s['skill_name'] for s in all_active}
    
    result = {"update": [], "new": [], "delete": []}
    
    # 检查活跃的 skill
    for skill in all_active:
        name = skill['skill_name']
        server_version = skill['version']
        
        if name in local_versions:
            local_version = local_versions[name]
            if local_version != server_version:
                result["update"].append({
                    "skill_name": name,
                    "version": server_version,
                    "display_name": skill['display_name'],
                    "action": "update",
                })
        else:
            result["new"].append({
                "skill_name": name,
                "version": server_version,
                "display_name": skill['display_name'],
                "action": "new",
            })
    
    # 检查本地有但服务端已禁用/删除的
    for local_name in local_versions:
        if local_name not in active_names:
            # 检查是否存在但被禁用
            skill = get_skill_by_name(local_name)
            if skill and skill['status'] == 'disabled':
                result["delete"].append({
                    "skill_name": local_name,
                    "reason": "已被管理员禁用",
                })
            elif not skill:
                result["delete"].append({
                    "skill_name": local_name,
                    "reason": "已被管理员删除",
                })
    
    return result