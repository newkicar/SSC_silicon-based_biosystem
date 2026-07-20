"""
数据源工具 —— 秘书的真实数据获取能力

提供三类数据源：
1. 花名册（Excel）：员工基础信息
2. 考勤API（HTTP）：员工考勤数据
3. 花名册API（HTTP）：实时员工数据查询

所有数据源统一通过 DataSecretary 类调用，秘书通过此类获取内外部数据。
"""
import os
import json
import base64
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

import requests
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

from src.config.settings import BASE_DIR


# ==================== 配置 ====================
ROSTER_EXCEL_PATH = str(Path(__file__).resolve().parent.parent.parent / "databases" / "员工花名册.xlsx")
ROSTER_SHEET_NAME = "花名册"

ROSTER_API_URL = "ROSTER_API_URL"
ROSTER_AUTH_CODE = "ROSTER_AUTH_CODE"
ROSTER_PUBLIC_KEY = """ROSTER_PUBLIC_KEY"""

ATTENDANCE_API_URL = "ATTENDANCE_API_URL"
ATTENDANCE_AUTH_CODE = "ATTENDANCE_AUTH_CODE"
ATTENDANCE_PUBLIC_KEY = """ATTENDANCE_PUBLIC_KEY"""

# 花名册中员工号与系统员工号的映射：后6位对应
EMPLOYEE_ID_SUFFIX_LENGTH = 6

# 员工级别分类
LEVEL_MAPPING = {
    "99": "派驻", "00": "1", "06": "-",
    "2Y": "2.5", "2Z": "2.4", "2A": "2.3", "2B": "2.2", "2C": "2.1",
    "3Y": "3.5", "3Z": "3.4", "3A": "3.3", "3B": "3.2", "3C": "3.1",
    "4Y": "4.5", "4Z": "4.4", "4A": "4.3", "4B": "4.2", "4C": "4.1",
    "5Y": "5.5", "5Z": "5.4", "5A": "5.3", "5B": "5.2", "5C": "5.1",
    "6A": "6.1", "6B": "6.2", "6C": "6.3",
    "7A": "7.1", "7B": "7.2", "7C": "7.3",
    "8A": "8.1", "8B": "8.2", "8C": "8.3",
    "9A": "9.1", "9B": "9.2", "9C": "9.3",
    "A1": "10.1", "A2": "10.2", "A3": "10.3",
    "B1": "11.1", "B2": "11.2", "B3": "11.3",
    "C1": "12.1", "C2": "12.2", "C3": "12.3",
}

# 花名册Excel列名映射（0-based index）
ROSTER_COLUMNS = {
    0: "序号", 1: "编制类型", 2: "人员编制", 3: "公司", 4: "地区",
    5: "员工号", 6: "姓名", 7: "中心", 8: "部门英文缩写", 9: "部门",
    10: "二级部门", 11: "三级部门", 12: "岗位", 13: "参加工作日期",
    14: "入职时间", 15: "合同开始日期", 16: "劳动合同试用期时间",
    17: "拟转正日期", 18: "实际转正日期", 19: "合同结束日期",
    20: "合同期状态", 21: "本单位工龄", 22: "合同类型",
    23: "身份证号", 24: "性别", 25: "出生日期", 26: "年龄",
    31: "最高学历", 39: "职称", 41: "电话号码",
    62: "离职日期", 63: "离职原因", 65: "工作工龄",
    66: "发展通道", 68: "汇报给谁", 69: "被汇报人工号", 70: "员工性质",
}


# ==================== RSA加密工具 ====================
def _rsa_encrypt(plain_text: str, public_key_str: str) -> str:
    """使用RSA公钥加密文本"""
    try:
        key_der = base64.b64decode(public_key_str)
        rsa_key = RSA.import_key(key_der)
        cipher = PKCS1_v1_5.new(rsa_key)
        encrypted = cipher.encrypt(plain_text.encode("utf-8"))
        return base64.b64encode(encrypted).decode("utf-8")
    except Exception as e:
        return f"[加密失败: {str(e)}]"


