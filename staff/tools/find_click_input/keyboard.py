import pyautogui
import time
import re


# 🔴 新增：导入 pyperclip 用于中文输入
try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False


def _type_chinese_via_clipboard(text: str) -> dict:
    """通过剪贴板方式输入中文文本
    
    Args:
        text: 要输入的中文文本
        
    Returns:
        dict: 操作结果
    """
    try:
        # 1. 复制文本到剪贴板
        pyperclip.copy(text)
        time.sleep(0.1)  # 等待剪贴板更新
        
        # 2. 模拟 Ctrl+V 粘贴
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.2)  # 等待粘贴完成
        
        return {
            "success": True,
            "message": f"输入完成：文本：{text}（通过剪贴板）",
            "input_text": text,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"中文输入失败：{str(e)}",
            "input_text": text,
        }


def keyboard_type_string(text: str, interval: float = 0.1) -> dict:
    """智能键盘输入：支持快捷键标记和普通文本混合输入

    Args:
        text: 输入内容，支持以下格式：
            - <enter>: 按 Enter 键
            - <ctrl+c>: 按 Ctrl+C 组合键
            - <F5>: 按 F5 键
            - hello: 输入文本 "hello"
            - 中文文本：自动使用剪贴板方式
            - 混合模式："请先<ctrl+v>粘贴，然后输入完成"
        interval: 打字间隔（秒），默认 0.1

    Returns:
        dict: {
            "success": bool,      # 操作是否成功
            "message": str,       # 操作描述
            "input_text": str     # 实际输入的文本
        }
    """
    try:
        # 🔴 关键修复：检测是否包含中文字符
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in text)
        
        # 如果包含中文且 pyperclip 可用，使用剪贴板方式
        if has_chinese and HAS_PYPERCLIP:
            return _type_chinese_via_clipboard(text)
        
        # 🔴 新增：如果包含中文但 pyperclip 不可用，给出警告
        if has_chinese and not HAS_PYPERCLIP:
            return {
                "success": False,
                "message": "中文输入需要 pyperclip 库，请安装：pip install pyperclip",
                "input_text": text,
            }

        # 定义有效的功能键集合
        special_keys = {
            "enter",
            "tab",
            "escape",
            "esc",
            "capslock",
            "numberlock",
            "scrolllock",
            "backspace",
            "delete",
            "up",
            "down",
            "left",
            "right",
            "home",
            "end",
            "pageup",
            "pagedown",
            "f1",
            "f2",
            "f3",
            "f4",
            "f5",
            "f6",
            "f7",
            "f8",
            "f9",
            "f10",
            "f11",
            "f12",
            "space",
            "insert",
            "print",
            "pause",
            "ctrl",
            "alt",
            "shift",
            "win",
        }

        # 正则表达式：匹配 <...> 格式的标记
        pattern = r"<([^>]+)>"

        # 分割文本为多个片段
        fragments = re.split(pattern, text)

        executed_actions = []
        i = 0

        while i < len(fragments):
            fragment = fragments[i]

            # 判断是否是标记内容（奇数索引是<> 内的内容）
            if i % 2 == 1:
                # 这是<...> 内的内容，解析为快捷键
                key_content = fragment.strip().lower()
                keys = [k.strip() for k in key_content.split("+")]

                # 验证是否全是有效键
                if all(key in special_keys or len(key) == 1 for key in keys):
                    if len(keys) > 1:
                        # 组合键
                        pyautogui.hotkey(*keys)
                        executed_actions.append(f"组合键：{key_content}")
                    else:
                        # 单键
                        pyautogui.press(keys[0])
                        executed_actions.append(f"按键：{keys[0]}")
                else:
                    # 无效的键名，作为普通文本输入
                    pyautogui.write(f"<{fragment}>", interval=interval)
                    executed_actions.append(f"文本：<{fragment}>")

            elif i % 2 == 0 and fragment:
                # 这是普通文本（偶数索引是<> 外的内容）
                pyautogui.write(fragment, interval=interval)
                executed_actions.append(f"文本：{fragment}")

            i += 1

        action_summary = " → ".join(executed_actions)
        return {
            "success": True,
            "message": f"输入完成：{action_summary}",
            "input_text": text,
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"键盘输入失败：{str(e)}",
            "input_text": text,
        }


# 示例用法（实际使用时请取消注释并调整）
if __name__ == "__main__":
    print("准备执行键盘输入测试...")
    print("请在 3 秒内切换到目标窗口...\n")
    time.sleep(3)

    # 测试1：快捷键
    result = keyboard_type_string("<ctrl+a>", interval=0.05)
    print(f"测试 1 - 快捷键：{result}")

    time.sleep(1)

    # 测试2：英文文本
    result = keyboard_type_string("hello world", interval=0.05)
    print(f"测试 2 - 英文：{result}")

    time.sleep(1)

    # 测试3：中文文本（新增）
    result = keyboard_type_string("重要会议", interval=0.05)
    print(f"测试 3 - 中文：{result}")

    time.sleep(1)

    # 测试4：混合输入（新增）
    result = keyboard_type_string("会议主题：季度总结会")
    print(f"测试 4 - 混合：{result}")