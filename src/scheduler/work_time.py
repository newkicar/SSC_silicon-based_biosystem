"""
工作时间窗口管理

功能：
- 员工配置上班时间，窗口外不计超时
- 升级策略：普通终端超时→重新分配→提醒直属上级→SSC经理24h内3次提醒
"""

from datetime import datetime

# 默认工作时间配置（可从数据库/配置文件读取）
DEFAULT_WORK_WINDOWS = {
    "weekday": {"start": "08:00", "end": "18:00"},
    "weekend": None,  # 周末不工作
}


def is_in_work_window(employee_id: str = None, config: dict = None) -> bool:
    """
    判断当前时间是否在工作窗口内。

    Args:
        employee_id: 员工ID（可选，用于查询个人配置）
        config: 自定义工作时间配置（可选）

    Returns:
        True=在工作窗口内，False=不在
    """
    now = datetime.now()
    work_config = config or DEFAULT_WORK_WINDOWS

    # 周末检查
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    if weekday >= 5:  # 周六周日
        weekend_config = work_config.get("weekend")
        if weekend_config is None:
            return False
        return _in_time_range(now, weekend_config["start"], weekend_config["end"])

    # 工作日检查
    weekday_config = work_config.get("weekday")
    if weekday_config is None:
        return True  # 默认工作日全天工作

    return _in_time_range(now, weekday_config["start"], weekday_config["end"])


def _in_time_range(now: datetime, start_str: str, end_str: str) -> bool:
    """判断当前时间是否在 start~end 范围内"""
    start_h, start_m = map(int, start_str.split(":"))
    end_h, end_m = map(int, end_str.split(":"))
    current_minutes = now.hour * 60 + now.minute
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m
    return start_minutes <= current_minutes <= end_minutes