def _generate_auth_info(auth_code: str, public_key_str: str) -> str:
    """
    生成[ERP系统接口]认证信息。
    格式：RSA加密("YYYYMMDD&authCode")
    """
    today = datetime.now().strftime("%Y%m%d")
    plaintext = f"{today}&{auth_code}"
    return _rsa_encrypt(plaintext, public_key_str)


# ==================== 花名册Excel读取器 ====================
class RosterExcelReader:
    """
    读取本地花名册Excel文件。
    提供按员工号、姓名、部门等维度的查询能力。
    """

    def __init__(self, file_path: str = ROSTER_EXCEL_PATH, sheet_name: str = ROSTER_SHEET_NAME):
        self._file_path = file_path
        self._sheet_name = sheet_name
        self._data = None  # 懒加载

    def _ensure_loaded(self):
        """懒加载Excel数据"""
        if self._data is not None:
            return

        if not os.path.exists(self._file_path):
            self._data = []
            return

        try:
            import openpyxl
            wb = openpyxl.load_workbook(self._file_path, read_only=True, data_only=True)
            ws = wb[self._sheet_name]
            self._data = []
            headers = None
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i == 0:
                    headers = [str(c).strip() if c else f"col_{j}" for j, c in enumerate(row)]
                    continue
                record = {}
                for j, val in enumerate(row):
                    col_name = headers[j] if j < len(headers) else f"col_{j}"
                    record[col_name] = val
                # 只保留在职员工（无离职日期）
                if record.get("员工号") and not record.get("离职日期"):
                    self._data.append(record)
            wb.close()
        except Exception as e:
            print(f"[数据源] 花名册加载失败: {e}")
            self._data = []

    def count(self) -> int:
        """总人数"""
        self._ensure_loaded()
        return len(self._data)

    def query_by_name(self, name: str) -> list:
        """按姓名查询"""
        self._ensure_loaded()
        return [r for r in self._data if str(r.get("姓名", "")).strip() == name]

    def query_by_department(self, department: str) -> list:
        """按部门查询（支持模糊匹配）"""
        self._ensure_loaded()
        return [r for r in self._data if department in str(r.get("部门", ""))]

    def query_by_employee_id(self, employee_id: str) -> list:
        """按工号查询（支持部分匹配）"""
        self._ensure_loaded()
        eid_str = str(employee_id).strip()
        results = []
        for r in self._data:
            roster_id = str(r.get("员工号", "")).strip()
            if eid_str == roster_id or eid_str in roster_id:
                results.append(r)
        return results

    def query_by_keyword(self, keyword: str) -> list:
        """按关键词模糊搜索（姓名/部门/岗位/工号）"""
        self._ensure_loaded()
        results = []
        for r in self._data:
            searchable = f"{r.get('姓名', '')} {r.get('员工号', '')} {r.get('部门', '')} {r.get('二级部门', '')} {r.get('岗位', '')} {r.get('地区', '')}"
            if keyword in searchable:
                results.append(r)
        return results

    def get_department_stats(self, department: str = None) -> dict:
        """获取部门统计数据"""
        self._ensure_loaded()
        data = self._data if department is None else self.query_by_department(department)

        stats = {
            "total": len(data),
            "by_department": {},
            "by_gender": {"男": 0, "女": 0},
            "by_education": {},
            "by_level": {},
            "avg_age": 0,
            "avg_tenure": 0,
        }

        age_sum = 0
        tenure_sum = 0
        valid_age = 0
        valid_tenure = 0

        for r in data:
            # 部门分布
            dept = str(r.get("二级部门", r.get("部门", "未知"))).strip() or "未知"
            stats["by_department"][dept] = stats["by_department"].get(dept, 0) + 1

            # 性别分布
            gender = str(r.get("性别", "")).strip()
            if gender in stats["by_gender"]:
                stats["by_gender"][gender] += 1

            # 学历分布
            edu = str(r.get("最高学历", "未知")).strip() or "未知"
            stats["by_education"][edu] = stats["by_education"].get(edu, 0) + 1

            # 年龄
            try:
                age = int(float(str(r.get("年龄", 0))))
                age_sum += age
                valid_age += 1
            except (ValueError, TypeError):
                pass

            # 工龄
            try:
                tenure = float(str(r.get("本单位工龄", 0)))
                tenure_sum += tenure
                valid_tenure += 1
            except (ValueError, TypeError):
                pass

        if valid_age > 0:
            stats["avg_age"] = round(age_sum / valid_age, 1)
        if valid_tenure > 0:
            stats["avg_tenure"] = round(tenure_sum / valid_tenure, 1)

        return stats

    def get_headcount_trend(self, department: str = None) -> dict:
        """获取人力变动趋势（基于入职/离职日期统计）"""
        self._ensure_loaded()

        # 在职人员按入职月份统计
        hire_by_month = {}
        for r in self._data:
            if department and department not in str(r.get("部门", "")):
                continue
            hire_date = r.get("入职时间")
            if hire_date:
                try:
                    if isinstance(hire_date, datetime):
                        month_key = hire_date.strftime("%Y-%m")
                    else:
                        month_key = str(hire_date)[:7]
                    hire_by_month[month_key] = hire_by_month.get(month_key, 0) + 1
                except Exception:
                    pass

        return {"hire_by_month": hire_by_month, "current_total": len(self._data)}


