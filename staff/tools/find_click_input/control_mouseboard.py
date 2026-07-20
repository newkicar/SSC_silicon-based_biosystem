# 🔴 新增：智能导入依赖库，提供友好的安装指导
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    print("⚠️ 警告：未找到 pandas 库")
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any
import os
import sys

# 🔴 修改：使用当前项目路径（staff/tools/find_click_input/ 和 staff/skills/）
_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent.parent.parent  # staff/tools/find_click_input -> project root
SKILLS_DIR = str(_project_root / "staff" / "skills")

# 🔴 修改：使用相对导入（当前项目结构）
from staff.tools.find_click_input.find_icon import find_icon
from staff.tools.find_click_input.keyboard import keyboard_type_string
from staff.tools.find_click_input.mouse import mouse_action

from langchain.tools import tool

# 全局变量：存储 find_icon 返回的坐标
last_coords = {"x": None, "y": None}


def get_skill_base_dir(skill_name_or_path: str) -> str:
    """
    根据技能名称或路径获取技能的完整目录路径

    Args:
        skill_name_or_path: 技能名称或路径（由 Agent 从 SKILL.md 读取后传递）
                           例如："skill-book-meeting-room"

    Returns:
        str: 技能的完整路径
    """
    # 构建完整路径
    skill_full_path = os.path.join(SKILLS_DIR, skill_name_or_path)

    if os.path.exists(skill_full_path):
        print(f"✅ 使用技能路径：{skill_name_or_path}")
        return skill_full_path
    else:
        print(f"⚠️ 技能路径不存在：{skill_full_path}")
        # 返回默认路径
        return SKILLS_DIR


def replace_placeholders(param_str: str, dynamic_params: Dict[str, str]) -> str:
    """
    替换参数字符串中的占位符

    Args:
        param_str: 参数字符串，包含 {param_name} 格式的占位符
        dynamic_params: 动态参数字典（由 Agent 提供，包含用户输入或 SKILL.md 默认值）

    Returns:
        str: 替换后的字符串

    Examples:
        >>> replace_placeholders("{participant}", {"participant": "张三"})
        '张三'
        >>> replace_placeholders("{meeting_name}", {"meeting_name": "重要会议"})
        '重要会议'
    """
    # 🔴 简化：只匹配 {param_name} 格式（不再支持 {param_name:default_value}）
    placeholder_pattern = r"\{(\w+)\}"

    # 检查是否有占位符
    placeholders = re.findall(placeholder_pattern, param_str)
    if not placeholders:
        return param_str

    print(f"\n🔍 [调试] 占位符替换：")
    print(f"   原始字符串: {param_str}")
    print(f"   dynamic_params: {dynamic_params}")
    print(f"   找到的占位符: {placeholders}")

    # 🔴 新增：创建大小写不敏感的参数映射
    param_map_lower = (
        {k.lower(): v for k, v in dynamic_params.items()} if dynamic_params else {}
    )

    def replace_match(match):
        param_name = match.group(1)

        # 🔴 修复：优先精确匹配
        if dynamic_params and param_name in dynamic_params:
            # 精确匹配
            new_value = str(dynamic_params[param_name])
            print(f"   ✅ 替换: {{{param_name}}} -> {new_value} (精确匹配)")
            return new_value
        # 其次大小写不敏感匹配
        elif param_map_lower and param_name.lower() in param_map_lower:
            # 大小写不敏感匹配
            new_value = str(param_map_lower[param_name.lower()])
            print(f"   ✅ 替换: {{{param_name}}} -> {new_value} (大小写不敏感匹配)")
            return new_value
        # 都没有，保留原占位符（会在后续报错）
        else:
            print(f"   ⚠️  未找到参数: {{{param_name}}}，保留原占位符")
            return match.group(0)

    result = re.sub(placeholder_pattern, replace_match, param_str)
    print(f"   替换结果: {result}\n")
    return result


