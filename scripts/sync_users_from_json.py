"""
临时脚本：将 users.json 中的 ssc_users 信息同步到数据库
用于更新 role、display_name、specialization 等字段（不修改密码）

用法：python scripts/sync_users_from_json.py
"""
import sys
import os
import json
import sqlite3
from pathlib import Path

# 添加项目根目录到 path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def sync_users():
    users_json_path = Path(project_root) / "src" / "config" / "users.json"
    db_path = Path(project_root) / "data" / "auth.db"

    if not users_json_path.exists():
        print(f"❌ users.json 不存在: {users_json_path}")
        return
    if not db_path.exists():
        print(f"❌ 数据库不存在: {db_path}")
        return

    with open(users_json_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    updated = 0
    not_found = 0

    # 同步 ssc_users
    for user in config.get("ssc_users", []):
        username = user.get("username", "")
        display_name = user.get("display_name", "")
        role = user.get("role", "")
        specialization = user.get("specialization", "")
        company = user.get("company", "")
        department = user.get("department", "")

        cursor.execute(
            "UPDATE users SET display_name=?, role=?, specialization=?, company=?, department=? WHERE username=?",
            (display_name, role, specialization, company, department, username)
        )
        if cursor.rowcount > 0:
            updated += 1
            print(f"  ✅ {username} ({display_name}) {role} - specialization 已更新")
        else:
            not_found += 1
            print(f"  ⚠️ {username} ({display_name}) 未在数据库中找到，跳过")

    # 同步 management_users
    for user in config.get("management_users", []):
        username = user.get("username", "")
        display_name = user.get("display_name", "")
        role = user.get("role", "")
        company = user.get("company", "")
        department = user.get("department", "")

        cursor.execute(
            "UPDATE users SET display_name=?, role=?, company=?, department=? WHERE username=?",
            (display_name, role, company, department, username)
        )
        if cursor.rowcount > 0:
            updated += 1
            print(f"  ✅ {username} ({display_name}) {role}")
        else:
            not_found += 1

    conn.commit()
    conn.close()

    print(f"\n同步完成: {updated} 条更新, {not_found} 条未找到")


if __name__ == "__main__":
    sync_users()