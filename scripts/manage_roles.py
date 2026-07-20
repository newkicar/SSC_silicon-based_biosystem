"""兼岗双向管理脚本

导出：从数据库读取所有兼岗配置，生成 Excel 文件
导入：读取修改后的 Excel 文件，同步回数据库

用法:
  # 导出当前兼岗配置
  python scripts/manage_roles.py export

  # 导入兼岗配置（会先清空现有兼岗，再重新导入）
  python scripts/manage_roles.py import <配置文件.xlsx>

输出文件:
  scripts/roles_export.xlsx - 兼岗配置导出文件
"""

import sys
import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "auth.db"
OUTPUT_FILE = Path(__file__).parent / "roles_export.xlsx"


def export_roles():
    """导出所有兼岗配置到 Excel"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            u.username,
            u.display_name,
            u.role as primary_role,
            u.department,
            ur.role,
            ur.org,
            ur.org_level,
            ur.notification_scope
        FROM users u
        JOIN user_roles ur ON u.id = ur.user_id
        WHERE u.status = 'active'
          AND ur.role IN ('总经理', '副总经理', '总监', '经理', 'HRBP')
          AND ur.org != ''
        ORDER BY u.username, ur.org
    """)

    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("没有找到兼岗记录")
        return

    data = []
    for row in rows:
        data.append(
            {
                "工号": row["username"],
                "姓名": row["display_name"],
                "主角色": row["primary_role"],
                "部门": row["department"] or "",
                "兼岗角色": row["role"],
                "兼岗组织": row["org"] or "",
                "兼岗级别": row["org_level"] or "",
                "notification_scope": row["notification_scope"] or "",
            }
        )

    df = pd.DataFrame(data)
    df.to_excel(str(OUTPUT_FILE), index=False, sheet_name="兼岗配置")
    print(f"已导出 {len(data)} 条兼岗记录到 {OUTPUT_FILE}")


def import_roles(excel_file: str):
    """从 Excel 导入兼岗配置"""
    if not Path(excel_file).exists():
        print(f"错误: 文件不存在: {excel_file}")
        sys.exit(1)

    df = pd.read_excel(excel_file, sheet_name="兼岗配置")
    print(f"读取到 {len(df)} 行兼岗配置")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 先清空所有兼岗记录
    cur.execute(
        "DELETE FROM user_roles WHERE role IN ('总经理', '副总经理', '总监', '经理', 'HRBP')"
    )
    deleted = cur.rowcount
    print(f"已清除 {deleted} 条旧兼岗记录")

    added = 0
    for _, row in df.iterrows():
        username = str(row["工号"]).strip()
        role = str(row["兼岗角色"]).strip()
        org = str(row["兼岗组织"]).strip()
        org_level = str(row["兼岗级别"]).strip()
        notification_scope = (
            str(row.get("notification_scope", "")).strip()
            if pd.notna(row.get("notification_scope", ""))
            else ""
        )

        if not username or not role or not org or not org_level:
            continue

        # 获取用户 ID
        cur.execute("SELECT id FROM users WHERE username = ?", (username,))
        user_row = cur.fetchone()
        if not user_row:
            print(f"  警告: 用户 {username} 不存在，跳过")
            continue

        user_id = user_row["id"]

        # 插入兼岗记录
        cur.execute(
            "INSERT INTO user_roles (user_id, role, org, org_level, notification_scope) VALUES (?, ?, ?, ?, ?)",
            (user_id, role, org, org_level, notification_scope),
        )
        added += 1
        print(f"  添加: {username} - {role}@{org} ({org_level})")

    conn.commit()
    conn.close()
    print(f"导入完成: 新增 {added} 条兼岗记录")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python scripts/manage_roles.py export          # 导出兼岗配置")
        print("  python scripts/manage_roles.py import <file>   # 导入兼岗配置")
        sys.exit(1)

    command = sys.argv[1].lower()
    if command == "export":
        export_roles()
    elif command == "import":
        if len(sys.argv) < 3:
            print("错误: 请提供 Excel 文件路径")
            sys.exit(1)
        import_roles(sys.argv[2])
    else:
        print(f"错误: 未知命令 {command}")
        sys.exit(1)
