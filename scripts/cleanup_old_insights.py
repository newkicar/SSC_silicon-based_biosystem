#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""清理过期的洞察通知记录

每天凌晨定时执行，清理 expires_at < NOW 的记录。

用法:
  python scripts/cleanup_old_insights.py
"""

import sqlite3
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = Path(__file__).parent.parent / "data" / "auth.db"


def main():
    """清理过期洞察通知记录"""
    print("=" * 50)
    print("  清理过期洞察通知记录")
    print("=" * 50)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        # 初始化表（如果不存在）
        from src.data.insight_notifications import init_insight_notifications_table

        init_insight_notifications_table(conn)

        # 清理过期记录
        from src.data.insight_notifications import cleanup_expired

        deleted = cleanup_expired(conn)
        print(f"  清理过期记录: {deleted} 条")

    finally:
        conn.close()

    print("=" * 50)
    print("  清理完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()