# ==================== API数据源 ====================
class SAPDataProvider:
    """
    通过SAP系统API获取实时数据（花名册/考勤）。
    数据传输使用RSA加密。
    """

    def __init__(self):
        self.timeout = 10

    def query_roster(self, person_no: str = None) -> list:
        """
        查询花名册API。
        参数格式：{"authInfo": RSA加密("YYYYMMDD&authCode")}
        """
        try:
            params = {"authInfo": _generate_auth_info(ROSTER_AUTH_CODE, ROSTER_PUBLIC_KEY)}
            if person_no:
                params["personNo"] = person_no.zfill(8)

            resp = requests.post(ROSTER_API_URL, json=params, headers={"Content-Type": "application/json"}, timeout=self.timeout)
            if resp.status_code == 200:
                result = resp.json()
                if result.get("code") == 200:
                    data = result.get("data", [])
                    return data if isinstance(data, list) else [data]
            return []
        except Exception as e:
            print(f"[数据源] 花名册API查询失败: {e}")
            return []

    def query_attendance(self, person_no: str, begin_date: str, end_date: str) -> list:
        """
        查询考勤API。
        参数格式：{"authInfo": ..., "personNo": ..., "beginDate": "YYYY-MM-DD", "endDate": "YYYY-MM-DD"}
        """
        try:
            params = {
                "personNo": str(person_no).zfill(8),
                "beginDate": begin_date,
                "endDate": end_date,
                "authInfo": _generate_auth_info(ATTENDANCE_AUTH_CODE, ATTENDANCE_PUBLIC_KEY),
            }
            resp = requests.post(ATTENDANCE_API_URL, json=params, headers={"Content-Type": "application/json"}, timeout=self.timeout)
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 200:
                data = result.get("data", [])
                return data if isinstance(data, list) else [data]
            else:
                print(f"[数据源] 考勤API返回错误: {result.get('msg')}")
                return []
        except Exception as e:
            print(f"[数据源] 考勤API查询失败: {e}")
            return []


