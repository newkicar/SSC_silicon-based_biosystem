"""
洞察数据提供者（InsightDataProvider）

职责：
1. 根据用户身份（roles + user_roles）自动推导管理范围
2. 按范围生成多粒度统计快照（公司→中心→部门，蓝领/白领分层）
3. 将结构化数据喂给 LLM 生成管理洞察

架构：
   InsightDataProvider（编排层）
        ↓ 调用
   DashboardDataProvider（计算引擎，已有）
        ↓ 读取
   Excel 数据源

权限控制：
- scope：由 RBAC 的 scope_level 决定管理范围
- deny_fields：由 RBAC 的 deny_fields 决定指标可见性
"""

from datetime import datetime
from typing import Optional

from src.tools.dashboard_data import get_dashboard_provider


class InsightDataProvider:
    """根据用户身份生成多粒度洞察数据快照"""

    # 黑名单字段：这些角色的用户不应看到某些指标
    # （由 permissions.py 的 ROLE_PERMISSIONS.deny_fields 驱动）
    DENY_FIELDS_MAP = {
        "HRBP": ["cost_rate", "cost_analysis", "salary_info"],  # 不能看薪酬/成本
        "考勤专员": ["cost_rate", "cost_analysis"],  # 不能看成本
        "招聘专员": ["cost_rate", "cost_analysis", "rank_info"],  # 不能看成本+岗级
    }

    def get_insight_context(self, user_info: dict) -> dict:
        """
        为指定用户生成完整的洞察上下文数据。

        Args:
            user_info: 当前用户信息，包含：
                - username, display_name
                - role (主角色)，roles (角色列表)
                - user_roles: [{role, org, org_level}, ...] 兼岗信息
                - department, center, company

        Returns:
            {
                "user": {...},
                "scopes": [
                    {
                        "label": "虚拟科技·白领",
                        "filters": {"company": "虚拟科技公司", "emp_type": "白领"},
                        "denied_fields": [...],
                        "kpi": {...},
                        "charts": {...},
                        "dept_detail": {...},
                    },
                    ...
                ],
                "meta": {"generated_at": "...", "scope_count": N}
            }
        """
        scopes = self._resolve_user_scopes(user_info)
        denied = self._get_denied_fields(user_info)

        dp = get_dashboard_provider()
        result_scopes = []

        for scope in scopes:
            filters = scope["filters"]
            # 生成当前月份（取最新可用月份）
            latest_month = self._resolve_month(filters, dp)

            scope_data = {
                "label": scope["label"],
                "filters": filters,
                "denied_fields": [
                    d for d in denied if self._is_field_in_scope(d, scope)
                ],
            }

            # KPI 快照
            try:
                scope_data["kpi"] = dp._compute_kpi(filters)
            except Exception as e:
                scope_data["kpi"] = {"error": str(e)}

            # 结构分布（性别/学历/年龄/工龄/职级）
            try:
                scope_data["charts"] = dp._compute_charts(filters)
            except Exception as e:
                scope_data["charts"] = {"error": str(e)}

            # 部门明细（人头/离职率/出勤率/加班/HC率/成本率）
            try:
                scope_data["dept_detail"] = dp._compute_dept_detail(filters)
            except Exception as e:
                scope_data["dept_detail"] = {"error": str(e)}

            # 成本分析（对有权看的用户）
            if "cost_rate" not in denied and "cost_analysis" not in denied:
                try:
                    scope_data["cost_analysis"] = dp._compute_cost_analysis(filters)
                except Exception as e:
                    scope_data["cost_analysis"] = {"error": str(e)}

            # 效能指标（仅全公司级别，过滤掉部门级切片）
            if not filters.get("center") and not filters.get("department"):
                if "salary_info" not in denied:
                    try:
                        scope_data["efficiency"] = dp._compute_efficiency(filters)
                    except Exception as e:
                        scope_data["efficiency"] = {"error": str(e)}

            result_scopes.append(scope_data)

        return {
            "user": {
                "display_name": user_info.get("display_name", ""),
                "username": user_info.get("username", ""),
                "roles": self._extract_role_names(user_info),
            },
            "scopes": result_scopes,
            "meta": {
                "generated_at": datetime.now().isoformat(),
                "scope_count": len(result_scopes),
            },
        }

    def _resolve_user_scopes(self, user_info: dict) -> list:
        """
        根据用户角色推导管理范围，返回 filters 列表。

        逻辑：
        1. 从 user_roles 获取所有角色及其组织范围
        2. 对每个 (角色, org) 生成初始 filters
        3. 对有 scope_level=company 的角色，生成全公司 filters
        4. 对 scope_level=per_role 的角色，按 org_level 展开
        5. 对每个范围，尝试拆分为 全部/蓝领/白领 三个子切片

        Returns:
            [{"label": "虚拟科技公司", "filters": {"company": "虚拟科技公司"}}, ...]
        """
        scopes = []
        seen_keys = set()

        user_roles = user_info.get("user_roles", [])
        if not user_roles:
            # 兼容旧式单角色用户
            role = user_info.get("role", "")
            dept = user_info.get("department", "")
            if role:
                user_roles = [{"role": role, "org": dept, "org_level": "department"}]

        for ur in user_roles:
            role_name = ur.get("role", "")
            org = ur.get("org", "").strip()
            org_level = ur.get("org_level", "department")

            # 从 permissions 获取 scope_level（简化判断：已知角色映射）
            scope_level = self._get_scope_level(role_name)

            if scope_level == "company":
                # 全公司级别
                base_filters = {}
                self._add_scope(scopes, seen_keys, "全公司", base_filters)
                self._add_scope(
                    scopes,
                    seen_keys,
                    "全公司·白领",
                    {**base_filters, "emp_type": "白领"},
                )
                self._add_scope(
                    scopes,
                    seen_keys,
                    "全公司·蓝领",
                    {**base_filters, "emp_type": "蓝领"},
                )

            elif scope_level == "per_role":
                if not org:
                    continue  # 没有组织范围，跳过

                if org_level == "center":
                    # 中心级：该中心 + 下属各部门
                    base_filters = {"center": org}
                    self._add_scope(scopes, seen_keys, org, base_filters)
                    self._add_scope(
                        scopes,
                        seen_keys,
                        f"{org}·白领",
                        {**base_filters, "emp_type": "白领"},
                    )
                    self._add_scope(
                        scopes,
                        seen_keys,
                        f"{org}·蓝领",
                        {**base_filters, "emp_type": "蓝领"},
                    )

                    # 尝试获取该中心下的部门列表，生成部门级子切片
                    try:
                        dp = get_dashboard_provider()
                        dept_detail = dp._compute_dept_detail(base_filters)
                        departments = dept_detail.get("departments", [])
                        for dept in departments:
                            dept_filters = {**base_filters, "department": dept}
                            self._add_scope(
                                scopes, seen_keys, f"{org}·{dept}", dept_filters
                            )
                    except Exception:
                        pass  # 部门明细获取失败，跳过子切片

                elif org_level == "department":
                    base_filters = {"department": org}
                    self._add_scope(scopes, seen_keys, org, base_filters)
                    self._add_scope(
                        scopes,
                        seen_keys,
                        f"{org}·白领",
                        {**base_filters, "emp_type": "白领"},
                    )
                    self._add_scope(
                        scopes,
                        seen_keys,
                        f"{org}·蓝领",
                        {**base_filters, "emp_type": "蓝领"},
                    )

        # 如果没有任何 scope（极端情况），回退到全公司
        if not scopes:
            self._add_scope(scopes, seen_keys, "全公司", {})

        return scopes

    def _add_scope(self, scopes, seen_keys, label, filters):
        """去重添加 scope"""
        key = f"{label}|{self._filters_key(filters)}"
        if key not in seen_keys:
            seen_keys.add(key)
            scopes.append({"label": label, "filters": filters})

    @staticmethod
    def _filters_key(filters: dict) -> str:
        """生成 filters 的唯一标识"""
        return "|".join(f"{k}={v}" for k, v in sorted(filters.items()) if v)

    @staticmethod
    def _get_scope_level(role_name: str) -> str:
        """
        获取角色的 scope_level。
        简化版映射，完整版见 permissions.py 的 ROLE_PERMISSIONS。
        """
        company_roles = {"总经理", "副总经理", "HR SSC经理"}
        center_roles = {"总监", "考勤专员"}  # 总监按 per_role，考勤专员也可能有中心级
        dept_roles = {"经理"}

        if role_name in company_roles:
            return "company"
        if role_name in center_roles:
            return "per_role"
        if role_name in dept_roles:
            return "per_role"
        # 其他角色（专员等）：按 user_roles 中的 org 决定
        return "per_role"

    def _get_denied_fields(self, user_info: dict) -> list:
        """获取当前用户被禁止查看的字段列表"""
        denied_set = set()
        user_roles = user_info.get("user_roles", [])
        for ur in user_roles:
            role_name = ur.get("role", "")
            fields = self.DENY_FIELDS_MAP.get(role_name, [])
            denied_set.update(fields)
        # 也检查主角色
        main_role = user_info.get("role", "")
        if main_role:
            fields = self.DENY_FIELDS_MAP.get(main_role, [])
            denied_set.update(fields)
        return list(denied_set)

    @staticmethod
    def _is_field_in_scope(field: str, scope: dict) -> bool:
        """判断某字段是否与当前 scope 相关"""
        # 薪酬字段仅在含成本分析的 scope 有影响
        if field in ("cost_rate", "cost_analysis", "salary_info"):
            return True
        # 岗级信息
        if field == "rank_info":
            return True
        return True

    @staticmethod
    def _resolve_month(filters: dict, dp) -> Optional[str]:
        """确定该 scope 的最新可用月份"""
        try:
            avail = dp.get_available_months()
            if avail:
                return avail[0]  # 最新可用月份
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_role_names(user_info: dict) -> list:
        """提取用户所有角色名称"""
        user_roles = user_info.get("user_roles", [])
        roles = [ur.get("role", "") for ur in user_roles]
        main_role = user_info.get("role", "")
        if main_role and main_role not in roles:
            roles.append(main_role)
        return [r for r in roles if r]

    def format_insight_for_llm(self, user_info: dict) -> str:
        """
        将洞察数据格式化为 LLM 友好的自然语言描述。

        供 scheduler 或 API 调用，直接生成可塞入 prompt 的数据上下文。
        """
        context = self.get_insight_context(user_info)

        lines = []
        lines.append(f"用户: {context['user']['display_name']}")
        lines.append(f"角色: {', '.join(context['user']['roles'])}")
        lines.append(f"管理范围数: {len(context['scopes'])}")
        lines.append("")

        for i, scope in enumerate(context["scopes"], 1):
            scope_label = scope["label"]
            denied = scope.get("denied_fields", [])
            denied_note = f" (不可见字段: {', '.join(denied)})" if denied else ""

            lines.append(f"--- 切片{i}: {scope_label}{denied_note} ---")

            # KPI 快照
            kpi = scope.get("kpi", {})
            if isinstance(kpi, dict) and "error" not in kpi:
                lines.append(f"  在职人数: {kpi.get('headcount', 'N/A')}")
                lines.append(f"  预算编制: {kpi.get('budget', 'N/A')}")
                lines.append(f"  白领人数: {kpi.get('white_collar', 'N/A')}")
                lines.append(f"  蓝领人数: {kpi.get('blue_collar', 'N/A')}")
                if "cost_rate" not in denied:
                    lines.append(f"  成本使用率: {kpi.get('cost_rate', 'N/A')}%")
                if "salary_info" not in denied:
                    lines.append(f"  人均薪酬: {kpi.get('avg_salary', 'N/A')}")
                lines.append(f"  已招聘入职: {kpi.get('hired_count', 'N/A')}")
                lines.append(f"  空缺岗位: {kpi.get('pending_recruit', 'N/A')}")

            # 结构分布摘要
            charts = scope.get("charts", {})
            if isinstance(charts, dict) and "error" not in charts:
                gender = charts.get("gender_dist", [])
                if gender:
                    gender_str = ", ".join(
                        f"{g.get('name','?')}:{g.get('value',0)}人" for g in gender[:3]
                    )
                    lines.append(f"  性别分布(top3): {gender_str}")

                age = charts.get("age_dist", [])
                if age:
                    age_str = ", ".join(
                        f"{a.get('name','?')}:{a.get('value',0)}人" for a in age[:3]
                    )
                    lines.append(f"  年龄分布(top3): {age_str}")

                edu = charts.get("edu_dist", [])
                if edu:
                    edu_str = ", ".join(
                        f"{e.get('name','?')}:{e.get('value',0)}人" for e in edu[:3]
                    )
                    lines.append(f"  学历分布(top3): {edu_str}")

            # 部门明细摘要
            dept = scope.get("dept_detail", {})
            if isinstance(dept, dict) and "error" not in dept:
                dept_data = dept.get("data", [])
                if dept_data:
                    # 摘取离职率/加班最高部门
                    dept_with_turnover = [
                        d for d in dept_data if d.get("turnover_rate") is not None
                    ]
                    if dept_with_turnover:
                        top_turnover = max(
                            dept_with_turnover, key=lambda x: x["turnover_rate"] or 0
                        )
                        lines.append(
                            f"  最高离职率部门: {top_turnover['dept']}({top_turnover['turnover_rate']}%)"
                        )

                    dept_with_ot = [
                        d
                        for d in dept_data
                        if d.get("overtime_hours") is not None
                        and d["overtime_hours"] > 0
                    ]
                    if dept_with_ot:
                        top_ot = max(
                            dept_with_ot, key=lambda x: x["overtime_hours"] or 0
                        )
                        lines.append(
                            f"  最高加班部门: {top_ot['dept']}({top_ot['overtime_hours']}小时)"
                        )

            lines.append("")

        return "\n".join(lines)

    # ================================================================
    # 企业级洞察（系统层，无具体用户）
    # ================================================================

    def get_enterprise_insight(
        self,
        dp: "DashboardDataProvider",
        auth_db_stats: Optional[dict] = None,
        memory_db_stats: Optional[dict] = None,
        company: Optional[str] = None,
    ) -> dict:
        """
        企业级全量洞察快照 —— 供 scheduler 等系统层调用。

        遍历组织架构中所有公司→中心→部门的切片，生成多粒度统计，
        同时聚合 auth.db 和 ssc_memory.db 中的系统运行指标。

        Args:
            dp: DashboardDataProvider 实例（计算引擎）
            auth_db_stats: auth.db 统计数据（ticket 数量等）
            memory_db_stats: ssc_memory.db 统计数据（事件/记忆数量等）
            company: 可选，限定某家公司（如 "虚拟科技公司" 或 "虚拟智联公司"）。
                     传 None 为全公司合并数据。

        Returns:
            {
                "timestamp": str,
                "company": str | None,  # 公司过滤条件（None=全公司合并）
                "system": { ... },
                "headcount": { ... },
                "cost": { ... },
                "turnover": { ... },
                "overtime_top_centers": list,
                "dept_highlights": list,
                "month": str,
            }
        """
        result = {
            "timestamp": datetime.now().isoformat(),
            "company": company,
            "system": {},
            "headcount": {},
            "cost": {},
            "turnover": {},
            "overtime_top_centers": [],
            "dept_highlights": [],
            "month": self._resolve_month({"company": company} if company else {}, dp)
            or "2026-06",
        }

        # === 系统运行指标（不按公司过滤，始终全系统） ===
        system = auth_db_stats or {}
        memory = memory_db_stats or {}
        result["system"] = {
            "total_tickets": system.get("total_tickets", 0),
            "open_tickets": system.get("open_tickets", 0),
            "completed_tasks": system.get("completed_tasks", 0),
            "registered_users": system.get("registered_users", 0),
            "memory_events": memory.get("event_count", 0),
            "memory_items": memory.get("item_count", 0),
        }

        month = result["month"]

        # 构建过滤条件：若指定 company，传递给各 dp 方法按公司过滤
        base_filters = {"month": month}
        if company:
            base_filters["company"] = company

        # === KPI（人头 + 成本） ===
        try:
            kpi = dp.get_kpi_data(filters=base_filters)
            if isinstance(kpi, dict) and "headcount" in kpi:
                hc = kpi["headcount"]
                result["headcount"] = {
                    "current": hc.get("current", 0),
                    "budget": hc.get("budget", 0),
                    "white_collar": hc.get("white_collar", 0),
                    "blue_collar": hc.get("blue_collar", 0),
                }
            if isinstance(kpi, dict) and "cost" in kpi:
                cost = kpi["cost"]
                result["cost"] = {
                    "rate": cost.get("ratio", 0),
                    "actual": cost.get("actual", 0),
                    "budget": cost.get("budget", 0),
                }
        except Exception as e:
            result["headcount"] = {"error": str(e)[:200]}
            result["cost"] = {"error": str(e)[:200]}

        # === 离职率 ===
        try:
            eff_data = dp.get_efficiency_data(filters=base_filters)
            if isinstance(eff_data, dict) and "turnover" in eff_data:
                result["turnover"]["categories"] = eff_data["turnover"]
        except Exception as e:
            result["turnover"] = {"error": str(e)[:200]}

        # === 加班 Top 中心 ===
        try:
            ot_data = dp.get_overtime_data(filters=base_filters)
            if isinstance(ot_data, dict) and "center" in ot_data:
                names = ot_data["center"].get("names", [])
                values = ot_data["center"].get("values", [])
                result["overtime_top_centers"] = [
                    {"name": n, "avg_hours": v} for n, v in zip(names[:5], values[:5])
                ]
        except Exception:
            pass

        # === 各部门明细 ===
        try:
            dept_data = dp.get_dept_detail_data(filters=base_filters)
            if isinstance(dept_data, dict) and "data" in dept_data:
                # 按离职率降序排列，取前20个部门
                sorted_depts = sorted(
                    dept_data["data"],
                    key=lambda d: d.get("turnover_rate") or 0,
                    reverse=True,
                )
                result["dept_highlights"] = sorted_depts[:20]
        except Exception:
            pass

        return result

    def format_enterprise_insight_for_llm(self, insight: dict) -> str:
        """
        将企业级洞察数据格式化为 LLM 可直接使用的数据表。

        Args:
            insight: get_enterprise_insight() 的返回值

        Returns:
            格式化的自然语言文本块，可直接拼接到 system/user prompt 中。
        """
        lines = []
        company_label = insight.get("company")
        title_prefix = f"【{company_label}】" if company_label else "【全公司合并】"
        lines.append(f"## {title_prefix} 当前系统运行数据快照")
        lines.append(f"数据截止月份: {insight.get('month', 'N/A')}")
        lines.append(f"快照生成时间: {insight.get('timestamp', 'N/A')}")
        lines.append("")
        lines.append(
            "【请基于下列数据表进行洞察分析，输出自然语言描述，禁止输出 JSON】"
        )
        lines.append("")

        # 系统运行指标
        sys = insight.get("system", {})
        lines.append("### 系统运行指标")
        lines.append(
            f"| 指标 | 数值 |\n"
            f"|------|------|\n"
            f"| 待处理工单 | {sys.get('open_tickets', 0)} (总量: {sys.get('total_tickets', 0)}) |\n"
            f"| 已完成任务 | {sys.get('completed_tasks', 0)} |\n"
            f"| 注册用户 | {sys.get('registered_users', 0)} |\n"
            f"| 系统事件 | {sys.get('memory_events', 0)} |\n"
            f"| 记忆条目 | {sys.get('memory_items', 0)} |"
        )
        lines.append("")

        # 人头
        hc = insight.get("headcount", {})
        if "error" not in hc:
            lines.append("### 全公司在职人数")
            lines.append(
                f"| 指标 | 数值 |\n"
                f"|------|------|\n"
                f"| 在职总人数 | {hc.get('current', 0)} |\n"
                f"| 预算编制 | {hc.get('budget', 0)} |\n"
                f"| 白领 | {hc.get('white_collar', 0)} |\n"
                f"| 蓝领 | {hc.get('blue_collar', 0)} |"
            )
            lines.append("")

        # 成本
        cost = insight.get("cost", {})
        if "error" not in cost:
            lines.append("### 公司级成本使用率")
            lines.append(
                f"| 指标 | 数值 |\n"
                f"|------|------|\n"
                f"| 成本使用率 | {cost.get('rate', 0)}% |\n"
                f"| 累积实际成本 | {cost.get('actual', 0)} |\n"
                f"| 累积预算成本 | {cost.get('budget', 0)} |"
            )
            lines.append("")

        # 离职率
        turnover = insight.get("turnover", {})
        if "error" not in turnover:
            cats = turnover.get("categories", {})
            if cats:
                lines.append("### 离职率（4类）")
                header = "| 类别 | 实际 | 预算 |"
                sep = "|------|------|------|"
                rows = []
                for cat_name, cat_data in cats.items():
                    actual = (
                        cat_data.get("actual") if isinstance(cat_data, dict) else "N/A"
                    )
                    budget = (
                        cat_data.get("budget") if isinstance(cat_data, dict) else "N/A"
                    )
                    rows.append(f"| {cat_name} | {actual} | {budget} |")
                lines.extend([header, sep] + rows if rows else [header, sep])
                lines.append("")

        # 加班 Top 中心
        ot = insight.get("overtime_top_centers", [])
        if ot:
            lines.append("### 加班最高的前5中心")
            lines.append("| 排名 | 中心 | 人均加班(h) |")
            lines.append("|------|------|------|")
            for i, item in enumerate(ot, 1):
                lines.append(f"| {i} | {item['name']} | {item['avg_hours']} |")
            lines.append("")

        # 部门明细表（取关键列）
        depts = insight.get("dept_highlights", [])
        if depts:
            lines.append("### 各部门关键指标（按离职率降序，前20）")
            header = "| 部门 | 中心 | 在职 | 离职率% | 出勤率% | 人均加班(h) | HC使用率% | 成本使用率% | 空缺岗位 |"
            sep = "|------|------|------|------|------|------|------|------|------|"
            rows = []
            for d in depts:
                dept_name = d.get("dept", "?")
                center_name = d.get("center", "?")
                hc_val = d.get("headcount", 0)
                turnover_rate = d.get("turnover_rate") or 0
                attendance = d.get("attendance") or 0
                ot_hours = d.get("overtime_hours") or 0
                hc_rate = d.get("hc_rate") or 0
                cost_rate = d.get("cost_rate") or 0
                pending = d.get("pending_recruit", 0)
                rows.append(
                    f"| {dept_name} | {center_name} | {hc_val} | "
                    f"{turnover_rate} | {attendance} | {ot_hours} | "
                    f"{hc_rate} | {cost_rate} | {pending} |"
                )
            lines.extend([header, sep] + rows)
            lines.append("")

        return "\n".join(lines)


# 全局实例
_insight_provider = None


def get_insight_provider() -> InsightDataProvider:
    """获取 InsightDataProvider 全局单例"""
    global _insight_provider
    if _insight_provider is None:
        _insight_provider = InsightDataProvider()
    return _insight_provider
