"""
员工数据库查询工具
上行脊髓通过此工具主动拉取员工档案信息，进行数据预取。
"""
from langchain.tools import tool


# MVP阶段：模拟员工数据库（后续替换为真实HRIS接口）
MOCK_EMPLOYEES = {
    "EMP001": {
        "name": "张三",
        "department": "研发二部",
        "position": "高级工程师",
        "hire_date": "2021-03-15",
        "social_insurance_location": "上海",
        "annual_leave_remaining": 8,
        "contract_end_date": "2026-03-14",
    },
    "EMP002": {
        "name": "李四",
        "department": "市场部",
        "position": "市场经理",
        "hire_date": "2019-07-01",
        "social_insurance_location": "北京",
        "annual_leave_remaining": 12,
        "contract_end_date": "2025-06-30",
    },
}


@tool
def query_employee_db(employee_id: str) -> str:
    """查询员工数据库，获取员工档案信息。
    当需要了解员工的基本信息、薪资、社保、合同等情况时使用。
    Args:
        employee_id: 员工工号（如 EMP001）
    """
    employee = MOCK_EMPLOYEES.get(employee_id.upper())
    if not employee:
        return f"未找到工号为 {employee_id} 的员工记录。请确认工号是否正确。"

    lines = [f"员工档案 - {employee['name']}（{employee_id}）"]
    lines.append(f"  部门：{employee['department']}")
    lines.append(f"  岗位：{employee['position']}")
    lines.append(f"  入职日期：{employee['hire_date']}")
    lines.append(f"  社保缴纳地：{employee['social_insurance_location']}")
    lines.append(f"  剩余年假：{employee['annual_leave_remaining']}天")
    lines.append(f"  合同到期日：{employee['contract_end_date']}")
    return "\n".join(lines)