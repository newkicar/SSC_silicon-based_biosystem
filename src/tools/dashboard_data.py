"""
Dashboard数据源 —— 读取 databases/ 目录下所有Excel文件
为门户前端提供KPI卡片、切片筛选、图表数据
"""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path
import openpyxl

DB_DIR = Path(__file__).resolve().parent.parent.parent / "databases"


def _load_sheet(file_name: str, sheet_name: str) -> tuple[list, list]:
    """加载Excel的指定sheet，返回(headers, rows)"""
    fpath = DB_DIR / file_name
    if not fpath.exists():
        return [], []
    try:
        wb = openpyxl.load_workbook(str(fpath), read_only=True, data_only=True)
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        if not rows:
            return [], []
        headers = [str(c).strip() if c else f"col_{i}" for i, c in enumerate(rows[0])]
        return headers, rows[1:]
    except Exception as e:
        print(f"[Dashboard] 加载失败 {file_name}/{sheet_name}: {e}")
        return [], []


def _row_to_dict(headers: list, row: tuple) -> dict:
    """将一行数据转为字典"""
    d = {}
    for i, val in enumerate(row):
        key = headers[i] if i < len(headers) else f"col_{i}"
        d[key] = val
    return d


class DashboardDataProvider:
    """Dashboard数据提供器"""

    def __init__(self):
        self._cache = {}
        self._cache_time = {}
        self._result_cache = {}  # API结果缓存
        self._result_cache_time = {}

    def _get_cache(self, key: str, loader, ttl=3600):
        """带TTL的缓存（默认1小时）"""
        now = datetime.now().timestamp()
        if key in self._cache and (now - self._cache_time.get(key, 0)) < ttl:
            return self._cache[key]
        data = loader()
        self._cache[key] = data
        self._cache_time[key] = now
        return data

    def _get_result_cache(self, key: str, loader, ttl=1800):
        """API结果级缓存（默认30分钟）"""
        now = datetime.now().timestamp()
        if (
            key in self._result_cache
            and (now - self._result_cache_time.get(key, 0)) < ttl
        ):
            return self._result_cache[key]
        data = loader()
        self._result_cache[key] = data
        self._result_cache_time[key] = now
        return data

    def _filters_key(self, filters: dict = None) -> str:
        """将filters转为缓存key"""
        if not filters:
            return "default"
        return "|".join(f"{k}={v}" for k, v in sorted(filters.items()))

    def _load_roster(self):
        """加载花名册"""

        def loader():
            headers, rows = _load_sheet("员工花名册.xlsx", "花名册")
            return [_row_to_dict(headers, r) for r in rows if r and len(r) > 5]

        return self._get_cache("roster", loader)

    def _load_budget(self):
        """加载人数预算"""

        def loader():
            headers, rows = _load_sheet("员工花名册.xlsx", "人数预算")
            return [_row_to_dict(headers, r) for r in rows if r]

        return self._get_cache("budget", loader)

    def _load_recruitment(self):
        """加载待招岗位需求"""

        def loader():
            headers, rows = _load_sheet("待招岗位需求.xlsx", "Sheet1")
            return [_row_to_dict(headers, r) for r in rows if r]

        return self._get_cache("recruitment", loader)

    def _load_cost_budget(self):
        """加载人工成本预算"""

        def loader():
            headers, rows = _load_sheet("各中心部门人工成本.xlsx", "人工成本预算")
            return [_row_to_dict(headers, r) for r in rows if r]

        return self._get_cache("cost_budget", loader)

    def _load_cost_actual(self):
        """加载实际成本"""

        def loader():
            headers, rows = _load_sheet("各中心部门人工成本.xlsx", "实际发生的成本")
            return [_row_to_dict(headers, r) for r in rows if r]

        return self._get_cache("cost_actual", loader)

    def _load_efficiency_actual(self):
        """加载人效实际数据"""

        def loader():
            headers, rows = _load_sheet("人效数据-公司级.xlsx", "人效实际")
            return [_row_to_dict(headers, r) for r in rows if r]

        return self._get_cache("eff_actual", loader)

    def _load_efficiency_budget(self):
        """加载人效预算数据"""

        def loader():
            headers, rows = _load_sheet("人效数据-公司级.xlsx", "人效预算")
            return [_row_to_dict(headers, r) for r in rows if r]

        return self._get_cache("eff_budget", loader)

    def _load_turnover_actual(self):
        """加载离职率实际数据"""

        def loader():
            headers, rows = _load_sheet(
                "离职率数据.xlsx", "离职率（公司中心部门）-实际"
            )
            return [_row_to_dict(headers, r) for r in rows if r]

        return self._get_cache("turnover_actual", loader)

    def _load_turnover_budget(self):
        """加载离职率预算数据"""

        def loader():
            headers, rows = _load_sheet("离职率数据.xlsx", "离职率（公司）-预算")
            return [_row_to_dict(headers, r) for r in rows if r]

        return self._get_cache("turnover_budget", loader)

    def _load_org_structure(self):
        """加载组织架构"""

        def loader():
            headers, rows = _load_sheet("元数据-公司组织架构.xlsx", "Sheet1")
            return [_row_to_dict(headers, r) for r in rows if r]

        return self._get_cache("org", loader)

    def _load_overtime_df(self):
        """加载考勤基础数据（pandas DataFrame，带缓存）"""
        import pandas as pd

        def loader():
            fpath = DB_DIR / "考勤基础数据.xlsx"
            if not fpath.exists():
                return None
            df = pd.read_excel(str(fpath), dtype=str)
            # 清洗关键列
            df["考勤年份_int"] = (
                df["考勤年份"].str.replace("年", "", regex=False).str.strip()
            )
            df["考勤年份_int"] = (
                pd.to_numeric(df["考勤年份_int"], errors="coerce").fillna(0).astype(int)
            )
            df["考勤月份_int"] = (
                pd.to_numeric(df["考勤月份"], errors="coerce").fillna(0).astype(int)
            )
            df["当日考勤时长_num"] = pd.to_numeric(
                df["当日考勤时长"], errors="coerce"
            ).fillna(0.0)
            df["员工编号_str"] = df["员工编号"].astype(str).str.strip()
            # 考勤日期标准化为 YYYY-MM 格式
            df["考勤日期_ym"] = (
                df["考勤年份_int"].astype(str)
                + "-"
                + df["考勤月份_int"].astype(str).str.zfill(2)
            )
            return df

        return self._get_cache("overtime_df", loader, ttl=600)

    def get_available_months(self) -> list:
        """从考勤基础数据的考勤日期列获取所有可用月份（去重、降序）"""
        cache_key = "available_months"

        def loader():
            ot_df = self._load_overtime_df()
            if ot_df is None or ot_df.empty:
                return []
            months = sorted(ot_df["考勤日期_ym"].unique().tolist(), reverse=True)
            return months

        return self._get_cache(cache_key, loader, ttl=300)

    def _is_active(self, record: dict) -> bool:
        """判断员工是否在职（无离职日期）"""
        val = record.get("离职日期")
        return val is None or str(val).strip() in ("", "None", "NaT")

    def _get_filter_options(self, filters: dict = None) -> dict:
        """获取切片筛选选项（支持级联过滤）"""
        org = self._load_org_structure()
        roster = self._load_roster()

        company = (filters or {}).get("company", "")
        center = (filters or {}).get("center", "")
        department = (filters or {}).get("department", "")

        # 公司选项：始终从组织架构获取
        companies = sorted(
            set(str(r.get("公司", "")).strip() for r in org if r.get("公司"))
        )

        # 中心选项：按公司过滤
        if company:
            centers = sorted(
                set(
                    str(r.get("中心", "")).strip()
                    for r in org
                    if str(r.get("公司", "")).strip() == company and r.get("中心")
                )
            )
        else:
            centers = sorted(
                set(str(r.get("中心", "")).strip() for r in org if r.get("中心"))
            )

        # 部门选项：按公司+中心过滤
        dept_filtered = org
        if company:
            dept_filtered = [
                r for r in dept_filtered if str(r.get("公司", "")).strip() == company
            ]
        if center:
            dept_filtered = [
                r for r in dept_filtered if str(r.get("中心", "")).strip() == center
            ]
        departments = sorted(
            set(str(r.get("部门", "")).strip() for r in dept_filtered if r.get("部门"))
        )

        # 人员类型选项：按公司+中心+部门过滤（从花名册）
        roster_filtered = [r for r in roster if self._is_active(r)]
        if company:
            roster_filtered = [
                r for r in roster_filtered if str(r.get("公司", "")).strip() == company
            ]
        if center:
            roster_filtered = [
                r for r in roster_filtered if str(r.get("中心", "")).strip() == center
            ]
        if department:
            roster_filtered = [
                r
                for r in roster_filtered
                if str(r.get("部门", "")).strip() == department
            ]
        emp_types = sorted(
            set(
                str(r.get("蓝领白领", "")).strip()
                for r in roster_filtered
                if r.get("蓝领白领")
            )
        )

        # 从考勤基础数据的"考勤日期"列获取可用月份（最频繁更新的数据表）
        months = self.get_available_months()

        return {
            "companies": companies,
            "centers": centers,
            "departments": departments,
            "emp_types": emp_types,
            "months": months,
        }

    def _filter_roster(self, filters: dict = None) -> list:
        """按条件过滤花名册。
        如果指定了month，按入职时间/离职日期计算该月在职人数。
        """
        all_roster = self._load_roster()
        month = (filters or {}).get("month", "")

        if month:
            # 按月计算在职：
            #   入职时间 <= 该月最后一天（含当月最后一天入职的）
            #   离职日期 > 该月最后1天 或 为空（即当月未离职）
            parts = month.split("-")
            if len(parts) == 2:
                y, m = int(parts[0]), int(parts[1])
                month_start = datetime(y, m, 1)  # 该月第1天
                # 该月最后1天 = 下月第1天 - 1秒
                if m == 12:
                    month_end_exclusive = datetime(y + 1, 1, 1)
                else:
                    month_end_exclusive = datetime(y, m + 1, 1)

                def _in_month(rec):
                    hire = rec.get("入职时间")
                    leave = rec.get("离职日期")
                    # 入职时间 <= 该月最后一天（含）
                    hire_dt = _parse_date(hire)
                    if hire_dt is None:
                        return False
                    if hire_dt > month_end_exclusive - timedelta(days=1):
                        return False
                    # 离职日期为空 或 离职日期 > 该月最后1天
                    if leave and str(leave).strip() not in ("", "None", "NaT"):
                        leave_dt = _parse_date(leave)
                        if (
                            leave_dt is not None
                            and leave_dt <= month_end_exclusive - timedelta(days=1)
                        ):
                            return False
                    return True

                data = [r for r in all_roster if _in_month(r)]
            else:
                data = [r for r in all_roster if self._is_active(r)]
        else:
            data = [r for r in all_roster if self._is_active(r)]

        if not filters:
            return data

        company = filters.get("company", "")
        center = filters.get("center", "")
        department = filters.get("department", "")
        emp_type = filters.get("emp_type", "")

        if company:
            data = [r for r in data if str(r.get("公司", "")).strip() == company]
        if center:
            data = [r for r in data if str(r.get("中心", "")).strip() == center]
        if department:
            data = [r for r in data if str(r.get("部门", "")).strip() == department]
        if emp_type:
            data = [r for r in data if str(r.get("蓝领白领", "")).strip() == emp_type]

        return data

    def _filter_budget(self, filters: dict = None) -> list:
        """按条件过滤人数预算（支持蓝领白领筛选）"""
        data = self._load_budget()
        if not filters:
            return data

        company = filters.get("company", "")
        center = filters.get("center", "")
        department = filters.get("department", "")
        month = filters.get("month", "")
        emp_type = filters.get("emp_type", "")

        if company:
            data = [r for r in data if str(r.get("公司", "")).strip() == company]
        if center:
            data = [r for r in data if str(r.get("中心", "")).strip() == center]
        if department:
            data = [r for r in data if str(r.get("部门", "")).strip() == department]
        if emp_type:
            data = [r for r in data if str(r.get("蓝领白领", "")).strip() == emp_type]
        if month:
            # month格式: "2026-01"
            parts = month.split("-")
            if len(parts) == 2:
                m = int(parts[1])
                data = [r for r in data if _safe_int(r.get("月份")) == m]

        return data

    def get_kpi_data(self, filters: dict = None) -> dict:
        """获取KPI卡片数据（带结果缓存）"""
        cache_key = f"kpi|{self._filters_key(filters)}"
        return self._get_result_cache(cache_key, lambda: self._compute_kpi(filters))

    def _compute_kpi(self, filters=None):
        """实际计算KPI数据"""

        # === 1. 在职总人数 ===
        active_roster = self._filter_roster(filters)
        current_headcount = len(active_roster)

        # 管控人数（从人数预算，默认取最新月份12月）
        budget_filters = dict(filters) if filters else {}
        if not budget_filters.get("month"):
            budget_filters["month"] = "2026-12"  # 默认最新月
        budget_data = self._filter_budget(budget_filters if budget_filters else None)
        budget_headcount = sum(_safe_float(r.get("人头预算")) for r in budget_data)
        headcount_diff = current_headcount - budget_headcount
        headcount_ratio = (
            (current_headcount / budget_headcount - 1) * 100
            if budget_headcount > 0
            else 0
        )

        # 按蓝领白领分
        white_collar = len(
            [r for r in active_roster if str(r.get("蓝领白领", "")).strip() == "白领"]
        )
        blue_collar = len(
            [r for r in active_roster if str(r.get("蓝领白领", "")).strip() == "蓝领"]
        )

        # === 2. 招聘岗位数量（白领） ===
        recruitment = self._load_recruitment()
        if filters:
            company = filters.get("company", "")
            center = filters.get("center", "")
            department = filters.get("department", "")
            if company:
                recruitment = [
                    r for r in recruitment if str(r.get("公司", "")).strip() == company
                ]
            if center:
                recruitment = [
                    r for r in recruitment if str(r.get("中心", "")).strip() == center
                ]
            if department:
                recruitment = [
                    r
                    for r in recruitment
                    if str(r.get("部门", "")).strip() == department
                ]

        recruit_total = sum(_safe_int(r.get("招聘数量")) for r in recruitment)
        recruit_hired = len(
            [r for r in recruitment if str(r.get("是否入职", "")).strip() == "是"]
        )
        recruit_pending = recruit_total - recruit_hired

        # === 3. 累积成本使用率（按公司/中心/部门/月份过滤） ===
        cost_budget_all = self._load_cost_budget()
        cost_actual_all = self._load_cost_actual()

        # 按公司/中心/部门过滤成本数据
        company = (filters or {}).get("company", "")
        center = (filters or {}).get("center", "")
        department = (filters or {}).get("department", "")

        cost_budget_filtered = cost_budget_all
        cost_actual_filtered = cost_actual_all
        if company:
            cost_budget_filtered = [
                r
                for r in cost_budget_filtered
                if str(r.get("公司", "")).strip() == company
            ]
            cost_actual_filtered = [
                r
                for r in cost_actual_filtered
                if str(r.get("公司", "")).strip() == company
            ]
        if center:
            cost_budget_filtered = [
                r
                for r in cost_budget_filtered
                if str(r.get("中心", "")).strip() == center
            ]
            cost_actual_filtered = [
                r
                for r in cost_actual_filtered
                if str(r.get("中心", "")).strip() == center
            ]
        if department:
            cost_budget_filtered = [
                r
                for r in cost_budget_filtered
                if str(r.get("部门", "")).strip() == department
            ]
            cost_actual_filtered = [
                r
                for r in cost_actual_filtered
                if str(r.get("部门", "")).strip() == department
            ]
        # Note: 不支持emp_type切片（实际成本表无蓝领白领列）

        # 获取最新月份（从过滤后的实际成本数据）
        if filters and filters.get("month"):
            latest_parts = filters["month"].split("-")
        else:
            max_year = 0
            max_month = 0
            for r in cost_actual_filtered:
                y = _safe_int(r.get("年份"))
                m = _safe_int(r.get("月份"))
                if y > max_year or (y == max_year and m > max_month):
                    max_year = y
                    max_month = m
            latest_parts = [str(max_year), str(max_month).zfill(2)]

        if len(latest_parts) >= 2:
            target_year = int(float(latest_parts[0]))
            target_month = int(float(latest_parts[1]))
        else:
            target_year = datetime.now().year
            target_month = datetime.now().month

        # 预算成本（累积到target_month）
        budget_cost = 0
        for r in cost_budget_filtered:
            y = _safe_int(r.get("年份"))
            m = _safe_int(r.get("月份"))
            if y == target_year and m <= target_month:
                budget_cost += _safe_float(r.get("计入费用职工薪酬总额"))

        # 实际成本（累积）
        actual_cost = 0
        cost_col = (
            "成本"
            if "成本"
            in (cost_actual_filtered[0].keys() if cost_actual_filtered else [])
            else None
        )
        if not cost_col:
            for k in (cost_actual_filtered[0].keys() if cost_actual_filtered else []):
                if k.startswith("col_") or k == "(col_5)":
                    cost_col = k
                    break
            if not cost_col:
                for k in (
                    list(cost_actual_filtered[0].keys()) if cost_actual_filtered else []
                ):
                    if k not in ("公司", "中心", "部门", "年份", "月份"):
                        cost_col = k
                        break

        for r in cost_actual_filtered:
            y = _safe_int(r.get("年份"))
            m = _safe_int(r.get("月份"))
            if y == target_year and m <= target_month:
                if cost_col:
                    actual_cost += _safe_float(r.get(cost_col))

        cost_ratio = (actual_cost / budget_cost * 100) if budget_cost > 0 else 0

        # 数据截止月份（从全部实际成本表找最大年月）
        cutoff_year, cutoff_month = 0, 0
        if cost_col:
            for r in cost_actual_all:
                cost_val = r.get(cost_col)
                if cost_val is not None and str(cost_val).strip() not in (
                    "",
                    "0",
                    "0.0",
                    "None",
                ):
                    y = _safe_int(r.get("年份"))
                    m = _safe_int(r.get("月份"))
                    if y > cutoff_year or (y == cutoff_year and m > cutoff_month):
                        cutoff_year, cutoff_month = y, m
        if cutoff_year == 0:
            cutoff_year, cutoff_month = target_year, target_month
        data_cutoff = f"{cutoff_year}年{cutoff_month}月"

        # === 组装返回 ===
        return {
            "filter_options": self._get_filter_options(filters),
            "data_cutoff": data_cutoff,
            "data_update_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "headcount": {
                "current": current_headcount,
                "budget": int(budget_headcount),
                "diff": headcount_diff,
                "ratio": round(headcount_ratio, 1),
                "white_collar": white_collar,
                "blue_collar": blue_collar,
            },
            "recruitment": {
                "total": recruit_total,
                "hired": recruit_hired,
                "pending": recruit_pending,
            },
            "cost": {
                "budget": round(budget_cost, 2),
                "actual": round(actual_cost, 2),
                "ratio": round(cost_ratio, 1),
                "cutoff": data_cutoff,
            },
        }

    def get_chart_data(self, filters: dict = None) -> dict:
        """获取图表数据（带结果缓存）"""
        cache_key = f"charts|{self._filters_key(filters)}"
        return self._get_result_cache(cache_key, lambda: self._compute_charts(filters))

    def _compute_charts(self, filters=None):
        """实际计算图表数据"""
        active_roster = self._filter_roster(filters)

        # === 图表1：员工结构分布 ===
        # 维度：性别、最高学历、年龄段、工龄段
        gender_data = _count_by_field(active_roster, "性别")
        education_data = _count_by_field(active_roster, "最高学历")
        age_data = _count_by_field(active_roster, "年龄", bins=AGE_BINS)
        tenure_data = _count_by_field(active_roster, "本单位工龄", bins=TENURE_BINS)

        # === 图表2：编制类型分析（合同类型） ===
        contract_data = _count_by_field(active_roster, "合同类型")

        # === 图表3：员工职级分布（大级别） ===
        level_data = _count_by_field(active_roster, "大级别")

        # === 图表4：当年人员变动趋势（入职/离职/净增长 by 月） ===
        trend_data = self._get_trend_data(filters)

        return {
            "filter_options": self._get_filter_options(filters),
            "structure": {
                "gender": gender_data,
                "education": education_data,
                "age": age_data,
                "tenure": tenure_data,
            },
            "contract": contract_data,
            "level": level_data,
            "trend": trend_data,
        }

    def _get_trend_data(self, filters: dict = None) -> dict:
        """计算当年各月的入职/离职/净增长人数（不按month过滤）"""
        all_roster = self._load_roster()
        # 当前年份：从数据中推断或使用2026
        current_year = 2026

        # 先按公司/中心/部门/人员类型过滤（不按月份过滤）
        company = (filters or {}).get("company", "")
        center = (filters or {}).get("center", "")
        department = (filters or {}).get("department", "")
        emp_type = (filters or {}).get("emp_type", "")

        filtered = all_roster
        if company:
            filtered = [
                r for r in filtered if str(r.get("公司", "")).strip() == company
            ]
        if center:
            filtered = [r for r in filtered if str(r.get("中心", "")).strip() == center]
        if department:
            filtered = [
                r for r in filtered if str(r.get("部门", "")).strip() == department
            ]
        if emp_type:
            filtered = [
                r for r in filtered if str(r.get("蓝领白领", "")).strip() == emp_type
            ]

        # 统计每个月的入职和离职人数
        months = []
        hire_counts = []
        leave_counts = []
        net_counts = []

        for m in range(1, 13):
            month_str = f"{current_year}-{str(m).zfill(2)}"
            months.append(month_str)

            # 入职：入职时间在该月
            hire = 0
            for r in filtered:
                hire_dt = _parse_date(r.get("入职时间"))
                if hire_dt and hire_dt.year == current_year and hire_dt.month == m:
                    hire += 1

            # 离职：离职日期在该月
            leave = 0
            for r in filtered:
                leave_dt = _parse_date(r.get("离职日期"))
                if leave_dt and leave_dt.year == current_year and leave_dt.month == m:
                    leave += 1

            hire_counts.append(hire)
            leave_counts.append(leave)
            net_counts.append(hire - leave)

        return {
            "months": months,
            "hire": hire_counts,
            "leave": leave_counts,
            "net": net_counts,
        }

    def get_efficiency_data(self, filters: dict = None) -> dict:
        """获取人效指标数据（带结果缓存）"""
        cache_key = f"efficiency|{self._filters_key(filters)}"
        return self._get_result_cache(
            cache_key, lambda: self._compute_efficiency(filters)
        )

    def _compute_efficiency(self, filters=None):
        """实际计算人效指标"""
        company = (filters or {}).get("company", "")
        month = (filters or {}).get("month", "")

        eff_actual = self._load_efficiency_actual()
        eff_budget = self._load_efficiency_budget()

        # 按公司过滤
        if company:
            eff_actual = [
                r for r in eff_actual if str(r.get("公司", "")).strip() == company
            ]
            eff_budget = [
                r for r in eff_budget if str(r.get("公司", "")).strip() == company
            ]

        # 确定目标月份
        if month:
            parts = month.split("-")
            target_month = int(parts[1]) if len(parts) == 2 else 0
        else:
            # 找最大月份
            max_m = 0
            for r in eff_actual:
                m = _safe_int(r.get("月份"))
                if m > max_m:
                    max_m = m
            target_month = max_m if max_m > 0 else 4

        # 要查找的三个项目
        projects = ["每元人力投入产出", "人事费用率", "人均毛利"]

        def _find_value(data, project, month_val):
            """从数据中查找指定项目和月份的值"""
            for r in data:
                if (
                    str(r.get("项目", "")).strip() == project
                    and _safe_int(r.get("月份")) == month_val
                ):
                    return _safe_float(r.get("值-当月")), _safe_float(r.get("值-累积"))
            return None, None

        result = {}
        for proj in projects:
            actual_month, actual_cum = _find_value(eff_actual, proj, target_month)
            budget_month, budget_cum = _find_value(eff_budget, proj, target_month)

            # 计算差值
            month_diff = None
            cum_diff = None
            if actual_month is not None and budget_month is not None:
                month_diff = round(actual_month - budget_month, 4)
            if actual_cum is not None and budget_cum is not None:
                cum_diff = round(actual_cum - budget_cum, 4)

            # 格式化：保留2位小数
            def _fmt(v):
                if v is None:
                    return "--"
                return f"{v:.2f}"

            result[proj] = {
                "actual_month": _fmt(actual_month),
                "actual_cum": _fmt(actual_cum),
                "budget_month": _fmt(budget_month),
                "budget_cum": _fmt(budget_cum),
                "month_diff": month_diff,
                "cum_diff": cum_diff,
            }

        # 确定颜色方向：每元人力投入产出和人均毛利是"越高越好"（正=绿），人事费用率是"越低越好"（正=红）
        # 由前端根据项目名决定

        # === 离职率数据 ===
        turnover = self._get_turnover_data(filters)

        return {
            "target_month": target_month,
            "indicators": result,
            "turnover": turnover,
        }

    def _get_turnover_data(self, filters: dict = None) -> dict:
        """获取离职率数据（4个类别）"""
        company = (filters or {}).get("company", "")
        month = (filters or {}).get("month", "")

        turnover_actual = self._load_turnover_actual()
        turnover_budget = self._load_turnover_budget()

        # 离职率数据都是公司级，过滤公司（"公司中心部门"字段）
        if company:
            turnover_actual = [
                r
                for r in turnover_actual
                if str(r.get("公司中心部门", "")).strip() == company
            ]
            turnover_budget = [
                r for r in turnover_budget if str(r.get("公司", "")).strip() == company
            ]

        # 确定目标月份
        if month:
            parts = month.split("-")
            target_month = int(parts[1]) if len(parts) == 2 else 0
        else:
            max_m = 0
            for r in turnover_actual:
                m = _safe_int(r.get("月份"))
                if m > max_m:
                    max_m = m
            target_month = max_m if max_m > 0 else 4

        # 4个类别
        categories = [
            "间接主动离职率",
            "间接被动离职率",
            "直接主动离职率",
            "直接被动离职率",
        ]

        def _find_rate(data, category, month_val, rate_field="离职率"):
            for r in data:
                if (
                    str(r.get("类别", "")).strip() == category
                    and _safe_int(r.get("月份")) == month_val
                ):
                    return _safe_float(r.get(rate_field))
            return None

        def _fmt_rate(v):
            if v is None:
                return "--"
            return f"{v*100:.2f}%"

        result = {}
        for cat in categories:
            actual_rate = _find_rate(turnover_actual, cat, target_month)
            budget_rate = _find_rate(turnover_budget, cat, target_month)

            result[cat] = {
                "actual": _fmt_rate(actual_rate),
                "actual_raw": (
                    round(actual_rate * 100, 4) if actual_rate is not None else None
                ),
                "budget": _fmt_rate(budget_rate),
                "budget_raw": (
                    round(budget_rate * 100, 4) if budget_rate is not None else None
                ),
            }

        return result

    def get_overtime_data(self, filters: dict = None) -> dict:
        """获取考勤数据（带结果缓存）"""
        cache_key = f"overtime|{self._filters_key(filters)}"
        return self._get_result_cache(
            cache_key, lambda: self._compute_overtime(filters), ttl=300
        )

    def _compute_overtime(self, filters=None):
        """实际计算考勤数据（图表1：中心级，图表2：部门级）
        - 中心图表：按公司+月份+人员类型过滤，横坐标为中心，从高到低
        - 部门图表：按公司+中心+月份+人员类型过滤，横坐标为部门，从高到低
        - 不使用二级部门
        """
        import pandas as pd

        df = self._load_overtime_df()
        if df is None or df.empty:
            return {
                "center": {"names": [], "values": []},
                "department": {"names": [], "values": []},
                "company_avg": 0,
            }

        company = (filters or {}).get("company", "")
        center = (filters or {}).get("center", "")
        month = (filters or {}).get("month", "")
        emp_type = (filters or {}).get("emp_type", "")

        # 公司和人员类型是公共过滤条件
        if company:
            df = df[df["公司"].str.strip() == company]
        if emp_type:
            df = df[df["蓝领白领"].str.strip() == emp_type]
        if month:
            parts = month.split("-")
            if len(parts) == 2:
                y, m = int(parts[0]), int(parts[1])
                df = df[(df["考勤年份_int"] == y) & (df["考勤月份_int"] == m)]

        if df.empty:
            return {
                "center": {"names": [], "values": []},
                "department": {"names": [], "values": []},
                "company_avg": 0,
            }

        # Step 1: 按员工编号+考勤年份+考勤月份汇总每人当月考勤时长
        emp_monthly = df.groupby(
            ["员工编号_str", "考勤年份_int", "考勤月份_int"], as_index=False
        ).agg(overtime=("当日考勤时长_num", "sum"))

        # 获取中心、部门映射
        emp_info_center = df.groupby("员工编号_str")["中心"].first().to_dict()
        emp_info_dept = df.groupby("员工编号_str")["部门"].first().to_dict()

        emp_monthly["中心"] = (
            emp_monthly["员工编号_str"].map(emp_info_center).fillna("未知")
        )
        emp_monthly["部门"] = (
            emp_monthly["员工编号_str"].map(emp_info_dept).fillna("未知")
        )

        # === 图表1：中心级（不按center/department过滤，只用company+month+emp_type）===
        center_grouped = emp_monthly.groupby(["中心"])["overtime"].mean().reset_index()
        center_grouped.columns = ["name", "avg"]
        center_grouped = center_grouped.sort_values("avg", ascending=False)

        # === 图表2：部门级（额外按center过滤，不按department过滤，不用二级部门）===
        # 过滤掉部门名等于中心名的行（这些是中心级汇总记录，不是真正的部门）
        dept_df = emp_monthly[
            emp_monthly["部门"].str.strip() != emp_monthly["中心"].str.strip()
        ]
        if center:
            dept_df = dept_df[dept_df["中心"].str.strip() == center]
        dept_grouped = dept_df.groupby(["部门"])["overtime"].mean().reset_index()
        dept_grouped.columns = ["name", "avg"]
        dept_grouped = dept_grouped.sort_values("avg", ascending=False)

        # === 公司平均（与中心图表同范围）===
        company_avg = emp_monthly["overtime"].mean()

        # 筛选选项
        filter_opts = self._get_filter_options(filters)

        return {
            "center": {
                "names": center_grouped["name"].tolist(),
                "values": [round(v, 2) for v in center_grouped["avg"].tolist()],
            },
            "department": {
                "names": dept_grouped["name"].tolist(),
                "values": [round(v, 2) for v in dept_grouped["avg"].tolist()],
            },
            "company_avg": round(company_avg, 2),
            "filter_options": filter_opts,
        }

    def get_dept_detail_data(self, filters: dict = None) -> dict:
        """获取部门明细表数据（带结果缓存）"""
        cache_key = f"dept_detail|{self._filters_key(filters)}"
        return self._get_result_cache(
            cache_key, lambda: self._compute_dept_detail(filters), ttl=300
        )

    def _compute_dept_detail(self, filters=None):
        """实际计算部门明细数据"""
        import pandas as pd

        company = (filters or {}).get("company", "")
        center = (filters or {}).get("center", "")
        department = (filters or {}).get("department", "")
        month = (filters or {}).get("month", "")
        emp_type = (filters or {}).get("emp_type", "")

        # 解析月份
        target_year, target_month = 0, 0
        if month:
            parts = month.split("-")
            if len(parts) == 2:
                target_year = int(parts[0])
                target_month = int(parts[1])
        else:
            # 从考勤数据获取最新月份
            avail = self.get_available_months()
            if avail:
                parts = avail[0].split("-")
                target_year, target_month = int(parts[0]), int(parts[1])
            else:
                target_year, target_month = 2026, 4

        # === 1. 获取部门列表（从组织架构）===
        org = self._load_org_structure()
        if company:
            org = [r for r in org if str(r.get("公司", "")).strip() == company]
        if center:
            org = [r for r in org if str(r.get("中心", "")).strip() == center]
        if department:
            org = [r for r in org if str(r.get("部门", "")).strip() == department]
        # 去重获取部门列表和对应中心
        dept_info = {}
        for r in org:
            d = str(r.get("部门", "")).strip()
            c = str(r.get("中心", "")).strip()
            if d and d not in dept_info:
                dept_info[d] = c
        dept_names = sorted(dept_info.keys())

        if not dept_names:
            return {"departments": [], "data": []}

        # === 2. 在职人数（按月过滤花名册）===
        roster = (
            self._filter_roster(filters)
            if filters
            else self._filter_roster({"month": month})
        )
        headcount_map = {}
        for r in roster:
            d = str(r.get("部门", "")).strip()
            headcount_map[d] = headcount_map.get(d, 0) + 1

        # === 3. 累积离职率-主动（间接主动离职率，按部门名匹配）===
        turnover_data = self._load_turnover_actual()
        turnover_map = {}
        for r in turnover_data:
            name = str(r.get("公司中心部门", "")).strip()
            cat = str(r.get("类别", "")).strip()
            y = _safe_int(r.get("年份"))
            m = _safe_int(r.get("月份"))
            if cat == "间接主动离职率" and y == target_year and m == target_month:
                turnover_map[name] = _safe_float(r.get("离职率"))

        # === 4. 本月出勤率（考勤数据，部门当日出勤率 按部门求平均）===
        ot_df = self._load_overtime_df()
        attendance_map = {}
        if ot_df is not None and not ot_df.empty:
            ot_filtered = ot_df[
                (ot_df["考勤年份_int"] == target_year)
                & (ot_df["考勤月份_int"] == target_month)
            ]
            if company:
                ot_filtered = ot_filtered[ot_filtered["公司"].str.strip() == company]
            if center:
                ot_filtered = ot_filtered[ot_filtered["中心"].str.strip() == center]
            if emp_type:
                ot_filtered = ot_filtered[
                    ot_filtered["蓝领白领"].str.strip() == emp_type
                ]
            if not ot_filtered.empty:
                att = ot_filtered.groupby("部门")["部门当日出勤率"].apply(
                    lambda x: pd.to_numeric(x, errors="coerce").mean()
                )
                attendance_map = att.to_dict()

        # === 5. 人均考勤（考勤数据，按员工+年+月汇总，再按部门求平均）===
        overtime_map = {}
        if ot_df is not None and not ot_df.empty:
            ot_filtered = ot_df[
                (ot_df["考勤年份_int"] == target_year)
                & (ot_df["考勤月份_int"] == target_month)
            ]
            if company:
                ot_filtered = ot_filtered[ot_filtered["公司"].str.strip() == company]
            if center:
                ot_filtered = ot_filtered[ot_filtered["中心"].str.strip() == center]
            if emp_type:
                ot_filtered = ot_filtered[
                    ot_filtered["蓝领白领"].str.strip() == emp_type
                ]
            if not ot_filtered.empty:
                emp_ot = ot_filtered.groupby(
                    ["员工编号", "考勤年份_int", "考勤月份_int", "部门"], as_index=False
                ).agg(ot_hours=("当日考勤时长_num", "sum"))
                dept_ot = emp_ot.groupby("部门")["ot_hours"].mean()
                overtime_map = dept_ot.to_dict()

        # === 6. HC编制使用率（在职人数 / 预算人数）===
        # 预算人数也需要按蓝领白领切片，否则切片后HC编制使用率会偏小
        budget_data = self._load_budget()
        budget_map = {}
        for r in budget_data:
            d = str(r.get("部门", "")).strip()
            m = _safe_int(r.get("月份"))
            if m == target_month:
                if not company or str(r.get("公司", "")).strip() == company:
                    if not center or str(r.get("中心", "")).strip() == center:
                        if (
                            not emp_type
                            or str(r.get("蓝领白领", "")).strip() == emp_type
                        ):
                            budget_map[d] = budget_map.get(d, 0) + _safe_float(
                                r.get("人头预算")
                            )

        # === 7. 成本使用率（累积实际/累积预算）===
        cost_actual = self._load_cost_actual()
        cost_budget = self._load_cost_budget()
        cost_actual_map = {}
        cost_budget_map = {}
        for r in cost_actual:
            d = str(r.get("部门", "")).strip()
            y = str(r.get("年份", "")).strip()
            m = _safe_int(r.get("月份"))
            y_int = _safe_int(y)
            if y_int == target_year and 1 <= m <= target_month:
                if not company or str(r.get("公司", "")).strip() == company:
                    if not center or str(r.get("中心", "")).strip() == center:
                        cost_actual_map[d] = cost_actual_map.get(d, 0) + _safe_float(
                            r.get("成本")
                        )
        for r in cost_budget:
            d = str(r.get("部门", "")).strip()
            y = str(r.get("年份", "")).strip()
            m = _safe_int(r.get("月份"))
            y_int = _safe_int(y)
            if y_int == target_year and 1 <= m <= target_month:
                if not company or str(r.get("公司", "")).strip() == company:
                    if not center or str(r.get("中心", "")).strip() == center:
                        cost_budget_map[d] = cost_budget_map.get(d, 0) + _safe_float(
                            r.get("计入费用职工薪酬总额")
                        )

        # === 8. 未入职需求岗位数（招聘数量 - 已入职数）===
        recruitment = self._load_recruitment()
        recruit_map = {}
        for r in recruitment:
            d = str(r.get("部门", "")).strip()
            if not company or str(r.get("公司", "")).strip() == company:
                if not center or str(r.get("中心", "")).strip() == center:
                    total = _safe_int(r.get("招聘数量"))
                    hired = 1 if str(r.get("是否入职", "")).strip() == "是" else 0
                    if d not in recruit_map:
                        recruit_map[d] = {"total": 0, "hired": 0}
                    recruit_map[d]["total"] += total
                    recruit_map[d]["hired"] += hired

        # === 组装结果 ===
        rows = []
        for d in dept_names:
            center_name = dept_info.get(d, "")
            hc = headcount_map.get(d, 0)
            budget_hc = budget_map.get(d, 0)
            hc_rate = (hc / budget_hc * 100) if budget_hc > 0 else None

            actual_cost = cost_actual_map.get(d, 0)
            budget_cost = cost_budget_map.get(d, 0)
            cost_rate = (actual_cost / budget_cost * 100) if budget_cost > 0 else None

            rec = recruit_map.get(d, {"total": 0, "hired": 0})
            pending = rec["total"] - rec["hired"]

            turnover_rate = turnover_map.get(d)
            attendance = attendance_map.get(d)
            ot_hours = overtime_map.get(d)

            rows.append(
                {
                    "dept": d,
                    "center": center_name,
                    "headcount": hc,
                    "turnover_rate": (
                        round(turnover_rate * 100, 2)
                        if turnover_rate is not None
                        else None
                    ),
                    "attendance": (
                        round(attendance * 100, 2) if attendance is not None else None
                    ),
                    "overtime_hours": (
                        round(ot_hours, 2) if ot_hours is not None else None
                    ),
                    "hc_rate": round(hc_rate, 1) if hc_rate is not None else None,
                    "cost_rate": round(cost_rate, 1) if cost_rate is not None else None,
                    "pending_recruit": pending if pending > 0 else 0,
                }
            )

        filter_opts = self._get_filter_options(filters)
        return {"departments": dept_names, "data": rows, "filter_options": filter_opts}

    def get_cost_analysis_data(self, filters: dict = None) -> dict:
        """获取部门成本包使用情况数据（带结果缓存）"""
        cache_key = f"cost_analysis|{self._filters_key(filters)}"
        return self._get_result_cache(
            cache_key, lambda: self._compute_cost_analysis(filters), ttl=300
        )

    def _compute_cost_analysis(self, filters=None):
        """计算各部门成本使用情况"""
        company = (filters or {}).get("company", "")
        center = (filters or {}).get("center", "")
        department = (filters or {}).get("department", "")
        month = (filters or {}).get("month", "")

        if month:
            parts = month.split("-")
            if len(parts) == 2:
                target_year = int(parts[0])
                target_month = int(parts[1])
        else:
            avail = self.get_available_months()
            if avail:
                parts = avail[0].split("-")
                target_year, target_month = int(parts[0]), int(parts[1])
            else:
                target_year, target_month = 2026, 4

        # 获取部门列表
        org = self._load_org_structure()
        if company:
            org = [r for r in org if str(r.get("公司", "")).strip() == company]
        if center:
            org = [r for r in org if str(r.get("中心", "")).strip() == center]
        if department:
            org = [r for r in org if str(r.get("部门", "")).strip() == department]
        dept_names = sorted(
            set(str(r.get("部门", "")).strip() for r in org if r.get("部门"))
        )

        if not dept_names:
            return {"names": [], "actual": [], "budget": [], "ratio": []}

        # 累积实际成本
        cost_actual = self._load_cost_actual()
        actual_map = {}
        for r in cost_actual:
            d = str(r.get("部门", "")).strip()
            y_int = _safe_int(r.get("年份"))
            m = _safe_int(r.get("月份"))
            if y_int == target_year and 1 <= m <= target_month:
                if not company or str(r.get("公司", "")).strip() == company:
                    if not center or str(r.get("中心", "")).strip() == center:
                        if not department or d == department:
                            actual_map[d] = actual_map.get(d, 0) + _safe_float(
                                r.get("成本")
                            )

        # 累积预算成本
        cost_budget = self._load_cost_budget()
        budget_map = {}
        for r in cost_budget:
            d = str(r.get("部门", "")).strip()
            y_int = _safe_int(r.get("年份"))
            m = _safe_int(r.get("月份"))
            if y_int == target_year and 1 <= m <= target_month:
                if not company or str(r.get("公司", "")).strip() == company:
                    if not center or str(r.get("中心", "")).strip() == center:
                        if not department or d == department:
                            budget_map[d] = budget_map.get(d, 0) + _safe_float(
                                r.get("计入费用职工薪酬总额")
                            )

        # 组装并按使用率从小到大排序
        rows = []
        for d in dept_names:
            a = actual_map.get(d, 0)
            b = budget_map.get(d, 0)
            ratio = (a / b * 100) if b > 0 else 0
            rows.append(
                {
                    "dept": d,
                    "actual": round(a, 2),
                    "budget": round(b, 2),
                    "ratio": round(ratio, 1),
                }
            )
        rows.sort(key=lambda x: x["ratio"])

        return {
            "names": [r["dept"] for r in rows],
            "actual": [r["actual"] for r in rows],
            "budget": [r["budget"] for r in rows],
            "ratio": [r["ratio"] for r in rows],
        }


