"""清理测试数据脚本

备份数据库并清空测试产生的垃圾数据，保留用户配置和兼岗信息。

用法:
  python scripts/cleanup_test_data.py

清理内容:
  - 备份数据库到 data/backups/
  - 清空 conversations、task_bs、task_st、cli_tasks 表
  - 清空 notifications、notification_reads 表
  - 清空 tickets 表
  - 清空 chat_messages、chat_sessions 表
  - 清空 insight_notifications 表（洞察查重记录）
  - 清空 logs/ 目录
  - 清空 memories/ 目录（vibe coding 指导文件）

保留内容:
  - 用户数据（users、user_roles 表）
  - 兼岗配置
  - memory/ 目录（项目记忆文件）
  - 向量索引（可重新构建）
"""

import sqlite3
import shutil
import os
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
BACKUPS_DIR = DATA_DIR / "backups"
LOGS_DIR = PROJECT_ROOT / "logs"
MEMORIES_DIR = PROJECT_ROOT / "memories"

SSC_MEMORY_DB = DATA_DIR / "ssc_memory.db"
AUTH_DB = DATA_DIR / "auth.db"


def backup_databases():
    """备份数据库到 data/backups/"""
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for db_name in ["auth.db", "ssc_memory.db"]:
        src = DATA_DIR / db_name
        if src.exists():
            dst = BACKUPS_DIR / f"{db_name}_backup_{timestamp}.db"
            shutil.copy2(src, dst)
            print(f"  备份: {db_name} -> {dst.name}")


def clear_table(conn: sqlite3.Connection, table_name: str):
    """清空表，如果表不存在则跳过"""
    cursor = conn.cursor()
    # 检查表是否存在
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    )
    if not cursor.fetchone():
        print(f"  跳过: {table_name} 表不存在")
        return

    cursor.execute(f"DELETE FROM {table_name}")
    deleted = cursor.rowcount
    conn.commit()
    if deleted > 0:
        print(f"  清空表: {table_name} ({deleted} 条记录)")


def clear_auth_db():
    """清空 auth.db 中的测试数据"""
    if not AUTH_DB.exists():
        print("  跳过: auth.db 不存在")
        return

    conn = sqlite3.connect(str(AUTH_DB))
    try:
        # 清空通知相关表
        clear_table(conn, "notifications")
        clear_table(conn, "notification_reads")

        # 清理工单表
        clear_table(conn, "tickets")

        # 清空 CLI 任务表
        clear_table(conn, "cli_tasks")

        # 清空聊天相关表
        clear_table(conn, "chat_messages")
        clear_table(conn, "chat_sessions")

        # 清空洞察通知查重记录表
        clear_table(conn, "insight_notifications")

        print("  auth.db 清理完成")
    finally:
        conn.close()


def clear_ssc_memory_db():
    """清空 ssc_memory.db 中的测试数据"""
    if not SSC_MEMORY_DB.exists():
        print("  跳过: ssc_memory.db 不存在")
        return

    conn = sqlite3.connect(str(SSC_MEMORY_DB))
    try:
        # 清空对话记录
        clear_table(conn, "conversations")

        # 清空任务表
        clear_table(conn, "task_bs")
        clear_table(conn, "task_st")

        # 清空记忆项
        clear_table(conn, "memory_items")

        print("  ssc_memory.db 清理完成")
    finally:
        conn.close()


def clear_logs_directory():
    """清空 logs/ 目录"""
    if not LOGS_DIR.exists():
        print("  跳过: logs/ 目录不存在")
        return

    count = 0
    for f in LOGS_DIR.iterdir():
        if f.is_file():
            f.unlink()
            count += 1
    print(f"  清空 logs/ 目录 ({count} 个文件)")


def clear_memories_directory():
    """清空 memories/ 目录（vibe coding 指导文件）"""
    if not MEMORIES_DIR.exists():
        print("  跳过: memories/ 目录不存在")
        return

    count = 0
    for f in MEMORIES_DIR.iterdir():
        if f.is_file():
            f.unlink()
            count += 1
        elif f.is_dir():
            shutil.rmtree(f)
            count += 1
    print(f"  清空 memories/ 目录 ({count} 个项目)")


def main():
    print("=" * 50)
    print("  SSC 硅基生物系统 - 测试数据清理工具")
    print("=" * 50)
    print()

    # 1. 备份数据库
    print("[1/5] 备份数据库...")
    backup_databases()
    print()

    # 2. 清空 auth.db
    print("[2/5] 清空 auth.db 测试数据...")
    clear_auth_db()
    print()

    # 3. 清空 ssc_memory.db
    print("[3/5] 清空 ssc_memory.db 测试数据...")
    clear_ssc_memory_db()
    print()

    # 4. 清空 logs/
    print("[4/5] 清空 logs/ 目录...")
    clear_logs_directory()
    print()

    # 5. 清空 memories/
    print("[5/5] 清空 memories/ 目录...")
    clear_memories_directory()
    print()

    print("=" * 50)
    print("  清理完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
