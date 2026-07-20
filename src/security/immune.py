"""
免疫系统 —— 硅基生物的自我保护机制

三层防御：
1. 防御层：数据质量检查（完整性、时效性、一致性）
2. 自愈层：错误修复（回溯决策链、定位错误、自动修复）
3. 能量管控：Token消耗监控
"""
from datetime import datetime


class ImmuneChecker:
    """免疫系统检查器"""

    @staticmethod
    def check_data_quality(data: dict) -> dict:
        """
        防御层：检查数据质量
        Returns: {"passed": bool, "issues": list[str]}
        """
        issues = []

        # 1. 完整性检查
        if not data.get("content") and not data.get("raw_content"):
            issues.append("内容为空")

        # 2. 长度检查
        content = data.get("content", "") or data.get("raw_content", "")
        if len(content) > 10000:
            issues.append(f"内容过长（{len(content)}字符），可能存在注入风险")

        # 3. 恶意内容检查
        suspicious_patterns = ["DROP TABLE", "DELETE FROM", "<script>", "javascript:", "eval("]
        for pattern in suspicious_patterns:
            if pattern.lower() in content.lower():
                issues.append(f"检测到可疑内容: {pattern}")

        # 4. 刷屏检查（同一条消息重复超过5次）
        if content and len(set(content.split())) < 3 and len(content) > 100:
            issues.append("检测到疑似刷屏内容")

        return {
            "passed": len(issues) == 0,
            "issues": issues,
        }

    @staticmethod
    def check_policy_timeliness(policy_refs: str) -> dict:
        """
        防御层：检查政策时效性
        Returns: {"passed": bool, "warnings": list[str]}
        """
        warnings = []
        if policy_refs:
            # 检查是否引用了过期年份的政策
            current_year = datetime.now().year
            for year in range(2020, current_year - 1):
                if str(year) in policy_refs and f"{current_year}" not in policy_refs:
                    warnings.append(f"引用了{year}年的政策，建议确认是否有更新版本")
                    break

        return {
            "passed": len(warnings) == 0,
            "warnings": warnings,
        }

    @staticmethod
    def detect_contradictions(sources: list[str]) -> dict:
        """
        防御层：多源信息矛盾检测
        简单实现：检查多个来源中是否有明显矛盾的数字
        Returns: {"has_contradiction": bool, "details": str}
        """
        # 简化实现：提取每个来源中的数字，检查是否一致
        import re
        numbers_per_source = []
        for source in sources:
            nums = re.findall(r'\d+', source)
            numbers_per_source.append(set(nums))

        # 如果多个来源的数字集合差异很大，可能存在矛盾
        if len(numbers_per_source) >= 2:
            all_nums = set()
            for s in numbers_per_source:
                all_nums.update(s)
            if len(all_nums) > 20:
                return {
                    "has_contradiction": True,
                    "details": "多个信息来源中数字差异较大，建议人工核对",
                }

        return {"has_contradiction": False, "details": ""}

    @staticmethod
    def calculate_daily_token_usage() -> dict:
        """
        能量管控：统计当日Token消耗
        MVP阶段用对话数量近似，后续替换为真实Token统计
        """
        from src.data.task_queue import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute(
            "SELECT COUNT(*) as cnt, SUM(LENGTH(content)) as total_chars FROM conversations WHERE date(created_at) = ?",
            (today,),
        )
        row = cursor.fetchone()
        conn.close()
        return {
            "date": today,
            "conversation_count": row["cnt"] if row else 0,
            "total_characters": row["total_chars"] if row and row["total_chars"] else 0,
            "estimated_tokens": (row["total_chars"] // 4) if row and row["total_chars"] else 0,
        }


class SelfHealer:
    """自愈层：错误修复"""

    @staticmethod
    def trace_decision_chain(task_id: str) -> list[dict]:
        """回溯决策链：从task_id追溯完整的事件链"""
        from src.data.task_queue import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        chain = []
        # 查找task_bs
        cursor.execute("SELECT * FROM task_bs WHERE task_id = ?", (task_id,))
        bs = cursor.fetchone()
        if bs:
            chain.append({"type": "task_bs", "data": dict(bs)})

        # 查找相关task_st
        cursor.execute("SELECT * FROM task_st WHERE parent_task_id = ?", (task_id,))
        sts = cursor.fetchall()
        for st in sts:
            chain.append({"type": "task_st", "data": dict(st)})

        # 查找相关事件
        cursor.execute(
            "SELECT * FROM event_bus WHERE payload LIKE ? ORDER BY timestamp",
            (f"%{task_id}%",),
        )
        events = cursor.fetchall()
        for evt in events:
            chain.append({"type": "event", "data": dict(evt)})

        conn.close()
        return chain

    @staticmethod
    def find_error_source(task_id: str) -> dict:
        """定位错误环节"""
        chain = SelfHealer.trace_decision_chain(task_id)

        for item in chain:
            data = item["data"]
            if data.get("status") in ("FAILED", "FAILED_FINAL", "ESCALATED"):
                return {
                    "found": True,
                    "type": item["type"],
                    "task_id": data.get("task_id"),
                    "status": data["status"],
                    "result": data.get("result"),
                }

        return {"found": False}