"""
SSC硅基生物系统 - 员工端工具集

提供给 deepagents agent 使用的自定义工具：
- execute_workflow: GUI自动化工作流执行引擎（鼠标键盘操作）
"""


def get_tools():
    """获取所有可用的自定义工具列表，供 deepagents agent 使用"""
    tools = []

    # 1. GUI自动化工作流执行工具（预约会议室、SAP操作等）
    try:
        from staff.tools.find_click_input.control_mouseboard import execute_workflow
        tools.append(execute_workflow)
    except ImportError as e:
        print(f"⚠️ execute_workflow 工具加载失败: {e}")

    # 未来添加更多工具...
    # try:
    #     from staff.tools.xxx import yyy
    #     tools.append(yyy)
    # except ImportError:
    #     pass

    return tools