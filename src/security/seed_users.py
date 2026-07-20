"""
初始化默认用户数据

数据来源：src/config/users.json（修改JSON即可增删用户/调整角色，无需改代码）

包含：
1. 管理层用户：总经理/副总/总监/经理/HRBP
2. SSC操作层用户：学科经理/工程师/主管/专员
3. 兼岗配置（role_assignments）
"""
import json
from pathlib import Path

from src.security.auth import (
    init_auth_db, register_user, create_default_admin,
    list_users, add_user_role,
)

# 用户配置文件路径
USERS_CONFIG_PATH = Path(__file__).parent.parent / "config" / "users.json"


def load_users_config() -> dict:
    """加载用户配置文件"""
    if not USERS_CONFIG_PATH.exists():
        raise FileNotFoundError(f"用户配置文件不存在: {USERS_CONFIG_PATH}")
    with open(USERS_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def seed_default_users():
    """创建所有默认用户（从users.json读取配置）"""
    config = load_users_config()

    # 初始化数据库
    init_auth_db()
    create_default_admin()

    created = 0

    # ==================== 管理层用户 ====================
    for user in config.get("management_users", []):
        result = register_user(**user)
        if result["success"]:
            created += 1
            print(f"  [管理层] 已创建: {user['username']} ({user['display_name']} - {user['role']})")
        else:
            print(f"  [管理层] 跳过: {user['username']} - {result['message']}")

    # ==================== SSC操作层用户 ====================
    for user in config.get("ssc_users", []):
        result = register_user(**user)
        if result["success"]:
            created += 1
            print(f"  [SSC操作层] 已创建: {user['username']} ({user['display_name']} - {user['role']})")
        else:
            print(f"  [SSC操作层] 跳过: {user['username']} - {result['message']}")

    # ==================== 兼岗配置（最后执行，确保所有用户已创建） ====================
    assignments = config.get("role_assignments", [])
    if assignments:
        print(f"\n  [兼岗配置] 开始配置 {len(assignments)} 条兼岗记录...")
        for a in assignments:
            username = a["username"]
            role = a["role"]
            org = a.get("org", "")
            org_level = a.get("org_level", "")
            result = add_user_role(username, role, org, org_level)
            if result["success"]:
                print(f"  {username}: {role}@{org or '全局'}")
            else:
                print(f"  {username}: 兼岗失败 - {result['message']}")

    total = len(list_users())
    print(f"\n[种子数据] 完成：新创建 {created} 个用户，共 {total} 个用户")
    return created


if __name__ == "__main__":
    seed_default_users()