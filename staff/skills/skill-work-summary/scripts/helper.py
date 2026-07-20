"""
工作总结辅助函数
提供时间计算、数据读取、索引管理等功能
"""

from datetime import datetime, timedelta
from pathlib import Path
import json
import sqlite3
import sys
import io
import os

# 【核心修复】强制设置 PYTHONIOENCODING 为 UTF-8，解决 subprocess GBK 编码问题
# 必须在任何其他导入之前设置，否则 subprocess 仍然使用 GBK
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 强制设置 stdout/stderr 为 UTF-8 编码，解决 Windows 编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ============================================================================
# 路径常量定义（使用相对路径，基于沙盒根目录）
# ============================================================================
# LocalShellBackend 的 root_dir 已设置为项目根目录
# execute 工具执行时的工作目录就是项目根目录
# 因此直接使用相对路径即可，不需要 Windows 绝对路径

WORK_SUMMARY_DIR = Path("staff") / "work_summaries"
MEMORIES_MD_DIR = Path("memories")
MEMORY_FILE = MEMORIES_MD_DIR / "AGENTS.md"
INDEX_FILE = WORK_SUMMARY_DIR / "index.json"
DB_FILE = Path("data") / "ssc_memory.db"


def get_date_range(summary_type: str, reference_date: str = None) -> dict:
    """
    计算时间范围

    Args:
        summary_type: "daily" | "weekly" | "monthly"
        reference_date: 可选，格式 "YYYY-MM-DD"。如果提供，则基于此日期计算；否则使用当前日期。

    Returns:
        {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
    """
    from datetime import datetime, timedelta

    # 如果有参考日期，使用参考日期；否则使用当前日期
    if reference_date:
        base_date = datetime.strptime(reference_date, "%Y-%m-%d").date()
    else:
        base_date = datetime.now().date()

    if summary_type == "daily":
        start_date = base_date
        end_date = base_date
    elif summary_type == "weekly":
        # 周一到周日
        start_date = base_date - timedelta(days=base_date.weekday())
        end_date = start_date + timedelta(days=6)
    elif summary_type == "monthly":
        # 月初到月末
        start_date = base_date.replace(day=1)
        if base_date.month == 12:
            end_date = base_date.replace(
                year=base_date.year + 1, month=1, day=1
            ) - timedelta(days=1)
        else:
            end_date = base_date.replace(month=base_date.month + 1, day=1) - timedelta(
                days=1
            )
    else:
        raise ValueError(f"不支持的 summary_type: {summary_type}")

    return {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
    }


def _fix_time_boundary(start: datetime, end: datetime) -> tuple:
    """
    智能修正时间边界问题

    核心逻辑：
    1. 如果 end 时间是 00:00:00（即只指定了日期，没有指定时刻）
    2. 自动减1秒 → 变成前一天的 23:59:59
    3. 如果减完后 end < start，说明是同一天的 00:00:00
    4. 给 end 加1天 → 变成当天的 23:59:59

    示例：
    - 2026-04-22 00:00:00 至 2026-04-23 00:00:00
      → 减1秒 → 2026-04-22 00:00:00 至 2026-04-22 23:59:59 ✅

    - 2026-04-22 00:00:00 至 2026-04-22 00:00:00
      → 减1秒 → 2026-04-21 23:59:59（end < start，错误）
      → 加1天 → 2026-04-22 00:00:00 至 2026-04-22 23:59:59 ✅
    """
    # 如果 end 时间是 00:00:00（只指定了日期）
    if end.hour == 0 and end.minute == 0 and end.second == 0:
        # 减1秒，变成前一天的 23:59:59
        end = end - timedelta(seconds=1)

        # 如果减完后 end < start，说明是同一天的 00:00:00
        # 需要给 end 加1天，变成当天的 23:59:59
        if end < start:
            end = end + timedelta(days=1)

    return start, end


