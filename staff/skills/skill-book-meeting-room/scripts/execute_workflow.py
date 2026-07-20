"""
会议室预约工作流执行器
读取 Excel 工作流文件，使用 pyautogui 模拟鼠标键盘操作

用法：python staff/skills/skill-book-meeting-room/scripts/execute_workflow.py --workflow 预约会议室工作流.xlsx --params '{"meeting_name":"xxx","meeting_date":"2026-06-08","start_time":"08:30","end_time":"17:00","participant":"赵卫玲"}'
"""
import sys
import os
import json
import time
import argparse
from pathlib import Path

# 设置项目根目录
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def load_workflow(xlsx_path):
    """读取 Excel 工作流文件"""
    try:
        import openpyxl
    except ImportError:
        print("[ERROR] 需要安装 openpyxl: pip install openpyxl")
        sys.exit(1)
    
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active
    steps = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:  # 跳过表头
            continue
        if row[0] is None:
            continue
        step = {
            "step": row[0],
            "tool": row[1],
            "action": row[2],
            "param": str(row[3]) if row[3] else "",
            "note": str(row[4]) if row[4] else "",
            "flow": str(row[5]) if row[5] else "下一步",
        }
        steps.append(step)
    return steps


def replace_params(text, params):
    """替换文本中的动态参数 {key} -> value"""
    result = text
    for key, value in params.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


def find_icon_on_screen(icon_path, confidence=0.8, retries=3, retry_delay=1.0):
    """在屏幕上查找图标，返回中心坐标 (x, y)。
    
    支持重试机制：最多尝试 retries 次，每次间隔 retry_delay 秒。
    置信度默认提高到 0.8 减少误匹配。
    
    注意：OpenCV 在 Windows 下无法读取包含非ASCII字符（如中文）的路径，
    所以需要将图标文件复制到临时目录再读取。
    """
    try:
        import pyautogui
    except ImportError:
        print("[ERROR] 需要安装 pyautogui: pip install pyautogui")
        sys.exit(1)
    
    if not os.path.exists(icon_path):
        print(f"[WARN] 图标文件不存在: {icon_path}")
        return None
    
    # 处理非ASCII路径：如果路径包含非ASCII字符，复制到临时目录
    import tempfile
    import shutil
    temp_icon_path = None
    actual_path = icon_path
    try:
        icon_path.encode('ascii')
    except UnicodeEncodeError:
        # 路径含中文，需要复制到临时目录
        try:
            ext = os.path.splitext(icon_path)[1]  # .png
            tmp_dir = tempfile.gettempdir()
            # 用原文件名的hash作临时文件名，避免冲突
            tmp_name = f"_ssc_icon_{hash(icon_path) & 0xFFFFFFFF:08x}{ext}"
            temp_icon_path = os.path.join(tmp_dir, tmp_name)
            if not os.path.exists(temp_icon_path):
                shutil.copy2(icon_path, temp_icon_path)
            actual_path = temp_icon_path
        except Exception as e:
            print(f"[WARN] 临时文件创建失败: {e}")
    
    # 重试机制：多次查找，避免因界面加载延迟而漏检
    for attempt in range(retries):
        try:
            location = pyautogui.locateOnScreen(actual_path, confidence=confidence)
            if location:
                center = pyautogui.center(location)
                return (center.x, center.y)
        except Exception as e:
            print(f"[WARN] 查找图标异常 (第{attempt+1}次): {e}")
            return None
        
        if attempt < retries - 1:
            print(f"  ⏳ 未找到，{retry_delay}秒后重试 ({attempt+1}/{retries})...")
            time.sleep(retry_delay)
    
    return None