def parse_parameters(
    tool_name: str, param_str: str, dynamic_params: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    解析 Excel 参数列

    Args:
        tool_name: 工具名称（mouse_action, mouse_drag, find_icon, keyboard_type_string）
        param_str: 参数字符串
        dynamic_params: 动态参数字典，用于替换占位符

    Returns:
        dict: 解析后的参数
    """
    if dynamic_params is None:
        dynamic_params = {}

    # 🔴 关键：先替换占位符
    param_str = replace_placeholders(param_str, dynamic_params)

    # 处理变量引用："上一步返回的 x" -> 全局坐标
    if last_coords["x"] is not None and last_coords["y"] is not None:
        # 替换"上一步返回的 x"和"上一步返回的 y"
        param_str = re.sub(r"上一步返回的 [x]", str(last_coords["x"]), param_str)
        param_str = re.sub(r"上一步返回的 [y]", str(last_coords["y"]), param_str)

    # 根据工具类型解析参数
    if tool_name == "mouse_action":
        # 判断是坐标还是动作
        if "=" in param_str and "," in param_str:
            # 坐标格式：x=3190,y=1930
            coords = parse_coords(param_str)

            # 🔍 新增：智能判断是否需要验证
            params = {"action": "move", **coords}

            # 检查是否有显式的 verify 参数
            if "verify=true" in param_str.lower():
                params["verify"] = True
            elif "verify=false" in param_str.lower():
                params["verify"] = False
            else:
                # 🔴 关键：如果没有显式指定 verify，根据坐标来源自动判断
                # 如果参数中包含"上一步返回的"，说明是从 find_icon 获取的坐标
                if "x" in param_str and "y" in param_str:
                    params["verify"] = False  # 用户指定坐标，不需要验证
                else:
                    params["verify"] = True  # 需要验证

            # 检查是否有 icon_image 参数
            icon_match = re.search(r"icon_image=([^,\s]+)", param_str)
            if icon_match:
                params["icon_image"] = icon_match.group(1)
            else:
                # 🔴 如果是从上一步获取的坐标，且没有指定 icon_image
                # 尝试从上一步的 find_icon 推断图标路径
                if ("x" not in param_str and "y" not in param_str) and last_coords.get(
                    "icon_path"
                ):
                    params["icon_image"] = last_coords["icon_path"]

            # 检查是否有 verify_threshold 参数
            threshold_match = re.search(r"verify_threshold=([0-9.]+)", param_str)
            if threshold_match:
                params["verify_threshold"] = float(threshold_match.group(1))

            return params
        else:
            # 动作格式：click, double_click, right_click, scroll_up, scroll_down
            return {"action": param_str.strip()}

    # 🔴 新增：解析 mouse_drag 工具
    elif tool_name == "mouse_drag":
        # 参数格式：start_x=100,start_y=200,end_x=300,end_y=400
        params = {"action": param_str.strip()}  # 直接使用参数作为动作（drag_left 等）
        return params

    elif tool_name == "find_icon":
        # 图标路径处理：如果包含路径分隔符，直接使用；否则只取文件名
        icon_path = param_str.strip()

        # 🔴 新增：支持从参数字符串中解析 max_retries 和 retry_interval
        params = {"icon_name": icon_path}

        # 解析 max_retries
        retries_match = re.search(r"max_retries=(\d+)", param_str)
        if retries_match:
            params["max_retries"] = int(retries_match.group(1))

        # 解析 retry_interval
        interval_match = re.search(r"retry_interval=([0-9.]+)", param_str)
        if interval_match:
            params["retry_interval"] = float(interval_match.group(1))

        return params

    elif tool_name == "keyboard_type_string":
        # 文本或快捷键（函数内部已处理<>）
        return {"text": param_str.strip()}

    return {}


def parse_coords(param_str: str) -> Dict[str, int]:
    """
    解析坐标参数字符串

    Args:
        param_str: 如 "x=3190,y=1930"

    Returns:
        dict: {"x": 3190, "y": 1930}
    """
    coords = {}
    parts = param_str.split(",")

    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            key = key.strip().lower()
            value = value.strip()

            if key in ["x", "y"] and value.isdigit():
                coords[key] = int(value)

    return coords


def is_icon_found(result: dict) -> bool:
    """
    判断 find_icon 是否成功

    Args:
        result: find_icon 的返回值（dict）

    Returns:
        bool: 是否成功
    """
    return result.get("success", False) and result.get("found", False)


def handle_jump(
    jump_instruction: str, tool_result: Any, current_step: int, total_steps: int
) -> int:
    """
    处理跳转逻辑

    Args:
        jump_instruction: 跳转列的内容
        tool_result: 工具执行结果
        current_step: 当前步骤序号（从 1 开始）
        total_steps: 总步骤数

    Returns:
        int: 下一步的序号
    """
    if pd.isna(jump_instruction) or jump_instruction == "下一步":
        # 默认下一步
        return current_step + 1

    elif "跳转到" in jump_instruction:
        # 无条件跳转：跳转到 X 步
        match = re.search(r"跳转到 (\d+)", jump_instruction)
        if match:
            target_step = int(match.group(1))
            return target_step
        return current_step + 1

    elif "如果" in jump_instruction and "否则" in jump_instruction:
        # 条件跳转
        if "找到图标" in jump_instruction:
            # 如果找到图标
            if is_icon_found(tool_result):
                # 条件成立，提取跳转步骤
                match = re.search(r"如果找到图标 [，,]跳转到 (\d+)", jump_instruction)
                if match:
                    return int(match.group(1))
            else:
                # 条件不成立，执行否则分支
                match = re.search(r"否则 [，,]跳转到 (\d+)", jump_instruction)
                if match:
                    return int(match.group(1))
                elif (
                    "否则下一步" in jump_instruction
                    or "否则就下一步" in jump_instruction
                ):
                    return current_step + 1

        elif "未找到图标" in jump_instruction:
            # 如果未找到图标
            if not is_icon_found(tool_result):
                # 条件成立，提取跳转步骤
                match = re.search(r"如果未找到图标 [，,]跳转到 (\d+)", jump_instruction)
                if match:
                    return int(match.group(1))
            else:
                # 条件不成立，执行否则分支
                match = re.search(r"否则 [，,]跳转到 (\d+)", jump_instruction)
                if match:
                    return int(match.group(1))
                elif (
                    "否则下一步" in jump_instruction
                    or "否则就下一步" in jump_instruction
                ):
                    return current_step + 1

    elif "结束" in jump_instruction:
        # 结束流程
        return total_steps + 1

    # 默认下一步
    return current_step + 1


def execute_tool(tool_name: str, params: Dict[str, Any]) -> Any:
    """
    执行工具函数

    Args:
        tool_name: 工具名称
        params: 参数字典

    Returns:
        dict: 工具执行结果（统一返回 dict）
    """
    global last_coords

    if tool_name == "mouse_action":
        action = params.get("action", "")

        # 执行鼠标动作
        if action == "move":
            x = params.get("x")
            y = params.get("y")

            # 🔍 支持位置验证参数
            verify = params.get("verify", False)
            icon_image = params.get("icon_image")
            verify_threshold = params.get("verify_threshold", 0.85)

            if x is not None and y is not None:
                result = mouse_action(
                    action="move",
                    x=x,
                    y=y,
                    verify=verify,
                    icon_image=icon_image,
                    verify_threshold=verify_threshold,
                )
            else:
                # 如果没有指定坐标，使用全局坐标
                if last_coords["x"] is not None and last_coords["y"] is not None:
                    result = mouse_action(
                        action="move",
                        x=last_coords["x"],
                        y=last_coords["y"],
                        verify=verify,
                        icon_image=icon_image,
                        verify_threshold=verify_threshold,
                    )
                else:
                    return {"success": False, "error": "move 操作需要提供坐标"}
        else:
            result = mouse_action(action=action)
        
        # 🔴 新增：鼠标操作后停顿 0.2 秒，给系统反应时间
        time.sleep(0.2)

        return result

    # 🔴 新增：执行 mouse_drag 工具
    elif tool_name == "mouse_drag":
        action = params.get("action", "")
        # mouse_drag 的参数直接包含拖拽方向（如 drag_left）
        # 后续可以扩展为实际执行拖拽动作
        return {"success": True, "message": f"拖拽操作：{action}", "action": action}

    elif tool_name == "find_icon":
        icon_name = params.get("icon_name", "")

        # 直接使用 icon_name（可能已经包含完整路径或相对路径）
        result = find_icon(
            icon_name=icon_name,
            threshold=0.8,
        )

        # 如果成功，更新全局坐标
        if is_icon_found(result):
            last_coords["x"] = result["coords"][0]
            last_coords["y"] = result["coords"][1]

            # 🔴 新增：保存图标路径，供后续 mouse_action 使用
            last_coords["icon_path"] = icon_name

            # 打印重试信息
            if result.get("retries", 1) > 1:
                print(f"✅ 找到图标 '{icon_name}'（第 {result['retries']} 次尝试）")
        else:
            # 查找失败，返回错误信息
            print(f"\n❌ 图标查找失败：{icon_name}")
            print(f"   尝试次数：{result.get('retries', 'N/A')} 次")
            print(f"   错误信息：{result.get('error', '未知错误')}")

        return result

    elif tool_name == "keyboard_type_string":
        text = params.get("text", "")
        result = keyboard_type_string(text=text)
        
        # 🔴 新增：键盘输入后停顿 0.5 秒，给系统反应时间
        time.sleep(0.5)
        
        return result

    return {"success": False, "error": f"未知工具：{tool_name}"}


@tool
def execute_workflow(
    workflow_filename: str,
    skill_name: str = "",
    start_step: int = 1,
    dynamic_params: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    执行工作流

    Args:
        workflow_filename: Excel 文件名（如“下载 SAP 花名册工作流.xlsx”）
        skill_name: 技能目录名称（由 Agent 从 SKILL.md 读取后传递，列标为：skill文件路径）
        start_step: 起始步骤序号（从 1 开始），默认从第 1 步开始
        dynamic_params: 动态参数字典，用于替换 Excel 中的占位符（可选）
                       例如：{"search_keyword": "张三", "department": "技术部"}

    Returns:
        dict: {"messages": "执行结果"}
    """
    # 🔴 关键修复：检查 pandas 是否可用
    if not HAS_PANDAS:
        return {
            "success": False,
            "message": "❌ 缺少必要依赖库：pandas\n\n请使用以下命令安装：\npip install pandas openpyxl\n\n安装完成后重新执行任务。",
            "error_type": "MISSING_DEPENDENCY",
            "required_packages": ["pandas", "openpyxl"]
        }
    
    global last_coords

    if dynamic_params is None:
        dynamic_params = {}

    try:
        # 🔴 修改：动态获取技能路径（由 Agent 传递）
        skill_base_dir = get_skill_base_dir(skill_name)

        # 技能目录配置 - 使用绝对路径
        SKILL_BASE_PATH = Path(skill_base_dir)
        REFERENCES_DIR = SKILL_BASE_PATH / "references"
        ICON_SHOT_DIR = SKILL_BASE_PATH / "icon_shot"

        # 1. 读取 Excel 文件
        excel_path = REFERENCES_DIR / workflow_filename
        if not excel_path.exists():
            return {"messages": f"错误：工作流文件不存在：{excel_path}"}

        df = pd.read_excel(excel_path)

        # 2. 验证起始步骤
        total_steps = len(df)
        if start_step < 1 or start_step > total_steps:
            return {
                "messages": f"错误：起始步骤 {start_step} 无效，有效范围：1-{total_steps}"
            }

        # 3. 初始化变量
        current_row = start_step - 1  # 行索引（从 0 开始）
        executed_steps = []
        skipped_steps = []

        # 4. 循环执行
        while current_row < total_steps:
            row = df.iloc[current_row]
            current_step = current_row + 1  # 步骤序号（从 1 开始）

            # 6. 获取工具名和参数
            tool_name = row["对应工具"]
            param_str = str(row["参数"]) if pd.notna(row["参数"]) else ""
            jump_instruction = str(row["跳转"]) if pd.notna(row["跳转"]) else "下一步"

            # 5. 解析参数（传入 dynamic_params）
            params = parse_parameters(
                tool_name, param_str, dynamic_params=dynamic_params
            )

            # 6. 如果是跳过的步骤，只记录不执行
            if current_step < start_step:
                skipped_steps.append(current_step)
                # 直接跳转到下一步
                current_row += 1
                continue

            # 7. 解析参数（传入 dynamic_params）
            params = parse_parameters(
                tool_name, param_str, dynamic_params=dynamic_params
            )

            # 8. 执行工具
            result = execute_tool(tool_name, params)
            executed_steps.append(
                {"step": current_step, "tool": tool_name, "result": result}
            )

            print(f"✅ 步骤 {current_step} 执行成功：{result}")

            # 🔴 关键：统一错误检查（所有工具都返回 dict）
            if isinstance(result, dict):
                if not result.get("success", True):
                    error_msg = result.get("error", str(result))
                    print(f"❌ 步骤 {current_step} 执行失败：{error_msg}")
                    return {
                        "messages": f"任务执行失败：步骤 {current_step} ({tool_name}) - {error_msg}"
                    }

            # 🔴 特别处理：find_icon 失败，立即终止
            if tool_name == "find_icon" and not is_icon_found(result):
                icon_name = params.get("icon_name", "未知图标")
                print(f"\n❌ 步骤 {current_step}: 查找图标 '{icon_name}' 失败")
                print(f"💀 程序终止，不再继续执行后续步骤")
                return {
                    "messages": f"任务执行失败：步骤 {current_step} - 未找到图标 '{icon_name}'，程序已终止"
                }

            # 9. 处理跳转
            next_step = handle_jump(jump_instruction, result, current_step, total_steps)

            # 🔴 关键修复：确保 next_step 一定大于 current_step，防止死循环
            if next_step <= current_step:
                print(
                    f"⚠️ 警告：跳转目标 {next_step} <= 当前步骤 {current_step}，强制跳到下一步"
                )
                next_step = current_step + 1

            # 10. 检查是否需要结束
            if next_step > total_steps:
                break

            # 11. 跳转到下一步
            current_row = next_step - 1  # 转换为行索引

        # 12. 返回结果
        return {"messages": "任务执行成功。"}

    except Exception as e:
        import traceback

        error_detail = traceback.format_exc()
        print(f"错误详情：{error_detail}")
        return {"messages": f"任务执行失败：{str(e)}"}


if __name__ == "__main__":
    """测试入口"""
    print("=" * 60)
    print("GUI 自动化工作流引擎 - 测试模式")
    print("=" * 60)

    # 测试执行工作流
    result = execute_workflow.invoke("下载SAP花名册")

    print(f"\n执行结果：{result['messages']}")
    print("=" * 60)