def generate_filename(summary_type: str, **kwargs) -> str:
    """
    生成标准文件名（不含扩展名）

    Args:
        summary_type: daily/weekly/monthly/quarterly/annual/project/milestone/custom
        kwargs: 根据类型不同的参数
            - date: datetime 对象或字符串 "YYYY-MM-DD"（daily/weekly/monthly/quarterly）
            - year: int（annual）
            - project_name: str（project）
            - milestone_name: str（milestone）
            - start_date, end_date: datetime 对象或字符串 "YYYY-MM-DD"（custom）

    Returns:
        文件名（不含 .md）
    """
    prefix = "work_summary"

    if summary_type == "daily":
        date = kwargs.get("date", datetime.now())
        # 支持字符串格式的日期
        if isinstance(date, str):
            date = datetime.strptime(date, "%Y-%m-%d")
        return f"{prefix}_daily_{date.strftime('%Y%m%d')}"

    elif summary_type == "weekly":
        date = kwargs.get("date", datetime.now())
        # 支持字符串格式的日期
        if isinstance(date, str):
            date = datetime.strptime(date, "%Y-%m-%d")
        iso_year, iso_week, _ = date.isocalendar()
        return f"{prefix}_weekly_{iso_year}W{iso_week:02d}"

    elif summary_type == "monthly":
        date = kwargs.get("date", datetime.now())
        # 支持字符串格式的日期
        if isinstance(date, str):
            date = datetime.strptime(date, "%Y-%m-%d")
        return f"{prefix}_monthly_{date.strftime('%Y%m')}"

    elif summary_type == "quarterly":
        date = kwargs.get("date", datetime.now())
        # 支持字符串格式的日期
        if isinstance(date, str):
            date = datetime.strptime(date, "%Y-%m-%d")
        quarter = (date.month - 1) // 3 + 1
        return f"{prefix}_quarterly_{date.year}Q{quarter}"

    elif summary_type == "annual":
        year = kwargs.get("year", datetime.now().year)
        return f"{prefix}_annual_{year}"

    elif summary_type == "project":
        project_name = kwargs.get("project_name", "unknown")
        name = project_name.replace(" ", "_").replace("/", "_")
        return f"{prefix}_project_{name}"

    elif summary_type == "milestone":
        milestone_name = kwargs.get("milestone_name", "unknown")
        name = milestone_name.replace(" ", "_").replace("/", "_")
        return f"{prefix}_milestone_{name}"

    elif summary_type == "custom":
        start = kwargs.get("start_date")
        end = kwargs.get("end_date")
        # 支持字符串格式的日期
        if isinstance(start, str):
            start = datetime.strptime(start, "%Y-%m-%d")
        if isinstance(end, str):
            end = datetime.strptime(end, "%Y-%m-%d")
        return f"{prefix}_custom_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"

    else:
        raise ValueError(f"不支持的总结类型: {summary_type}")