def execute_mouse_action(action, param, last_pos):
    """执行鼠标操作。
    
    对于需要坐标的操作（鼠标移动、单击、双击），如果 last_pos 为 None，
    则拒绝执行并返回 False，防止在错误位置操作。
    """
    try:
        import pyautogui
    except ImportError:
        print("[ERROR] 需要安装 pyautogui: pip install pyautogui")
        sys.exit(1)
    
    if action == "鼠标移动":
        if last_pos:
            pyautogui.moveTo(last_pos[0], last_pos[1], duration=0.3)
            print(f"  🖱️ 移动到 ({last_pos[0]}, {last_pos[1]})")
        else:
            print(f"  ❌ 无有效坐标，跳过鼠标移动")
            return False
    elif action == "鼠标单击":
        if last_pos:
            # 先移动到目标位置，再点击
            pyautogui.moveTo(last_pos[0], last_pos[1], duration=0.2)
            time.sleep(0.1)
            if param == "double_click":
                pyautogui.doubleClick()
                print(f"  🖱️ 移动到 ({last_pos[0]}, {last_pos[1]}) 后双击")
            elif param == "right_click":
                pyautogui.rightClick()
                print(f"  🖱️ 移动到 ({last_pos[0]}, {last_pos[1]}) 后右键单击")
            else:
                pyautogui.click()
                print(f"  🖱️ 移动到 ({last_pos[0]}, {last_pos[1]}) 后单击")
        else:
            print(f"  ❌ 无有效坐标，跳过鼠标单击")
            return False
    elif action == "鼠标双击":
        if last_pos:
            pyautogui.moveTo(last_pos[0], last_pos[1], duration=0.2)
            time.sleep(0.1)
            pyautogui.doubleClick()
            print(f"  🖱️ 移动到 ({last_pos[0]}, {last_pos[1]}) 后双击")
        else:
            print(f"  ❌ 无有效坐标，跳过鼠标双击")
            return False
    elif action == "滚轮向下":
        pyautogui.scroll(-3)
        print(f"  🖱️ 滚轮向下")
    elif action == "滚轮向上":
        pyautogui.scroll(3)
        print(f"  🖱️ 滚轮向上")
    else:
        print(f"  ⚠️ 未知鼠标操作: {action} / {param}")
        return False
    return True


def execute_keyboard_action(param):
    """执行键盘操作"""
    try:
        import pyautogui
    except ImportError:
        print("[ERROR] 需要安装 pyautogui: pip install pyautogui")
        sys.exit(1)
    
    # 处理特殊键和快捷键
    if param.startswith("<") and param.endswith(">"):
        # 快捷键或特殊键
        key_content = param[1:-1]
        
        # 组合键（如 ctrl+a, shift）
        if "+" in key_content:
            keys = [k.strip() for k in key_content.split("+")]
            pyautogui.hotkey(*keys)
            print(f"  ⌨️ 快捷键: {'+'.join(keys)}")
        else:
            # 单个特殊键
            key_map = {
                "shift": "shift",
                "ctrl": "ctrl",
                "alt": "alt",
                "enter": "enter",
                "tab": "tab",
                "esc": "escape",
                "backspace": "backspace",
                "delete": "delete",
                "space": "space",
                "up": "up",
                "down": "down",
                "left": "left",
                "right": "right",
            }
            key = key_map.get(key_content.lower(), key_content)
            pyautogui.press(key)
            print(f"  ⌨️ 按键: {key}")
    else:
        # 普通文本输入
        pyautogui.typewrite(param, interval=0.05) if param.isascii() else pyautogui.write(param)
        print(f"  ⌨️ 输入: {param}")


