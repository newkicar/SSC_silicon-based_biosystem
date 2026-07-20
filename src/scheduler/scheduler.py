"""
定时任务调度器 —— 硅基生物的自主神经系统

心跳、呼吸、消化、体温——持续运转的基础生命功能。

调度的任务：
- 超时扫描器：每30秒扫描超时任务，重试/重新分配/升级
- 心跳巡检：每30分钟快照对比，差异报告传给大脑
- 凌晨记忆整理：每天02:00清理 + 02:30提炼MD记忆
- 晨间扫描：每天08:00生成晨报
- 日终总结：每天18:00生成日报告
- Token消耗监控：实时统计
"""

import sys
import threading
import time
from datetime import datetime
from src.data.task_queue import (
    get_connection,
    update_task_bs_status,
    update_task_st_status,
    insert_task_bs,
    insert_event,
)
from src.scheduler.work_time import is_in_work_window
from src.security.auth import list_users, AUTH_DB_PATH
from src.tools.insight_data import get_insight_provider
from src.tools.dashboard_data import get_dashboard_provider
import sqlite3


class Scheduler:
    """定时任务调度器"""

    def __init__(self):
        self._running = False
        self._threads = []
        self._last_insight_date = ""
        self._last_refresh_context = ""
        self._last_evening_date = ""  # 日终总结防重复

    def start(self):
        """启动所有定时任务"""
        if self._running:
            return
        self._running = True

        tasks = [
            ("超时扫描器", self._timeout_scanner, 30),
            ("心跳巡检", self._heartbeat, 30 * 60),
            ("凌晨记忆整理", self._memory_cleanup, 60),
            ("晨间扫描", self._morning_scan, 60),
            ("日终总结", self._evening_summary, 60),
            ("数据自动更新", self._daily_data_refresh, 60),
            ("Token监控", self._token_monitor, 5 * 60),
        ]

        for name, func, interval in tasks:
            t = threading.Thread(
                target=self._run_loop, args=(name, func, interval), daemon=True
            )
            t.start()
            self._threads.append(t)

    def stop(self):
        self._running = False

    def _run_loop(self, name, func, interval):
        while self._running:
            try:
                func()
            except Exception as e:
                print(f"[调度器-{name}] 异常: {e}")
            time.sleep(interval)

    # ---- 超时扫描器 ----
    def _timeout_scanner(self):
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        # 扫描 task_bs 超时任务
        cursor.execute(
            """SELECT * FROM task_bs
               WHERE status IN ('ISSUED', 'ACCEPTED', 'IN_PROGRESS')
               AND timeout_at < ?""",
            (now,),
        )
        bs_overdue = cursor.fetchall()

        for row in bs_overdue:
            row = dict(row)
            if row["status"] == "ISSUED":
                update_task_bs_status(
                    row["task_id"], "FAILED", result={"reason": "超时未认领"}
                )
                insert_event(
                    event_id=f"EVT-TIMEOUT-{row['task_id']}",
                    event_type="task_timeout",
                    source="scheduler",
                    payload={"task_id": row["task_id"], "reason": "超时未认领"},
                )
            elif row["status"] in ("ACCEPTED", "IN_PROGRESS"):
                if row["retry_count"] < 3:
                    cursor.execute(
                        "UPDATE task_bs SET status='ISSUED', retry_count=retry_count+1 WHERE task_id=?",
                        (row["task_id"],),
                    )
                    conn.commit()
                else:
                    update_task_bs_status(
                        row["task_id"],
                        "ESCALATED",
                        result={"reason": "重试耗尽，升级人工"},
                    )

        # 扫描 task_st 超时任务
        cursor.execute(
            """SELECT * FROM task_st
               WHERE status IN ('ISSUED', 'ACCEPTED', 'IN_PROGRESS')
               AND timeout_at < ?""",
            (now,),
        )
        st_overdue = cursor.fetchall()

        for row in st_overdue:
            row = dict(row)
            if row["status"] == "ISSUED":
                update_task_st_status(
                    row["task_id"], "FAILED", result={"reason": "超时未认领"}
                )
            elif row["status"] in ("ACCEPTED", "IN_PROGRESS"):
                if row["retry_count"] < row["max_retries"]:
                    cursor.execute(
                        "UPDATE task_st SET status='ISSUED', retry_count=retry_count+1 WHERE task_id=?",
                        (row["task_id"],),
                    )
                    conn.commit()
                else:
                    update_task_st_status(
                        row["task_id"], "FAILED_FINAL", result={"reason": "重试耗尽"}
                    )

        conn.close()

    # ---- 心跳巡检 ----
    def _heartbeat(self):
        now = datetime.now()
        if not (8 <= now.hour < 18):
            return

        insert_event(
            event_id=f"EVT-HEARTBEAT-{now.strftime('%Y%m%d%H%M%S')}",
            event_type="heartbeat",
            source="scheduler",
            payload={"status": "alive", "timestamp": now.isoformat()},
        )

    # ---- 凌晨记忆整理（LLM驱动：发送所有记录，让大脑决定什么重要）----
    def _memory_cleanup(self):
        now = datetime.now()
        if now.hour != 2 or now.minute > 5:
            return

        from src.memory.database import (
            cleanup_low_value_records,
            get_unmemorized_records,
            mark_as_memorized,
        )

        records = get_unmemorized_records()
        if records:
            # 不做过滤，只做基础清洗：去空消息、截断过长内容
            raw_records = []
            for r in records:
                content = (r.get("content", "") or "").strip()
                if not content or len(content) < 3:  # 只去空消息
                    continue
                # 截断过长消息（保留前500字符给LLM判断）
                truncated = content[:500] + "..." if len(content) > 500 else content
                raw_records.append(
                    f"[{r.get('role', '?')}|{r.get('created_at', '')[:16]}] {truncated}"
                )

            if raw_records:
                brain_prompt = f"""以下是一天的HR SSC对话记录。请从中提炼有价值的信息，忽略无意义的闲聊。

## 对话记录（共{len(raw_records)}条）
{chr(10).join(raw_records[:80])}

你的任务：
1. **先过滤**：忽略问候语（你好/谢谢/好的/收到）、命令日志（/tasks/whoami/quit等）、无信息量的确认回复
2. **再提炼**：从剩余记录中提取：
   - 关键决策（处理了什么问题，做出了什么决定）
   - 教训总结（发现的新模式或注意事项）
   - 待办事项（未完成的任务）
3. 如果所有记录都是无意义的闲聊，直接回复"今日无有价值记录"

每条简短精炼，用"-"开头。输出纯文本。"""

                refined = self._call_brain(brain_prompt)

                if refined and "无有价值" not in refined:
                    from src.memory.md_memory import read_memory, update_memory

                    existing = read_memory()
                    append_content = (
                        f"\n\n## 自动提炼 ({now.strftime('%Y-%m-%d')})\n{refined}"
                    )
                    if len(existing) + len(append_content) < 5000:
                        update_memory(existing + append_content)
                    print(f"[记忆整理] 大脑已提炼 {len(raw_records)} 条对话记录")
                elif refined:
                    print(f"[记忆整理] 大脑判断今日无有价值记录，跳过提炼")
                else:
                    # 大脑调用失败，回退到简单拼接
                    md_content = self._build_md_from_records(records)
                    if md_content:
                        from src.memory.md_memory import read_memory, update_memory

                        existing = read_memory()
                        append_content = f"\n\n## 自动提炼 ({now.strftime('%Y-%m-%d')})\n{md_content}"
                        if len(existing) + len(append_content) < 5000:
                            update_memory(existing + append_content)
                    print(f"[记忆整理] 大脑调用失败，回退到简单拼接")

            mark_as_memorized([r["id"] for r in records])

        deleted = cleanup_low_value_records()
        print(f"[记忆整理] 清理低价值记录: {deleted}条")

    def _build_md_from_records(self, records):
        """简单拼接（大脑调用失败时的回退方案）"""
        summaries = []
        for r in records:
            content = (r.get("content", "") or "").strip()
            if content and len(content) >= 10:
                summaries.append(f"- {r.get('role', '?')}: {content[:80]}...")
        return "\n".join(summaries[:10]) if summaries else ""

    # ---- 晨间扫描（调用大脑生成晨报）----
    def _morning_scan(self):
        now = datetime.now()
        if now.hour != 8 or now.minute > 5:
            return

        # 工单/任务数据 from auth.db
        auth_conn = self._get_auth_conn()
        auth_cur = auth_conn.cursor()
        auth_cur.execute(
            "SELECT COUNT(*) as cnt FROM cli_tasks WHERE status IN ('dispatched', 'claimed')"
        )
        pending_tasks = auth_cur.fetchone()["cnt"]
        auth_cur.execute("SELECT COUNT(*) as cnt FROM tickets WHERE status = 'open'")
        open_tickets = auth_cur.fetchone()["cnt"]
        auth_conn.close()

        # 对话数据 from ssc_memory.db
        yesterday = now.strftime("%Y-%m-%d")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content, created_at FROM conversations WHERE date(created_at) = ? ORDER BY created_at DESC LIMIT 50",
            (yesterday,),
        )
        recent_records = [dict(r) for r in cursor.fetchall()]
        conn.close()
        # 只做基础清洗：去空消息
        conv_lines = []
        for r in recent_records:
            content = (r.get("content", "") or "").strip()
            if not content or len(content) < 3:
                continue
            truncated = content[:200] + "..." if len(content) > 200 else content
            conv_lines.append(
                f"- [{r['role']}|{r.get('created_at', '')[:16]}] {truncated}"
            )
        conv_summary = "\n".join(conv_lines[:30])
        brain_prompt = f"""请为今天的HR SSC工作生成一份简洁的晨报（中文）。

## 当前待办
- 待处理CLI任务：{pending_tasks}
- 未关闭工单：{open_tickets}

## 最近对话摘要
{conv_summary or '（无）'}

请生成一份简短的晨报，包含：
1. 今日待办事项（如有）
2. 需要关注的事项（如有）
3. 今日建议优先处理的事项（如有）

输出纯文本，不要用markdown格式。"""
        morning_text = self._call_brain(brain_prompt)
        insert_event(
            event_id=f"EVT-MORNING-{now.strftime('%Y%m%d')}",
            event_type="morning_scan",
            source="scheduler",
            payload={
                "type": "晨报",
                "pending_tasks": pending_tasks,
                "open_tickets": open_tickets,
                "summary": morning_text[:500] if morning_text else "",
            },
        )
        print(f"[晨报] 已生成 {now.strftime('%Y-%m-%d')} 的晨报")

    # ---- 日终总结（调用大脑生成文字报告）----
    def _evening_summary(self):
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        # 防重复：同一天只触发一次，且只在 18:00-18:05 窗口
        if self._last_evening_date == today:
            return
        if now.hour != 18 or now.minute > 5:
            return

        # task_bs / task_st / conversations from ssc_memory.db
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM task_bs WHERE date(issued_at) = ?", (today,)
        )
        bs_count = cursor.fetchone()["cnt"]
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM task_st WHERE status = 'COMPLETED' AND date(completed_at) = ?",
            (today,),
        )
        completed = cursor.fetchone()["cnt"]
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM conversations WHERE date(created_at) = ?",
            (today,),
        )
        conv_count = cursor.fetchone()["cnt"]
        # 收集今天的所有对话（不过滤，让LLM判断什么重要）
        cursor.execute(
            "SELECT role, content, created_at FROM conversations WHERE date(created_at) = ? ORDER BY created_at DESC LIMIT 80",
            (today,),
        )
        today_records = [dict(r) for r in cursor.fetchall()]
        conn.close()

        # 今天的工单 from auth.db
        auth_conn = self._get_auth_conn()
        auth_cur = auth_conn.cursor()
        auth_cur.execute(
            "SELECT ticket_no, title, status, submitter FROM tickets WHERE date(created_at) = ?",
            (today,),
        )
        today_tickets = [dict(r) for r in auth_cur.fetchall()]
        auth_conn.close()
        # 组装摘要数据（基础清洗，不过滤）
        conv_lines = []
        for r in today_records:
            content = (r.get("content", "") or "").strip()
            if not content or len(content) < 3:
                continue
            truncated = content[:200] + "..." if len(content) > 200 else content
            conv_lines.append(
                f"- [{r['role']}|{r.get('created_at', '')[:16]}] {truncated}"
            )
        conv_summary = "\n".join(conv_lines[:50])
        ticket_summary = "\n".join(
            [
                f"- {t['ticket_no']} {t['title']} ({t['status']})"
                for t in today_tickets[:10]
            ]
        )
        # 调用大脑生成文字总结（让LLM过滤垃圾信息）
        brain_prompt = f"""请为今天的HR SSC工作生成一份简洁的日终总结报告（中文）。

## 今日数据统计
- 大脑处理任务数：{bs_count}
- 完成任务数：{completed}
- 对话轮数：{conv_count}

## 今日对话记录（共{len(conv_lines)}条）
{conv_summary or '（无）'}

## 今日工单
{ticket_summary or '（无）'}

你的任务：
1. **先过滤**：忽略问候语、命令日志（/tasks/whoami/quit等）、无信息量的确认回复
2. **再总结**：从剩余记录中提炼：
   - 今日概览（一句话概括）
   - 重要事项（处理的关键问题和决策）
   - 待跟进事项（未完成的任务）
   - 明日建议（如有）
3. 如果所有对话都是无意义的闲聊，直接回复"今日无重要事项"

输出纯文本，不要用markdown格式。"""
        summary_text = self._call_brain(brain_prompt)
        # 保存到MD记忆
        if summary_text:
            from src.memory.md_memory import read_memory, update_memory

            existing = read_memory()
            append_content = f"\n\n## 日终总结 ({today})\n{summary_text}"
            if len(existing) + len(append_content) < 5000:
                update_memory(existing + append_content)

        # 标记今日已完成
        self._last_evening_date = today

        # 写入事件
        insert_event(
            event_id=f"EVT-EVENING-{now.strftime('%Y%m%d')}",
            event_type="evening_summary",
            source="scheduler",
            payload={
                "task_bs_count": bs_count,
                "completed": completed,
                "conversations": conv_count,
                "summary": summary_text[:500] if summary_text else "",
            },
        )
        print(f"[日终总结] 已生成 {today} 的日终总结报告")

    # ---- 调用大脑（通用方法）----
    def _call_brain(self, prompt: str) -> str:
        """直接调用 LLM 生成内容，不走大脑 agent loop。

        用于晨报、日终总结等非对话场景。
        避免触发完整的消息处理流程（下行脊髓、工单创建等）。

        Args:
            prompt: 大脑提示词

        Returns:
            LLM 生成的纯文本回复
        """
        from src.config.settings import get_llm

        llm = get_llm()
        response = llm.invoke(prompt)
        # LangChain LLM 返回 AIMessage，提取 content
        if hasattr(response, "content"):
            return response.content
        return str(response)

    # ---- 每日数据自动更新（每天05:00窗口）----
    def _daily_data_refresh(self):
        now = datetime.now()
        if now.hour != 5 or now.minute > 10:
            return

        today_str = now.strftime("%Y-%m-%d")
        self._last_insight_date = ""  # 重置，允许本轮更新后触发洞察

        import subprocess
        from pathlib import Path

        project_root = str(Path(__file__).resolve().parent.parent.parent)
        print(f"[数据更新] 开始每日数据刷新...")

        # 1. 运行花名册刷新
        roster_ok = False
        try:
            result = subprocess.run(
                [sys.executable, "-X", "utf8", "scripts/refresh_roster.py"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=300,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                print(f"[数据更新] 花名册刷新完成")
                roster_ok = True
            else:
                print(f"[数据更新] 花名册刷新失败: {result.stderr[:300]}")
        except Exception as e:
            print(f"[数据更新] 花名册刷新异常: {e}")

        # 2. 运行加班数据更新
        overtime_ok = False
        try:
            result = subprocess.run(
                [sys.executable, "-X", "utf8", "scripts/build_overtime.py"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=3600,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                print(f"[数据更新] 加班数据更新完成")
                overtime_ok = True
            else:
                print(f"[数据更新] 加班数据更新失败: {result.stderr[:300]}")
        except Exception as e:
            print(f"[数据更新] 加班数据更新异常: {e}")

        # 3. 增量刷新向量索引
        if roster_ok or overtime_ok:
            from src.tools.vector_rag import rebuild_db_index_file

            if roster_ok:
                cnt = rebuild_db_index_file("员工花名册.xlsx")
                print(f"[数据更新] 花名册索引更新: {cnt} 行")
            if overtime_ok:
                print(f"[数据更新] 重建加班数据向量索引...")
                cnt = rebuild_db_index_file("加班基础数据.xlsx")
                print(f"[数据更新] 加班数据索引更新: {cnt} 行")

        # 4. 写入事件日志
        insert_event(
            event_id=f"EVT-DATA-REFRESH-{now.strftime('%Y%m%d')}",
            event_type="data_refresh",
            source="scheduler",
            payload={
                "roster_ok": roster_ok,
                "overtime_ok": overtime_ok,
                "timestamp": now.isoformat(),
            },
        )

        # 5. 数据状态判断：双数据源都成功才触发洞察，否则创建故障工单
        if roster_ok and overtime_ok:
            self._last_refresh_context = "花名册已刷新、加班数据已刷新"
            # 立即触发（不等待下一个调度 tick）
            self._run_daily_insight(now, self._last_refresh_context)
        else:
            failed = []
            if not roster_ok:
                failed.append("花名册")
            if not overtime_ok:
                failed.append("加班数据")
            self._create_hris_emergency_ticket(now, "、".join(failed))

        print(f"[数据更新] 每日数据刷新完成")

    def _get_auth_conn(self) -> sqlite3.Connection:
        """获取 auth.db 连接（用于查询 tickets / cli_tasks）"""
        conn = sqlite3.connect(str(AUTH_DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def _run_daily_insight(self, now, data_context: str = "") -> bool:
        """数据洞察：只使用洞察子代理，无降级。

        创建独立子代理（create_deep_agent），传入 model=get_llm()。
        子代理失败直接抛异常，不降级到大脑。
        """
        # 防重复：同一天只触发一次
        today_str = now.strftime("%Y-%m-%d")
        if self._last_insight_date == today_str:
            print(f"[数据洞察] 今日洞察已生成，跳过重复触发")
            return False

        # === 1) 创建洞察子代理（必须传入 model，失败直接抛异常）===
        from src.insight_agent.agent import (
            create_insight_agent,
            generate_insight_with_retry,
        )

        agent = create_insight_agent()  # 无降级，失败直接报错

        # === 2) 生产结构化洞察快照 ===
        insight_provider = get_insight_provider()
        dp = get_dashboard_provider()

        # 收集 auth.db 统计
        auth_db_stats = self._gather_auth_db_stats()
        # 收集 ssc_memory.db 统计
        memory_db_stats = self._gather_memory_db_stats()

        # === 3) 获取公司列表 ===
        companies = self._get_distinct_companies(dp)

        # === 4) 严格按公司分别洞察，不合并 ===
        import time

        insight_start = time.time()
        insight_results = {}
        for company_name in companies:
            if not company_name:
                continue

            company_start = time.time()
            print(
                f"\n[数据洞察] ==================== 开始生成 {company_name} 洞察 ===================="
            )

            enterprise_single = insight_provider.get_enterprise_insight(
                dp=dp,
                auth_db_stats=auth_db_stats,
                memory_db_stats=memory_db_stats,
                company=company_name,
            )
            data_tables_single = insight_provider.format_enterprise_insight_for_llm(
                enterprise_single
            )

            # 构建 prompt
            scope_label = company_name
            users_info = self._get_notification_users_info()
            org_mapping = self._get_org_leader_mapping()

            prompt = f"""你是HR SSC系统的自动洞察引擎。请基于今日更新的数据和当前系统状态，生成洞察通知。

## 洞察范围
{scope_label}

## 本轮数据更新
- {data_context if data_context else "无特定更新（全量扫描模式）"}

## 系统运行数据快照
{data_tables_single}

    ## 任务
    1. 分析上述数据，识别最值得关注的异常或趋势
    2. **最多生成5条洞察**，按优先级排序
    3. 每条洞察附带具体数据支撑，避免空泛描述
    4. title 必须包含年月（格式：2026年6月），控制在25字以内，content 控制在80字以内
    5. 每条洞察必须生成20字以内的summary（用于查重）
    6. 只提供数据说明和关注要点，不要建议谁来处理

    ## 输出格式
    必须输出 JSON 格式，包含 dispatch_actions 数组，每个元素包含：
    - type: "create_notification"
    - company: 公司名称（虚拟科技公司 或 虚拟智联公司，必填）
    - target_user: 具体用户名（从下方用户列表和组织映射中查找）
    - title: [类型]2026年6月洞察内容（25字以内，**必须包含年月**）
    - content: 详细说明（40-80字，简洁）
    - summary: 洞察总结（20字以内，用于查重）
    - priority: "high"|"normal"
    - notif_type: "alert"|"info"|"warning"
    - insight_level: "company"|"center"|"department"
    - insight_org: 组织名称，公司级留空
    - insight_type: "cost"|"attendance"|"headcount"|"er"|"hris"

## 组织-负责人映射（根据洞察中的组织名称查找负责人）
{org_mapping if org_mapping else "（暂无组织映射数据）"}

## 用户列表（必须从以下列表中选择 target_user）
{users_info}

## 输出示例
```json
{{
  "dispatch_actions": [
    {{
      "type": "create_notification",
      "company": "{scope_label}",
      "target_user": "110031",
      "title": "[考勤]{scope_label}本月人均加班XX小时",
      "content": "2026年X月{scope_label}人均加班时长XX小时。",
      "summary": "{scope_label}加班突出",
      "priority": "high",
      "notif_type": "alert",
      "insight_level": "company",
      "insight_org": "",
      "insight_type": "attendance"
    }}
  ]
}}
```"""

            # Token 统计
            import tiktoken

            enc = tiktoken.get_encoding("cl100k_base")
            data_tables_tokens = len(enc.encode(data_tables_single))
            users_info_tokens = len(enc.encode(users_info))
            prompt_tokens = len(enc.encode(prompt))
            print(
                f"[Token统计] {company_name}: data_tables={data_tables_tokens} tokens, users_info={users_info_tokens} tokens, total_prompt={prompt_tokens} tokens"
            )

            result, success, errors = generate_insight_with_retry(
                agent, prompt, max_retries=3
            )

            insight_results[company_name] = {
                "raw_prompt": prompt,
                "raw_output": result,
                "success": success,
                "errors": errors,
            }

            if success:
                print(
                    f"[数据洞察] {company_name} 洞察生成成功（验证通过，耗时: {time.time()-company_start:.1f}s）"
                )
                # 分发通知（带查重）
                self._dispatch_insight_actions(
                    result.get("dispatch_actions", []), company_name
                )
            else:
                print(
                    f"[数据洞察] {company_name} 洞察验证失败: {errors} (耗时: {time.time()-company_start:.1f}s)"
                )

        # === 5) 二次格式检查：target_user 必须是纯工号 ===
        for company_name, data in insight_results.items():
            if not data["success"]:
                continue
            actions = data["raw_output"].get("dispatch_actions", [])
            for i, action in enumerate(actions):
                target_user = action.get("target_user", "")
                # 检查是否为纯工号（6位数字）
                if not target_user.isdigit():
                    print(
                        f"[数据洞察] {company_name} action[{i}] target_user 格式异常: "
                        f"'{target_user}'（应为纯工号，如 110031）"
                    )

        self._last_insight_date = today_str
        total_elapsed = time.time() - insight_start
        print(
            f"\n[数据洞察] ==================== 洞察流程执行完成 ===================="
        )
        print(f"[数据洞察] 总耗时: {total_elapsed:.1f}s | 处理公司数: {len(companies)}")
        print(f"[数据洞察] 洞察流程执行完成（触发来源：{data_context or '手动/全量'}）")
        return True

    def _dispatch_insight_actions(self, actions: list, company: str = ""):
        """分发洞察通知（带查重）"""
        if not actions:
            return

        from pathlib import Path

        from src.spine.dispatcher import dispatch_actions
        from src.data.insight_notifications import (
            init_insight_notifications_table,
            get_recent_notifications,
            save_insight_notification,
        )
        from src.tools.insight_dedup import check_is_duplicate
        import sqlite3

        # 初始化洞察通知记录表
        auth_db_path = Path(__file__).parent.parent.parent / "data" / "auth.db"
        conn = sqlite3.connect(str(auth_db_path))
        init_insight_notifications_table(conn)

        # 过滤掉重复通知
        filtered_actions = []
        for action in actions:
            target_user = action.get("target_user", "")
            title = action.get("title", "")
            content = action.get("content", "")
            summary = action.get("summary", title[:20] if title else "")

            # 查重：先做快速预过滤，insight_type 不同直接跳过
            insight_type = action.get("insight_type", "")
            recent_records = get_recent_notifications(conn, target_user)
            if recent_records and insight_type:
                # 快速预过滤：只检查相同 insight_type 的记录
                same_type_records = [
                    r for r in recent_records if r.get("insight_type") == insight_type
                ]
                if same_type_records:
                    # 只有相同类型的记录才需要 LLM 查重
                    if check_is_duplicate(
                        target_user, title, content, summary, same_type_records
                    ):
                        print(f"[洞察查重] 跳过重复通知: {title} -> {target_user}")
                        continue
                else:
                    print(
                        f"[洞察查重] 无相同类型历史记录，跳过查重: {title} (type={insight_type}) -> {target_user}"
                    )

            # 保存记录
            save_insight_notification(
                conn,
                target_user=target_user,
                title=title,
                content=content,
                summary=summary,
                insight_level=action.get("insight_level", ""),
                insight_org=action.get("insight_org", ""),
                insight_type=action.get("insight_type", ""),
                company=company,
            )

            filtered_actions.append(action)

        conn.close()

        if not filtered_actions:
            print("[数据洞察] 所有洞察通知均为重复，已过滤")
            return

        # 调用分派器处理过滤后的通知
        result = dispatch_actions(filtered_actions, session_id="insight-dispatch")
        print(f"[数据洞察] 分派结果: {result}")

    def _get_distinct_companies(self, dp) -> list:
        """从 DashboardDataProvider 获取公司列表"""
        dept_data = dp.get_dept_detail_data(filters={})
        if isinstance(dept_data, dict) and "data" in dept_data:
            companies = set()
            for d in dept_data["data"]:
                company = d.get("company", "").strip()
                if company:
                    companies.add(company)
            if companies:
                return sorted(companies)
        # 硬编码回退：已知两家公司
        return ["虚拟科技公司", "虚拟智联公司"]

    def _get_org_leader_mapping(self) -> str:
        """获取组织-负责人映射表

        用于注入到洞察 prompt 中，让子代理知道每个组织层级的负责人是谁。

        返回格式：
        【组织-负责人映射】
        制造一中心（center）→ 总监: 110136 张三
        总装部（department）→ 经理: 110xxx 李四
        ...
        """
        import sqlite3
        from pathlib import Path

        db_path = str(
            Path(__file__).resolve().parent.parent.parent / "data" / "auth.db"
        )
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 查询所有有 org 的管理者兼岗记录
        cursor.execute("""
            SELECT u.username, u.display_name, u.role, ur.org, ur.org_level
            FROM users u
            JOIN user_roles ur ON u.id = ur.user_id
            WHERE ur.org != ''
              AND ur.org_level IN ('center', 'department')
              AND u.status = 'active'
              AND ur.role IN ('总监', '经理', 'HRBP')
            ORDER BY 
                CASE ur.org_level WHEN 'center' THEN 1 WHEN 'department' THEN 2 END,
                ur.org, ur.org_level
        """)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return ""

        # 按 org 分组，同一组织可能有多个角色（总监+HRBP）
        org_leaders: dict[str, list[str]] = {}
        for row in rows:
            org = row["org"]
            if org not in org_leaders:
                org_leaders[org] = []
            info = (
                f"{row['org_level']} → {row['role']}: "
                f"{row['username']} {row['display_name']}"
            )
            org_leaders[org].append(info)

        lines = ["【组织-负责人映射】"]
        for org in sorted(org_leaders.keys()):
            leaders = ", ".join(org_leaders[org])
            lines.append(f"- {org} → {leaders}")

        return "\n".join(lines)

    def _get_notification_users_info(self) -> str:
        """获取需要接收洞察通知的用户信息（仅管理者和SSC团队）

        用于注入到洞察 prompt 中，帮助大脑理解组织架构和职责分工。
        """
        import sqlite3
        from pathlib import Path

        # 直接使用 auth.db 路径，设置 row_factory 以支持键访问
        db_path = str(
            Path(__file__).resolve().parent.parent.parent / "data" / "auth.db"
        )
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # 注意：specialization 字段在 users 表中，不在 user_roles 表中
        cursor.execute("""
            SELECT u.username, u.display_name, u.role, u.specialization,
                   ur.org, ur.org_level, ur.notification_scope
            FROM users u
            JOIN user_roles ur ON u.id = ur.user_id
            WHERE ur.notification_scope IN ('manager', 'ssc')
              AND u.status = 'active'
            ORDER BY 
                CASE ur.notification_scope WHEN 'manager' THEN 1 ELSE 2 END,
                u.role, ur.org
        """)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return ""

        # 按 notification_scope 分组
        managers = []
        ssc_staff = []

        for row in rows:
            # 明确标注工号，方便子代理直接复制
            info = (
                f"- 工号:{row['username']} 姓名:{row['display_name']}（{row['role']}）"
            )
            org_part = ""
            if row["org"]:
                org_part = f" @{row['org']}"
                if row["org_level"]:
                    org_part += f"（{row['org_level']}）"
            if row["specialization"]:
                org_part += f" [{row['specialization']}]"

            if row["notification_scope"] == "manager":
                managers.append(info + org_part)
            else:
                ssc_staff.append(info + org_part)

        lines = []
        if managers:
            lines.append("【管理者】")
            lines.extend(managers)
        if ssc_staff:
            lines.append("【SSC团队】")
            lines.extend(ssc_staff)

        return "\n".join(lines)

    def _gather_auth_db_stats(self) -> dict:
        """收集 auth.db 的统计指标"""
        stats = {}
        auth_conn = self._get_auth_conn()
        cur = auth_conn.cursor()

        cur.execute("SELECT COUNT(*) as cnt FROM tickets")
        stats["total_tickets"] = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM tickets WHERE status='open'")
        stats["open_tickets"] = cur.fetchone()["cnt"]

        cur.execute(
            "SELECT COUNT(*) as cnt FROM cli_tasks WHERE status IN ('dispatched', 'claimed')"
        )
        stats["pending_tasks"] = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM cli_tasks WHERE status='completed'")
        stats["completed_tasks"] = cur.fetchone()["cnt"]

        stats["registered_users"] = len(list_users())
        auth_conn.close()
        return stats

    def _gather_memory_db_stats(self) -> dict:
        """收集 ssc_memory.db 的统计指标"""
        stats = {}
        ssc_conn = get_connection()
        cur = ssc_conn.cursor()

        cur.execute("SELECT COUNT(*) as cnt FROM conversations")
        stats["event_count"] = cur.fetchone()["cnt"]

        cur.execute(
            "SELECT COUNT(*) as cnt FROM conversations WHERE date(created_at) >= date('now', '-3 days')"
        )
        stats["recent_conversations"] = cur.fetchone()["cnt"]

        # 尝试查询 memory_items 表（如果存在）
        try:
            cur.execute("SELECT COUNT(*) as cnt FROM memory_items")
            stats["item_count"] = cur.fetchone()["cnt"]
        except Exception:
            stats["item_count"] = 0
        ssc_conn.close()
        return stats

    # ---- 手动触发洞察（供管理员测试/补跑）----
    def trigger_insight(self) -> bool:
        """立即执行一次洞察（不受时间限制，即使今日已触发过也会补跑）"""
        now = datetime.now()
        self._last_insight_date = ""  # 强制允许触发
        self._last_refresh_context = "手动触发（全量扫描模式）"
        return self._run_daily_insight(now, self._last_refresh_context)

    def _create_hris_emergency_ticket(self, now: datetime, failed_items: str):
        """数据更新失败，给HRIS工程师创建紧急工单"""
        insert_task_bs(
            task_id=f"TASK-DATA-FAIL-{now.strftime('%Y%m%d%H%M%S')}",
            task_type="data_refresh",
            source="scheduler",
            target_system="HRIS",
            target_user="",
            target_role="HRIS工程师",
            payload={
                "title": f"【数据更新失败】{failed_items}更新异常",
                "description": f"每日 05:00 数据刷新失败：{failed_items}。\n系统已跳过当日洞察，需人工排查。\n\n失败时间：{now.strftime('%Y-%m-%d %H:%M')}",
                "priority": "urgent",
                "category": "数据故障",
            },
        )
        print(f"[数据更新] ⚠️ {failed_items}更新失败，已创建HRIS紧急工单")

    def _token_monitor(self):
        conn = get_connection()
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM conversations WHERE date(created_at) = ?",
            (today,),
        )
        count = cursor.fetchone()["cnt"]
        conn.close()
        if count > 500:
            print(f"[Token监控] 今日对话量较高: {count}条，建议关注")