def get_data_source_info(start_date: datetime, end_date: datetime):
    """
    根据时间范围智能选择数据源（分层读取策略）

    策略：
    - < 7天：直接读 SQLite
    - 7天 - 30天：读日报
    - 30天 - 90天：读周报
    - ≥ 90天：分层读取（月报 + 周报 + 日报）

    Args:
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        dict: {
            "source_type": "sqlite" / "mixed" / "daily_summaries" / "weekly_summaries" / "monthly_summaries",
            "instructions": str,
            "files": list (可选),
            "layers": list (分层信息，可选)
        }
    """
    days = (end_date - start_date).days

    # 简单情况：< 90天，使用单一数据源
    if days <= 7:
        return {
            "source_type": "sqlite",
            "instructions": "请执行 read_conversations_from_db() 函数从 SQLite 数据库读取对话记录，并读取 resources/memories_md/MEMORY.md 获取用户信息",
        }

    elif days <= 30:
        files = list(WORK_SUMMARY_DIR.glob("work_summary_daily_*.md"))
        valid_files = []
        for f in files:
            date_str = f.stem.split("_")[-1]
            try:
                file_date = datetime.strptime(date_str, "%Y%m%d")
                if start_date <= file_date <= end_date:
                    valid_files.append(str(f))
            except:
                continue

        return {
            "source_type": "daily_summaries",
            "files": sorted(valid_files),
            "instructions": f"请读取以下日总结文件（共{len(valid_files)}个）：\n"
            + "\n".join(valid_files),
        }

    elif days <= 90:
        files = list(WORK_SUMMARY_DIR.glob("work_summary_weekly_*.md"))
        valid_files = []
        for f in files:
            parts = f.stem.split("_")
            week_str = parts[-1]  # 2026W16
            try:
                year = int(week_str[:4])
                week = int(week_str[5:])
                # ISO周格式：YYYY-Www-1 (周一)
                file_date = datetime.strptime(f"{year}-W{week:02d}-1", "%G-W%V-%u")
                if start_date <= file_date <= end_date:
                    valid_files.append(str(f))
            except:
                continue

        return {
            "source_type": "weekly_summaries",
            "files": sorted(valid_files),
            "instructions": f"请读取以下周总结文件（共{len(valid_files)}个）：\n"
            + "\n".join(valid_files),
        }

    # 复杂情况：≥ 90天，使用分层读取策略
    else:
        layers = []
        current = start_date

        while current < end_date:
            # 计算到月末还有多少天
            if current.month == 12:
                next_month = current.replace(year=current.year + 1, month=1, day=1)
            else:
                next_month = current.replace(month=current.month + 1, day=1)

            days_to_month_end = (next_month - current).days

            # 判断是否足够形成一个完整月（≥ 25天，考虑有些月份只有28天）
            if (
                days_to_month_end >= 25
                and current + timedelta(days=days_to_month_end) <= end_date
            ):
                # 完整月：查找月报
                month_file = (
                    WORK_SUMMARY_DIR
                    / f"work_summary_monthly_{current.strftime('%Y%m')}.md"
                )
                if month_file.exists():
                    layers.append(
                        {
                            "type": "monthly",
                            "file": str(month_file),
                            "period": f"{current.strftime('%Y-%m')}月",
                        }
                    )
                    current = next_month
                else:
                    # 月报不存在，降级到周报
                    week_end = min(current + timedelta(days=7), end_date)
                    layers.append(
                        {
                            "type": "fallback_weekly",
                            "period": f"{current.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')}",
                            "note": "月报不存在，需要读取日报聚合",
                        }
                    )
                    current = week_end

            # 剩余天数 ≥ 7天：查找周报
            elif days_to_month_end >= 7:
                week_end = min(current + timedelta(days=7), end_date)
                iso_year, iso_week, _ = current.isocalendar()
                week_file = (
                    WORK_SUMMARY_DIR
                    / f"work_summary_weekly_{iso_year}W{iso_week:02d}.md"
                )

                if week_file.exists():
                    layers.append(
                        {
                            "type": "weekly",
                            "file": str(week_file),
                            "period": f"第{iso_week}周 ({current.strftime('%m-%d')} 至 {week_end.strftime('%m-%d')})",
                        }
                    )
                else:
                    # 周报不存在，标记需要读取日报
                    layers.append(
                        {
                            "type": "fallback_daily",
                            "period": f"{current.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')}",
                            "note": "周报不存在，需要读取日报聚合",
                        }
                    )

                current = week_end

            # 剩余天数 < 7天：需要读取日报
            else:
                period_end = min(current + timedelta(days=7), end_date)
                layers.append(
                    {
                        "type": "daily",
                        "period": f"{current.strftime('%Y-%m-%d')} 至 {period_end.strftime('%Y-%m-%d')}",
                    }
                )
                current = period_end

        # 构建返回结果
        instructions = "请按照以下分层数据源读取数据（从高层级到低层级）：\n\n"

        for i, layer in enumerate(layers, 1):
            if layer["type"] in ["monthly", "weekly"]:
                instructions += f"{i}. 【{layer['type'].upper()}】{layer['period']}\n"
                instructions += f"   文件：{layer['file']}\n\n"
            else:
                instructions += f"{i}. 【{layer['type'].upper()}】{layer['period']}\n"
                if "note" in layer:
                    instructions += f"   说明：{layer['note']}\n"
                instructions += "\n"

        instructions += "\n请逐层读取并合并数据，然后生成总结。同时读取 resources/memories_md/MEMORY.md 获取用户背景信息。"

        return {"source_type": "mixed", "layers": layers, "instructions": instructions}


def _read_via_http_api(start_date: datetime, end_date: datetime) -> list:
    """
    通过 HTTP API 从服务端读取对话记录（员工端回退方案）
    
    员工电脑上没有数据库，需要通过 API 从服务器获取数据。
    环境变量:
      - SSC_SERVER_URL: 服务端地址（默认 http://localhost:8000）
      - SSC_TOKEN: 认证 Token
    """
    import urllib.request
    import urllib.parse
    
    server_url = os.environ.get("SSC_SERVER_URL", "http://localhost:8000")
    token = os.environ.get("SSC_TOKEN", "")
    
    params = urllib.parse.urlencode({
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
    })
    url = f"{server_url}/api/conversations?{params}"
    
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        
        conversations = []
        for item in data.get("conversations", []):
            conversations.append({
                "user_input": item.get("user_input", ""),
                "agent_response": item.get("agent_response", ""),
                "timestamp": item.get("timestamp", ""),
            })
        return conversations
    except Exception as e:
        print(f"[WARN] HTTP API 调用失败: {e}", file=sys.stderr)
        return []