def run_workflow(xlsx_path, params, confidence=0.8):
    """执行完整工作流
    
    核心逻辑：
    1. find_icon 步骤：查找图标，找到则设置 last_pos + icon_ready=True，
       未找到则清空 last_pos + icon_ready=False，并重试3次
    2. mouse_action 步骤：检查 icon_ready，未就绪则跳过，不在错误位置操作
    3. keyboard_type_string 步骤：也检查 icon_ready，确保在正确界面下才输入
    4. 每次 find_icon 成功后 icon_ready 保持 True，直到下一个 find_icon
    """
    print(f"\n{'='*50}")
    print(f"📋 加载工作流: {xlsx_path}")
    steps = load_workflow(xlsx_path)
    print(f"📊 共 {len(steps)} 个步骤")
    print(f"📝 参数: {json.dumps(params, ensure_ascii=False)}")
    print(f"🎯 置信度阈值: {confidence}")
    print(f"{'='*50}\n")
    
    # 工作流文件所在目录（用于查找图标）
    workflow_dir = os.path.dirname(os.path.abspath(xlsx_path))
    # Skill 根目录（icon_shot 在这里）
    skill_dir = os.path.dirname(workflow_dir)  # 上一级就是 skill 根目录
    # Skills 父目录（Excel中的图标路径如 skill-book-meeting-room/icon_shot/1.png
    # 是相对于 staff/skills/ 目录的，不是相对于 skill_dir）
    skills_parent_dir = os.path.dirname(skill_dir)  # staff/skills/
    
    last_pos = None       # 上一次成功找到的图标坐标
    icon_ready = False     # 当前是否处于"图标已定位"状态
    total = len(steps)
    skipped_count = 0      # 因图标未找到而跳过的步骤数
    
    for idx, step in enumerate(steps):
        step_num = step["step"]
        tool = step["tool"]
        action = step["action"]
        param = replace_params(step["param"], params)
        
        print(f"\n[Step {step_num}/{total}] {tool} - {action}")
        
        try:
            if tool == "find_icon":
                # Excel中的图标路径如 "skill-book-meeting-room/icon_shot/1.png"
                # 是相对于 staff/skills/ 目录的（skills_parent_dir）
                icon_path = os.path.join(skills_parent_dir, param)
                if not os.path.exists(icon_path):
                    # 也尝试从 skill 根目录找（兼容旧格式）
                    icon_path = os.path.join(skill_dir, param)
                if not os.path.exists(icon_path):
                    # 最后尝试从 references 目录找
                    icon_path = os.path.join(workflow_dir, param)
                
                pos = find_icon_on_screen(icon_path, confidence=confidence)
                if pos:
                    last_pos = pos
                    icon_ready = True
                    print(f"  ✅ 找到图标: ({pos[0]}, {pos[1]})")
                else:
                    last_pos = None
                    icon_ready = False
                    print(f"  ❌ 未找到图标: {param}（后续操作将跳过，直到找到下一个图标）")
                    
            elif tool == "mouse_action":
                if not icon_ready:
                    print(f"  ⛔ 跳过：图标未定位，不在错误位置操作鼠标")
                    skipped_count += 1
                    continue
                success = execute_mouse_action(action, param, last_pos)
                if not success:
                    icon_ready = False  # 操作失败，标记为未就绪
                    
            elif tool == "keyboard_type_string":
                if not icon_ready:
                    print(f"  ⛔ 跳过：图标未定位，不在错误界面输入内容")
                    skipped_count += 1
                    continue
                execute_keyboard_action(param)
                
            else:
                print(f"  ⚠️ 未知工具: {tool}")
                
        except Exception as e:
            print(f"  ❌ 执行异常: {e}")
            icon_ready = False  # 异常后标记为未就绪，防止后续瞎操作
        
        # 每步之间短暂等待，让界面响应
        time.sleep(0.3)
    
    print(f"\n{'='*50}")
    print(f"✅ 工作流执行完成！共 {total} 个步骤")
    if skipped_count > 0:
        print(f"⚠️ 其中 {skipped_count} 个步骤因图标未定位而跳过")
    print(f"{'='*50}\n")
    
    return skipped_count == 0  # 返回是否全部成功执行


def main():
    parser = argparse.ArgumentParser(description="会议室预约工作流执行器")
    parser.add_argument("--workflow", required=True, help="工作流 Excel 文件名")
    parser.add_argument("--skill-name", default="skill-book-meeting-room", help="Skill 目录名")
    parser.add_argument("--params", default="{}", help="动态参数 JSON 字符串")
    parser.add_argument("--confidence", type=float, default=0.8, help="图标匹配置信度（默认0.8，越高越严格）")
    args = parser.parse_args()
    
    # 设置 pyautogui 置信度
    try:
        import pyautogui
        pyautogui.FAILSAFE = True  # 启用安全模式（鼠标移到左上角可中断）
    except ImportError:
        pass
    
    # 解析参数
    try:
        params = json.loads(args.params)
    except json.JSONDecodeError:
        print(f"[ERROR] 参数 JSON 格式错误: {args.params}")
        sys.exit(1)
    
    # 查找工作流文件 - 从 skill 的 references 目录找
    skill_dir = Path(__file__).resolve().parent.parent  # skill-book-meeting-room/
    workflow_path = skill_dir / "references" / args.workflow
    
    if not workflow_path.exists():
        # 尝试其他路径
        workflow_path = Path(args.workflow)
        if not workflow_path.exists():
            print(f"[ERROR] 工作流文件不存在: {args.workflow}")
            print(f"  尝试路径: {skill_dir / 'references' / args.workflow}")
            sys.exit(1)
    
    all_ok = run_workflow(str(workflow_path), params, confidence=args.confidence)
    if not all_ok:
        print("⚠️ 工作流未完全执行，部分步骤被跳过。请检查：")
        print("  1. 目标软件窗口是否已打开并显示在屏幕上？")
        print("  2. 屏幕分辨率/缩放比例是否与截图时一致？")
        print("  3. 截图是否清晰、尺寸足够大（建议至少 30x30 像素）？")
        sys.exit(1)


if __name__ == "__main__":
    main()