def _bin_range(val: float, bins: list) -> str:
    """将数值分桶，返回对应的标签。bins = [(low, high, label), ...]"""
    for low, high, label in bins:
        if low <= val < high:
            return label
    # 超出范围取最后一个桶
    if bins:
        return bins[-1][2]
    return str(val)


# 年龄段分桶
AGE_BINS = [
    (0, 25, "25岁以下"),
    (25, 30, "25-30岁"),
    (30, 35, "30-35岁"),
    (35, 40, "35-40岁"),
    (40, 45, "40-45岁"),
    (45, 50, "45-50岁"),
    (50, 100, "50岁以上"),
]

# 工龄段分桶（年）
TENURE_BINS = [
    (0, 1, "1年以下"),
    (1, 3, "1-3年"),
    (3, 5, "3-5年"),
    (5, 10, "5-10年"),
    (10, 15, "10-15年"),
    (15, 20, "15-20年"),
    (20, 100, "20年以上"),
]


def _count_by_field(records: list, field: str, bins=None) -> list:
    """统计记录中某字段的分布。如果指定bins则先分桶。
    返回 [{name, value}, ...] 按value降序
    """
    counter = {}
    for r in records:
        raw = r.get(field)
        if raw is None:
            continue
        s = str(raw).strip()
        if s in ("", "None", "NaT"):
            continue
        if bins:
            num = _safe_float(raw) if isinstance(raw, (int, float)) else _safe_float(s)
            s = _bin_range(num, bins)
        counter[s] = counter.get(s, 0) + 1
    result = [{"name": k, "value": v} for k, v in counter.items()]
    result.sort(key=lambda x: x["value"], reverse=True)
    return result


def _parse_date(val) -> datetime | None:
    """解析日期值，支持datetime对象和各种字符串格式"""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    if s in ("", "None", "NaT"):
        return None
    # 尝试常见格式
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
    ):
        try:
            return datetime.strptime(s[: len(fmt) + 2], fmt)
        except (ValueError, IndexError):
            continue
    # 尝试只取前10位
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except (ValueError, IndexError):
        return None


def _safe_float(val) -> float:
    try:
        if val is None:
            return 0.0
        s = str(val).strip()
        # 去除中文字符如"2026年" → "2026"
        s = re.sub(r"[^\d.\-]", "", s)
        return float(s) if s else 0.0
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val) -> int:
    try:
        if val is None:
            return 0
        s = str(val).strip()
        s = re.sub(r"[^\d.\-]", "", s)
        return int(float(s)) if s else 0
    except (ValueError, TypeError):
        return 0


# 全局实例
_dashboard_provider = None


def get_dashboard_provider() -> DashboardDataProvider:
    global _dashboard_provider
    if _dashboard_provider is None:
        _dashboard_provider = DashboardDataProvider()
    return _dashboard_provider