def read_conversations_from_db(start_date: datetime, end_date: datetime):
    """
    读取指定时间范围的对话记录
    
    【员工端回退】如果本地 DB 不存在，自动通过 HTTP API 从服务端获取
    【关键优化】过滤掉 Agent 自身生成的总结性回复，避免 AI 幻觉传播

    Args:
        start_date: 开始日期
        end_date: 结始日期

    Returns:
        list: 对话记录列表（已过滤）
    """
    if not DB_FILE.exists():
        # 本地 DB 不存在，尝试通过 HTTP API 获取（员工端场景）
        print(f"[INFO] 本地数据库不存在，尝试通过 HTTP API 获取对话数据...", file=sys.stderr)
        raw_conversations = _read_via_http_api(start_date, end_date)
        if not raw_conversations:
            return []
        # 对 HTTP API 返回的数据也进行过滤
        summary_keywords = [
            "工作主线", "关键决策链", "工作节奏分析", "任务完成情况",
            "核心成果", "量化指标", "对话总轮数", "任务完成数",
            "整体思维逻辑", "成果展示", "困难与解决", "个人成长",
            "KISS 反思", "下阶段规划", "六段式工作总结",
        ]
        conversations = []
        for conv in raw_conversations:
            resp_text = conv.get("agent_response", "") or ""
            if any(kw in resp_text for kw in summary_keywords):
                continue
            conversations.append(conv)
        return conversations

    conn = sqlite3.connect(str(DB_FILE))
    cursor = conn.cursor()

    # 表结构：每条消息一行，role='user' 或 'assistant'，content 为消息内容
    # 需要配对 user + assistant 消息为一条对话
    query = """
        SELECT role, content, timestamp
        FROM conversations
        WHERE timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp ASC
    """

    cursor.execute(
        query,
        (
            start_date.strftime("%Y-%m-%d %H:%M:%S"),
            end_date.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )

    rows = cursor.fetchall()
    conn.close()

    # 【关键过滤】排除 Agent 自身生成的总结性回复
    summary_keywords = [
        "工作主线", "关键决策链", "工作节奏分析", "任务完成情况",
        "核心成果", "量化指标", "对话总轮数", "任务完成数",
        "技能使用次数", "用户满意度", "整体思维逻辑",
        "成果展示", "困难与解决", "个人成长",
        "KISS 反思", "下阶段规划", "六段式工作总结",
        "第一段：", "第二段：", "第三段：",
    ]

    # 配对 user/assistant 消息为对话
    conversations = []
    pending_user = None
    filtered_count = 0

    for row in rows:
        role = row[0]
        content = row[1]
        timestamp = row[2]

        if role == "user":
            pending_user = {"user_input": content, "timestamp": timestamp}
        elif role == "assistant" and pending_user:
            # 检查 assistant 回复是否为总结性内容
            is_summary = any(kw in (content or "") for kw in summary_keywords)
            if is_summary and "生成" not in (pending_user["user_input"] or "") and "整理" not in (pending_user["user_input"] or "") and "总结" not in (pending_user["user_input"] or ""):
                filtered_count += 1
                pending_user = None
                continue
            conversations.append({
                "user_input": pending_user["user_input"],
                "agent_response": content,
                "timestamp": pending_user["timestamp"],
            })
            pending_user = None

    if filtered_count > 0:
        print(f"[INFO] 已过滤 {filtered_count} 条 Agent 编造的总结性回复", file=sys.stderr)

    return conversations


def file_exists(filename: str) -> bool:
    """
    检查总结文件是否已存在

    Args:
        filename: 文件名（不含扩展名）

    Returns:
        bool: 文件是否存在
    """
    filepath = WORK_SUMMARY_DIR / f"{filename}.md"
    return filepath.exists()


def update_index(
    filename: str,
    summary_type: str,
    start_date: datetime,
    end_date: datetime,
    word_count: int = 0,
):
    """
    更新 work_summary/index.json 索引

    Args:
        filename: 生成的文件名（不含扩展名）
        summary_type: 总结类型
        start_date: 开始日期
        end_date: 结束日期
        word_count: 字数统计
    """
    # 读取现有索引
    if INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            index_data = json.load(f)
    else:
        index_data = {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "summaries": [],
        }

    # 查找是否已存在（用于更新）
    existing_idx = None
    for i, entry in enumerate(index_data["summaries"]):
        if entry["filename"] == f"{filename}.md":
            existing_idx = i
            break

    # 构建新记录
    new_entry = {
        "filename": f"{filename}.md",
        "type": summary_type,
        "period": {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        },
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "word_count": word_count,
            "tags": [],
        },
    }

    if existing_idx is not None:
        # 更新已有记录
        index_data["summaries"][existing_idx] = new_entry
    else:
        # 添加新记录
        index_data["summaries"].append(new_entry)

    index_data["last_updated"] = datetime.now().isoformat()

    # 保存
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)