# ==================== 秘书数据服务（统一入口） ====================
class DataSecretary:
    """
    秘书的数据服务能力。
    统一入口，负责获取、加工、汇总数据，返回给大脑做决策。

    核心逻辑：
    - 秘书能做的事：查找/检索/汇总/整理已有的数据和政策
    - 秘书做不到的事：人的判断、人际沟通、外部系统操作、审批
    """

    def __init__(self):
        self.roster = RosterExcelReader()
        self.sap = SAPDataProvider()

    def can_handle(self, task_description: str) -> bool:
        """判断秘书是否有能力处理此任务"""
        handleable_keywords = [
            "查询", "搜索", "检索", "统计", "汇总", "整理", "数据",
            "花名册", "员工信息", "部门人数", "学历分布", "年龄分布",
            "考勤", "加班", "迟到", "出勤", "招聘数据",
            "报告", "报表", "分析", "趋势",
        ]
        for kw in handleable_keywords:
            if kw in task_description:
                return True
        return False

    def get_roster_summary(self, department: str = None) -> str:
        """获取花名册汇总数据，返回格式化的文本"""
        stats = self.roster.get_department_stats(department)
        if stats["total"] == 0:
            return f"未找到{'部门' if department else '系统'}相关的员工数据。"

        dept_label = department if department else "全公司"
        lines = [
            f"=== {dept_label} 人员花名册统计 ===",
            f"在职总人数: {stats['total']}人",
            "",
            "【性别分布】",
            f"  男: {stats['by_gender'].get('男', 0)}人 | 女: {stats['by_gender'].get('女', 0)}人",
            "",
            f"【平均年龄】{stats['avg_age']}岁 | 【平均本单位工龄】{stats['avg_tenure']}年",
            "",
            "【部门分布】",
        ]

        sorted_depts = sorted(stats["by_department"].items(), key=lambda x: x[1], reverse=True)
        for dept, count in sorted_depts[:15]:
            lines.append(f"  {dept}: {count}人")

        if len(sorted_depts) > 15:
            lines.append(f"  ...及其他{len(sorted_depts) - 15}个部门")

        lines.append("")
        lines.append("【学历分布】")
        for edu, count in sorted(stats["by_education"].items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {edu}: {count}人")

        return "\n".join(lines)

    def search_employee(self, keyword: str, user_info: dict = None) -> str:
        """
        搜索员工信息。
        如果提供user_info，自动应用权限过滤（范围+字段）。
        """
        results = self.roster.query_by_keyword(keyword)
        if not results:
            return f"未找到与'{keyword}'相关的员工信息。"

        # 权限过滤
        if user_info:
            from src.security.permissions import check_data_access
            results = check_data_access(user_info, results)

        lines = [f"=== 搜索'{keyword}'结果（共{len(results)}人） ==="]
        for r in results[:20]:
            name = r.get("姓名", "?")
            dept = r.get("部门", "?")
            pos = r.get("岗位", "?")
            emp_id = r.get("员工号", "?")
            gender = r.get("性别", "?")
            age = r.get("年龄", "?")
            lines.append(f"  {name} | 工号:{emp_id} | {dept} | {pos} | {gender} | {age}岁")

        if len(results) > 20:
            lines.append(f"  ...还有{len(results) - 20}人未显示")

        return "\n".join(lines)

    def get_department_roster(self, department: str) -> str:
        """获取某部门的人员清单"""
        results = self.roster.query_by_department(department)
        if not results:
            return f"未找到'{department}'的人员数据。"

        lines = [f"=== {department} 人员清单（共{len(results)}人） ==="]
        for r in results:
            name = r.get("姓名", "?")
            pos = r.get("岗位", "?")
            sub_dept = r.get("二级部门", "") or ""
            lines.append(f"  {name} | {sub_dept} | {pos}")

        return "\n".join(lines)

    def get_recruitment_data(self, period: str = None) -> str:
        """获取招聘数据（基于花名册中的入职信息统计）"""
        data = self.roster._data
        self.roster._ensure_loaded()

        if not data:
            return "无法获取招聘数据：花名册数据未加载。"

        # 按入职月份统计新入职人数
        hire_stats = {}
        now = datetime.now()

        for r in data:
            hire_date = r.get("入职时间")
            if hire_date:
                try:
                    if isinstance(hire_date, datetime):
                        month_key = hire_date.strftime("%Y-%m")
                    else:
                        month_key = str(hire_date)[:7]

                    # 只统计最近12个月
                    if month_key >= (now - timedelta(days=365)).strftime("%Y-%m"):
                        if month_key not in hire_stats:
                            hire_stats[month_key] = {"total": 0, "by_dept": {}}
                        hire_stats[month_key]["total"] += 1
                        dept = str(r.get("部门", "未知")).strip()
                        hire_stats[month_key]["by_dept"][dept] = hire_stats[month_key]["by_dept"].get(dept, 0) + 1
                except Exception:
                    pass

        # 按渠道统计（基于"来源"字段）
        source_stats = {}
        for r in data:
            source = str(r.get("来源", "未知")).strip() or "未知"
            hire_date = r.get("入职时间")
            if hire_date:
                try:
                    if isinstance(hire_date, datetime):
                        month_key = hire_date.strftime("%Y-%m")
                    else:
                        month_key = str(hire_date)[:7]
                    if month_key >= (now - timedelta(days=365)).strftime("%Y-%m"):
                        source_stats[source] = source_stats.get(source, 0) + 1
                except Exception:
                    pass

        lines = [
            "=== 招聘数据统计（近12个月） ===",
            f"统计时间: {now.strftime('%Y-%m-%d')}",
            f"在职总人数: {len(data)}人",
            "",
            "【按月度入职人数】",
        ]

        for month in sorted(hire_stats.keys(), reverse=True):
            info = hire_stats[month]
            lines.append(f"  {month}: {info['total']}人入职")

        lines.append("")
        lines.append("【入职渠道分布】")
        for source, count in sorted(source_stats.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {source}: {count}人")

        return "\n".join(lines)

    def _try_get_attendance(self, request_text: str, requester_identity: str = "",
                            employee_id: str = "", employee_name: str = "") -> str:
        """
        尝试自动获取考勤数据。
        
        新版（v12）：接受显式参数 employee_id/employee_name，不再从文本中正则猜测。
        调用方（brain tool query_attendance）已知员工身份，直接传入即可。
        日期范围仍从 request_text 中检测关键词（"上月"等是死格式关键词）。
        """
        self.roster._ensure_loaded()
        matched = []

        # 1. 优先用显式传入的工号或姓名精确查询（信任调用方）
        if employee_id:
            matched = self.roster.query_by_employee_id(employee_id)
            if matched:
                print(f"[秘书] 通过显式工号'{employee_id}'找到员工: {matched[0].get('姓名')}")

        if not matched and employee_name:
            matched = self.roster.query_by_name(employee_name)
            if matched:
                print(f"[秘书] 通过显式姓名'{employee_name}'找到员工: {matched[0].get('姓名')}")

        # 2. 如果显式参数未命中，尝试从 request_text 中精确匹配花名册姓名
        #    （姓名是花名册已知的死集合，用子串匹配而非正则提取）
        if not matched:
            self.roster._ensure_loaded()
            for r in self.roster._data:
                name = str(r.get("姓名", "")).strip()
                if name and len(name) >= 2 and name in request_text:
                    matched = [r]
                    print(f"[秘书] 通过花名册姓名子串匹配找到: {name}")
                    break

        if not matched:
            return ""

        employee = matched[0]
        emp_id = str(employee.get("员工号", "")).strip()
        emp_name = str(employee.get("姓名", "")).strip()
        emp_dept = str(employee.get("部门", "")).strip()

        if not emp_id:
            return f"找到员工'{emp_name}'但缺少工号信息，无法查询考勤数据。"

        # 3. 自动确定日期范围（默认本月，如果提到"上月"则查上月）
        now = datetime.now()
        if any(kw in request_text for kw in ("上月", "上个月", "上月")):
            first_of_this_month = now.replace(day=1)
            last_of_prev_month = first_of_this_month - timedelta(days=1)
            first_of_prev_month = last_of_prev_month.replace(day=1)
            start_date = first_of_prev_month.strftime("%Y-%m-%d")
            end_date = last_of_prev_month.strftime("%Y-%m-%d")
            period_label = f"{first_of_prev_month.year}年{first_of_prev_month.month}月"
        else:
            # 默认查本月
            start_date = now.replace(day=1).strftime("%Y-%m-%d")
            end_date = now.strftime("%Y-%m-%d")
            period_label = f"{now.year}年{now.month}月"

        # 4. 调用SAP考勤API
        try:
            print(f"[秘书] 尝试调用考勤API：员工={emp_name}({emp_id}), 日期={start_date}~{end_date}")
            attendance_data = self.sap.query_attendance(emp_id, start_date, end_date)
            
            if attendance_data:
                # API调用成功，格式化返回
                lines = [
                    f"=== {emp_name} 的考勤数据（{period_label}）===",
                    f"工号: {emp_id} | 部门: {emp_dept}",
                    "",
                ]
                for record in attendance_data[:31]:  # 最多31天
                    if isinstance(record, dict):
                        date = record.get("attendanceDate", "")
                        classes = record.get("attendanceClasses", "")
                        duration = record.get("attendanceDuration", "")
                        ot_normal = record.get("overtimeDuration", 0)
                        ot_weekend = record.get("overtimeWDuration", 0)
                        ot_holiday = record.get("overtimeHDuration", 0)
                        in_card = record.get("beginCard", "")
                        out_card = record.get("endCard", "")
                        line = f"  {date} {classes}"
                        if duration:
                            line += f" | 出勤{duration}h"
                        if ot_normal or ot_weekend or ot_holiday:
                            line += f" | 加班:{ot_normal}/{ot_weekend}/{ot_holiday}h"
                        if in_card or out_card:
                            line += f" | 卡:{in_card}-{out_card}"
                        lines.append(line)
                    else:
                        lines.append(f"  {record}")
                
                return "\n".join(lines)
            else:
                # API返回空数据 — 不编造，如实告知
                print(f"[秘书] 考勤API返回空数据")
                return (
                    f"=== 考勤数据查询结果 ===\n"
                    f"员工: {emp_name}（工号: {emp_id}）| 部门: {emp_dept}\n"
                    f"查询期间: {period_label}\n"
                    f"结果: 考勤[ERP系统接口]未返回该员工的考勤数据。\n"
                    f"可能原因: SAP考勤API接口参数格式需要确认，或该员工暂无考勤记录。"
                )
                
        except Exception as e:
            # API不可达，降级处理 — 不编造，如实告知
            print(f"[秘书] 考勤API调用失败: {e}")
            return (
                f"=== 考勤数据查询结果 ===\n"
                f"员工: {emp_name}（工号: {emp_id}）| 部门: {emp_dept}\n"
                f"查询期间: {period_label}\n"
                f"结果: 考勤[ERP系统接口]调用失败（{str(e)[:100]}）。\n"
                f"建议: 请直接通过SAP系统查询该员工考勤记录。"
            )

    def get_employee_detail(self, keyword: str) -> str:
        """
        查询单个员工的详细信息（包含岗级、学历、工龄、部门等）。
        用于回答"查看某人信息/岗级/级别"等个人查询。
        """
        self.roster._ensure_loaded()
        results = self.roster.query_by_keyword(keyword)
        
        if not results:
            # 尝试按姓名精确匹配
            results = self.roster.query_by_name(keyword)
        
        if not results:
            return f"未在花名册中找到与'{keyword}'相关的员工信息。"
        
        employee = results[0]  # 取第一个匹配结果
        name = employee.get("姓名", "未知")
        emp_id = str(employee.get("员工号", "未知")).strip()
        dept = employee.get("部门", "未知")
        sub_dept = employee.get("二级部门", "") or ""
        position = employee.get("岗位", "未知")
        gender = employee.get("性别", "未知")
        age = str(employee.get("年龄", "未知"))
        edu = employee.get("最高学历", "未知")
        hire_date = employee.get("入职时间", "未知")
        tenure = str(employee.get("本单位工龄", "未知"))
        channel = employee.get("发展通道", "") or ""
        contract_type = employee.get("合同类型", "") or ""
        supervisor = employee.get("汇报给谁", "") or ""
        company = employee.get("公司", "") or ""
        region = employee.get("地区", "") or ""
        staff_type = employee.get("人员编制", "") or ""
        nature = employee.get("员工性质", "") or ""
        
        # 岗级解析：使用员工号后几位作为查询依据
        # 注意：岗级信息可能不在花名册Excel中，需要通过[ERP系统接口]查询
        # 这里先提供花名册中已有的信息
        
        lines = [
            f"=== 员工详细信息 ===",
            f"姓名: {name}",
            f"工号: {emp_id}",
            f"性别: {gender}",
            f"年龄: {age}岁",
            f"公司: {company}",
            f"地区: {region}",
            f"部门: {dept}",
            f"二级部门: {sub_dept}" if sub_dept else "",
            f"岗位: {position}",
            f"发展通道: {channel}" if channel else "",
            f"人员编制: {staff_type}" if staff_type else "",
            f"员工性质: {nature}" if nature else "",
            f"最高学历: {edu}",
            f"入职时间: {hire_date}",
            f"本单位工龄: {tenure}年",
            f"合同类型: {contract_type}" if contract_type else "",
            f"汇报给谁: {supervisor}" if supervisor else "",
        ]
        
        return "\n".join([l for l in lines if l])

    def process_data_request(self, request_text: str, requester_identity: str = "",
                             employee_id: str = "", employee_name: str = "") -> str:
        """
        处理数据请求的统一入口。
        根据请求内容和请求者身份，自动选择合适的数据获取方式。

        这是秘书的核心能力：理解需求 → 获取数据 → 初步加工 → 返回给大脑。
        
        v12: 接受显式 employee_id/employee_name，不再从文本中正则猜测。
        部门名和员工姓名的匹配改为花名册已知集合的子串匹配。
        """
        results = []

        # 1. 确定部门关键词：从花名册已知部门名中做子串匹配（不从文本中正则提取）
        dept = None
        for r in (self.roster._data or []):
            d_name = str(r.get("部门", "")).strip()
            if d_name and len(d_name) >= 2 and d_name in request_text:
                dept = d_name
                break

        # 2. 优先判断是否为个人员工查询（查看/查询某人的信息、岗级、级别等）
        employee_query_keywords = ["岗级", "级别", "信息", "档案", "资料", "详情", "个人信息"]
        is_employee_query = any(kw in request_text for kw in employee_query_keywords)

        if is_employee_query:
            # 优先用显式参数查询
            matched_employee = None
            if employee_id:
                check = self.roster.query_by_employee_id(employee_id)
                if check:
                    matched_employee = check[0]
            if not matched_employee and employee_name:
                check = self.roster.query_by_name(employee_name)
                if check:
                    matched_employee = check[0]

            # 如果显式参数未提供或未命中，从花名册已知姓名做子串匹配
            if not matched_employee:
                for r in (self.roster._data or []):
                    name = str(r.get("姓名", "")).strip()
                    if name and len(name) >= 2 and name in request_text:
                        matched_employee = r
                        break

            if matched_employee:
                candidate = str(matched_employee.get("姓名", "")).strip()
                print(f"[秘书] 识别到员工姓名: {candidate}")
                detail = self.get_employee_detail(candidate)
                results.append(detail)
            elif dept:
                results.append(self.get_department_roster(dept))

        # 3. 根据请求内容选择数据源
        if any(kw in request_text for kw in ["招聘", "入职", "新员工", "人员需求"]):
            results.append(self.get_recruitment_data())

        if any(kw in request_text for kw in ["花名册", "人员", "人数", "编制"]):
            results.append(self.get_roster_summary(dept))

        if any(kw in request_text for kw in ["部门", "团队", "组织"]):
            if dept:
                results.append(self.get_department_roster(dept))

        if any(kw in request_text for kw in ["考勤", "加班", "迟到", "出勤"]):
            # 尝试自动获取考勤数据，传入已知的 employee_id/employee_name
            attendance_result = self._try_get_attendance(
                request_text, requester_identity,
                employee_id=employee_id, employee_name=employee_name,
            )
            if attendance_result:
                results.append(attendance_result)
            else:
                results.append(self.get_roster_summary(dept))

        # 4. 如果没有匹配到具体数据类型，返回通用统计
        if not results:
            results.append(self.get_roster_summary(dept))

        return "\n\n".join(results)


# 全局实例
_secretary = None

def get_secretary() -> DataSecretary:
    """获取秘书实例（单例）"""
    global _secretary
    if _secretary is None:
        _secretary = DataSecretary()
    return _secretary