def main():
    """命令行入口函数"""
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "Missing action parameter",
            "usage": "python helper.py <action> [json_args]",
            "available_actions": [
                "get_date_range",
                "generate_filename",
                "get_data_source_info",
                "read_conversations_from_db",
                "file_exists",
                "update_index"
            ]
        }, ensure_ascii=True))
        sys.exit(1)

    action = sys.argv[1]

    # 解析 JSON 参数（如果有）
    args = {}
    if len(sys.argv) > 2:
        # 【智能参数修复】收集所有剩余参数并合并
        all_params = sys.argv[2:]
        
        print(f"DEBUG: received {len(all_params)} args", file=sys.stderr)
        print(f"DEBUG: raw args = {all_params}", file=sys.stderr)
        
        # 暴力合并所有参数（用空格连接）
        full_cmd_args = " ".join(all_params)
        print(f"DEBUG: merged args = {full_cmd_args[:150]}", file=sys.stderr)
        
        # 清理 Windows 特有的转义字符
        clean_json = full_cmd_args.replace('\\"', '"').replace("\\'", "'")
        print(f"DEBUG: cleaned args = {clean_json[:150]}", file=sys.stderr)
        
        # 提取 JSON 对象（找到第一个 { 和最后一个 }）
        start = clean_json.find("{")
        end = clean_json.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw_json = clean_json[start : end + 1]
            print(f"DEBUG: extracted JSON = {raw_json[:100]}", file=sys.stderr)
        else:
            raw_json = clean_json
            print(f"DEBUG: using full string as JSON = {raw_json[:100]}", file=sys.stderr)

        # 检查是否为 JSON 文件路径
        if raw_json.endswith('.json'):
            try:
                # 尝试 utf-8-sig（带 BOM）编码，兼容 Windows PowerShell
                with open(raw_json, 'r', encoding='utf-8-sig') as f:
                    args = json.load(f)
            except UnicodeDecodeError:
                # 如果失败，尝试普通 utf-8
                try:
                    with open(raw_json, 'r', encoding='utf-8') as f:
                        args = json.load(f)
                except Exception as e:
                    print(json.dumps({
                        "success": False,
                        "error": f"Failed to read JSON file: {str(e)}",
                        "file": raw_json
                    }, ensure_ascii=True))
                    sys.exit(1)
            except Exception as e:
                print(json.dumps({
                    "success": False,
                    "error": f"Failed to read JSON file: {str(e)}",
                    "file": raw_json
                }, ensure_ascii=True))
                sys.exit(1)
        else:
            # 尝试直接解析 JSON 字符串
            try:
                args = json.loads(raw_json)
                print("DEBUG: JSON parsed successfully", file=sys.stderr)
            except json.JSONDecodeError as e:
                # 【智能修复】尝试修复常见的 JSON 格式问题
                fixed_json = raw_json
                
                # 移除可能的外层引号（Shell 添加的）
                if (fixed_json.startswith("'") and fixed_json.endswith("'")) or (
                    fixed_json.startswith('"') and fixed_json.endswith('"')
                ):
                    fixed_json = fixed_json[1:-1]
                    print(f"DEBUG: removed outer quotes", file=sys.stderr)
                
                import re
                
                # 第 1 步：修复键没有引号的情况：{type: ...} -> {"type": ...}
                fixed_json = re.sub(
                    r"(\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1 "\2":', fixed_json
                )
                print(f"DEBUG: after fixing keys = {fixed_json}", file=sys.stderr)
                
                # 第 2 步：修复字符串值没有引号的情况
                # 匹配 : 后面的非数字、非布尔、非 null、非数组、非对象的值
                def fix_string_value(match):
                    prefix = match.group(1)  # : 或 ,
                    value = match.group(2).strip()
                    
                    # 如果已经是引号包裹的，不处理
                    if value.startswith('"') or value.startswith("'"):
                        return f'{prefix} {value}'
                    
                    # 如果是布尔值、null，不处理
                    if value in ('true', 'false', 'null'):
                        return f'{prefix} {value}'
                    
                    # 如果是纯数字（整数或浮点数），不处理
                    # 注意：日期格式如 2026-04-24 不是纯数字，需要加引号
                    try:
                        float(value)
                        # 能成功转换为数字，说明是真正的数字
                        return f'{prefix} {value}'
                    except ValueError:
                        pass  # 不是数字，继续下面的检查
                    
                    # 如果是数组或对象，不处理
                    if value.startswith('[') or value.startswith('{'):
                        return f'{prefix} {value}'
                    
                    # 其他情况（包括日期、字符串等），添加双引号
                    return f'{prefix} "{value}"'
                
                # 匹配 : 或 , 后面的值（直到下一个 , 或 } 或行尾）
                fixed_json = re.sub(
                    r'(:|,)\s*([^,}\]]+)',
                    fix_string_value,
                    fixed_json
                )
                print(f"DEBUG: trying fixed JSON = {fixed_json}", file=sys.stderr)
                
                try:
                    args = json.loads(fixed_json)
                    print("DEBUG: JSON fixed and parsed successfully", file=sys.stderr)
                except json.JSONDecodeError as e2:
                    print(json.dumps({
                        "success": False,
                        "error": f"JSON parse error: {str(e)}",
                        "hint": "Ensure valid JSON format, e.g.: '{\"type\": \"daily\"}'",
                        "received": raw_json,
                        "attempted_fix": fixed_json
                    }, ensure_ascii=True))
                    sys.exit(1)

    # 执行对应操作
    try:
        if action == "get_date_range":
            result = get_date_range(
                summary_type=args.get("type", "daily"),
                reference_date=args.get("reference_date")
            )
            print(json.dumps({"success": True, **result}, ensure_ascii=True))

        elif action == "generate_filename":
            summary_type = args.get("type", "daily")
            
            # 提取其他参数，并将日期字符串转换为 datetime 对象
            func_args = {}
            for k, v in args.items():
                if k == "type":
                    continue
                # 如果是日期字段，转换为 datetime 对象
                if k in ("date", "start_date", "end_date") and isinstance(v, str):
                    try:
                        func_args[k] = datetime.strptime(v, "%Y-%m-%d")
                    except ValueError:
                        print(json.dumps({
                            "success": False,
                            "error": f"Invalid date format for {k}: {v}",
                            "hint": "Date format must be YYYY-MM-DD (e.g., '2026-04-24')"
                        }, ensure_ascii=False))
                        sys.exit(1)
                else:
                    func_args[k] = v
            
            result = generate_filename(summary_type=summary_type, **func_args)
            print(json.dumps({"success": True, "filename": result}, ensure_ascii=False))

        elif action == "get_data_source_info":
            # 从参数获取日期，如果没有则使用默认值
            start_date = datetime.strptime(args.get("start_date"), "%Y-%m-%d") if args.get("start_date") else datetime.now()
            end_date = datetime.strptime(args.get("end_date"), "%Y-%m-%d") if args.get("end_date") else datetime.now()

            result = get_data_source_info(start_date, end_date)
            print(json.dumps({"success": True, **result}, ensure_ascii=True))

        elif action == "read_conversations_from_db":
            # 【调试】打印当前工作目录到 stderr
            print(f"[DEBUG] CWD: {os.getcwd()}", file=sys.stderr)
            print(f"[DEBUG] DB_FILE: {DB_FILE.absolute()}", file=sys.stderr)
            print(f"[DEBUG] DB_FILE exists: {DB_FILE.exists()}", file=sys.stderr)
            
            start_date = datetime.strptime(args.get("start_date"), "%Y-%m-%d") if args.get("start_date") else datetime.now()
            end_date = datetime.strptime(args.get("end_date"), "%Y-%m-%d") if args.get("end_date") else datetime.now()

            # 【调试】打印原始时间
            print(f"[DEBUG] Original start_date: {start_date}", file=sys.stderr)
            print(f"[DEBUG] Original end_date: {end_date}", file=sys.stderr)

            # 修正时间边界
            start_date, end_date = _fix_time_boundary(start_date, end_date)
            
            # 【调试】打印修正后的时间
            print(f"[DEBUG] Fixed start_date: {start_date}", file=sys.stderr)
            print(f"[DEBUG] Fixed end_date: {end_date}", file=sys.stderr)

            result = read_conversations_from_db(start_date, end_date)
            
            # 【调试】打印结果数量
            print(f"[DEBUG] Query result count: {len(result)}", file=sys.stderr)
            
            # 【关键修复】返回足够多的真实对话内容，避免 Agent 编造
            # 策略：最多返回 20 条完整对话（包含 user_input 和 agent_response）
            if result:
                # 如果对话数量 <= 20，全部返回；否则返回前 10 条 + 最后 10 条
                if len(result) <= 20:
                    sample_conversations = result
                else:
                    sample_conversations = result[:10] + result[-10:]
                
                output = json.dumps({
                    "success": True, 
                    "count": len(result),
                    "message": f"找到 {len(result)} 条对话记录",
                    "sample_conversations": sample_conversations,
                    "note": f"为节省输出空间，显示 {len(sample_conversations)} 条代表性对话。Agent 必须严格基于这些真实对话生成工作总结，严禁编造任何不存在的内容。"
                }, ensure_ascii=False)
            else:
                output = json.dumps({
                    "success": True, 
                    "count": 0,
                    "message": "没有找到对话记录",
                    "conversations": []
                }, ensure_ascii=False)
            
            print(output)
            
            # 【调试】打印输出大小
            print(f"[DEBUG] Output size: {len(output)} bytes", file=sys.stderr)

        elif action == "file_exists":
            filename = args.get("filename")
            if not filename:
                print(json.dumps({
                    "success": False,
                    "error": "Missing filename parameter"
                }, ensure_ascii=True))
                sys.exit(1)

            exists = file_exists(filename)
            print(json.dumps({"success": True, "exists": exists}, ensure_ascii=True))

        elif action == "update_index":
            filename = args.get("filename")
            summary_type = args.get("summary_type", "daily")
            start_date_str = args.get("start_date")
            end_date_str = args.get("end_date")
            word_count = args.get("word_count", 0)

            # 验证必需参数
            if not filename:
                print(json.dumps({
                    "success": False,
                    "error": "Missing filename parameter",
                    "required_params": ["filename", "start_date", "end_date"]
                }, ensure_ascii=True))
                sys.exit(1)
            
            if not start_date_str:
                print(json.dumps({
                    "success": False,
                    "error": "Missing start_date parameter",
                    "hint": "Date format must be YYYY-MM-DD (e.g., '2026-04-24')",
                    "required_params": ["filename", "start_date", "end_date"]
                }, ensure_ascii=True))
                sys.exit(1)
            
            if not end_date_str:
                print(json.dumps({
                    "success": False,
                    "error": "Missing end_date parameter",
                    "hint": "Date format must be YYYY-MM-DD (e.g., '2026-04-24')",
                    "required_params": ["filename", "start_date", "end_date"]
                }, ensure_ascii=True))
                sys.exit(1)
            
            # 解析日期
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            except ValueError:
                print(json.dumps({
                    "success": False,
                    "error": f"Invalid start_date format: {start_date_str}",
                    "hint": "Date format must be YYYY-MM-DD (e.g., '2026-04-24')",
                    "received": start_date_str
                }, ensure_ascii=True))
                sys.exit(1)
            
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
            except ValueError:
                print(json.dumps({
                    "success": False,
                    "error": f"Invalid end_date format: {end_date_str}",
                    "hint": "Date format must be YYYY-MM-DD (e.g., '2026-04-24')",
                    "received": end_date_str
                }, ensure_ascii=True))
                sys.exit(1)

            update_index(filename, summary_type, start_date, end_date, word_count)
            print(json.dumps({"success": True, "message": "Index updated successfully"}, ensure_ascii=True))

        else:
            print(json.dumps({
                "success": False,
                "error": f"Unknown action: {action}",
                "available_actions": [
                    "get_date_range",
                    "generate_filename",
                    "get_data_source_info",
                    "read_conversations_from_db",
                    "file_exists",
                    "update_index"
                ]
            }, ensure_ascii=True))
            sys.exit(1)

    except Exception as e:
        print(json.dumps({
            "success": False,
            "error": f"Execution failed: {str(e)}",
            "action": action,
            "args": args
        }, ensure_ascii=True))
        sys.exit(1)


if __name__ == "__main__":
    main()
