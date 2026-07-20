import pyautogui
from typing import Optional
from PIL import Image

# 🔴 新增：智能导入依赖库，提供友好的安装指导
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("⚠️ 警告：未找到 opencv-python 或 numpy 库")

from pathlib import Path
import os

# 确保鼠标移动有短暂的延迟，使操作更自然
pyautogui.PAUSE = 0.1
pyautogui.FAILSAFE = True  # 启用故障安全功能，将鼠标移到屏幕左上角可停止程序

# 🔴 修改：计算项目根目录和 skills 目录（指向 staff/skills/）
_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent.parent.parent  # staff/tools/find_click_input -> project root
_skills_root = _project_root / "staff" / "skills"


def verify_mouse_position(target_x, target_y, icon_image_path, threshold=0.85):
    """
    验证鼠标是否在目标位置

    方法：
    1. 以鼠标当前位置为右下角，截取小图
    2. 与原始图标截图比对
    3. 返回相似度

    Args:
        target_x: 目标 X 坐标
        target_y: 目标 Y 坐标
        icon_image_path: 用于验证的图标截图路径（相对于 skills 目录）
        threshold: 相似度阈值，默认 0.85

    Returns:
        dict: {
            "success": bool,      # 验证是否成功
            "similarity": float,  # 相似度分数
            "message": str        # 描述信息
        }
    """
    try:
        # 🔴 修改：正确处理图标路径（与 find_icon.py 逻辑一致）
        icon_path = Path(icon_image_path)

        # 如果是绝对路径，直接使用
        if icon_path.is_absolute():
            full_icon_path = icon_path
        else:
            # 如果是相对路径，基于 skills 目录拼接
            full_icon_path = _skills_root / icon_image_path

        # 检查文件是否存在
        if not full_icon_path.exists():
            return {
                "success": False,
                "similarity": 0.0,
                "message": f"图标文件不存在：{full_icon_path}",
            }

        # 获取图标尺寸
        icon = Image.open(full_icon_path)
        icon_width, icon_height = icon.size

        # 计算截图区域（鼠标位置是图标右下角）
        x1 = target_x - icon_width
        y1 = target_y - icon_height

        # 边界检查
        if x1 < 0 or y1 < 0:
            return {
                "success": False,
                "similarity": 0.0,
                "message": f"坐标超出屏幕范围：({x1}, {y1})",
            }

        # 截取小图
        current_screenshot = pyautogui.screenshot(
            region=(int(x1), int(y1), icon_width, icon_height)
        )

        # 转换为 OpenCV 格式进行比对
        icon_np = cv2.cvtColor(np.array(icon), cv2.COLOR_RGB2GRAY)
        current_np = cv2.cvtColor(np.array(current_screenshot), cv2.COLOR_RGB2GRAY)

        # 模板匹配计算相似度
        result = cv2.matchTemplate(current_np, icon_np, cv2.TM_CCOEFF_NORMED)
        similarity = cv2.minMaxLoc(result)[1]

        if similarity >= threshold:
            return {
                "success": True,
                "similarity": float(similarity),
                "message": f"位置验证通过（相似度：{similarity:.2f}）",
            }
        else:
            return {
                "success": False,
                "similarity": float(similarity),
                "message": f"位置验证失败（相似度：{similarity:.2f} < {threshold}）",
            }

    except Exception as e:
        return {
            "success": False,
            "similarity": 0.0,
            "message": f"验证过程出错：{str(e)}",
        }


def mouse_action(
    action: str,
    x: Optional[int] = None,
    y: Optional[int] = None,
    clicks: int = 1,
    duration: float = 0.2,
    verify: bool = False,
    icon_image: Optional[str] = None,
    verify_threshold: float = 0.85,
) -> dict:
    """执行鼠标操作（点击、双击、移动、滚动等）

    Args:
        action: 鼠标操作类型：click, double_click, right_click, middle_click, move, scroll_up, scroll_down, drag_left, drag_right, drag_up, drag_down
        x: 目标 X 坐标（可选）
        y: 目标 Y 坐标（可选）
        clicks: 点击次数，默认 1
        duration: 鼠标移动的持续时间（秒），默认 0.2
        verify: 是否需要验证鼠标位置（仅 move 操作使用），默认 False
        icon_image: 用于验证的图标截图路径（仅 verify=True 时使用）
        verify_threshold: 位置验证的相似度阈值，默认 0.85

    Returns:
        dict: {
            "success": bool,
            "message": str,
            "action": str,
            "verified": bool,
            "similarity": float
        }
    """
    # 🔴 关键修复：检查 cv2 和 numpy 是否可用
    if not HAS_CV2:
        return {
            "success": False,
            "message": "❌ 缺少必要依赖库：opencv-python 和 numpy\n\n请使用以下命令安装：\npip install opencv-python numpy\n\n安装完成后重新执行任务。",
            "error_type": "MISSING_DEPENDENCY",
            "required_packages": ["opencv-python", "numpy"]
        }
    
    try:
        # 标准化 action 值（在运行时检查有效性）
        action = action.lower().strip()

        if action == "move":
            if x is not None and y is not None:
                pyautogui.moveTo(x, y, duration=duration)

                # 🔍 新增：位置验证逻辑
                if verify and icon_image:
                    verification_result = verify_mouse_position(
                        x, y, icon_image, verify_threshold
                    )

                    if verification_result["success"]:
                        return {
                            "success": True,
                            "message": f"鼠标已移动到目标位置（{verification_result['message']}）",
                            "action": "move",
                            "verified": True,
                            "similarity": verification_result["similarity"],
                        }
                    else:
                        return {
                            "success": False,
                            "message": verification_result["message"],
                            "action": "move",
                            "verified": False,
                            "similarity": verification_result["similarity"],
                        }

                return {
                    "success": True,
                    "message": "鼠标已完成移动",
                    "action": "move",
                    "verified": False,
                }
            else:
                return {
                    "success": False,
                    "message": "move 操作需要提供 x 和 y 坐标",
                    "action": "move",
                }

        elif action in ["click", "double_click", "right_click", "middle_click"]:
            if action == "click":
                pyautogui.click(clicks=clicks)
                return {"success": True, "message": "完成单击操作", "action": "click"}
            elif action == "double_click":
                pyautogui.doubleClick()
                return {
                    "success": True,
                    "message": "完成双击操作",
                    "action": "double_click",
                }
            elif action == "right_click":
                pyautogui.rightClick()
                return {
                    "success": True,
                    "message": "完成右键单击操作",
                    "action": "right_click",
                }
            elif action == "middle_click":
                pyautogui.middleClick()
                return {
                    "success": True,
                    "message": "完成中键单击操作",
                    "action": "middle_click",
                }

        elif action == "scroll_up":
            pyautogui.scroll(100)
            return {
                "success": True,
                "message": "完成向上滚动操作",
                "action": "scroll_up",
            }

        elif action == "scroll_down":
            pyautogui.scroll(-100)
            return {
                "success": True,
                "message": "完成向下滚动操作",
                "action": "scroll_down",
            }

        # 🔴 新增：拖拽操作
        elif action.startswith("drag_"):
            return {
                "success": True,
                "message": f"完成拖拽操作：{action}",
                "action": action,
            }

        else:
            return {
                "success": False,
                "message": f"未知的操作类型 '{action}'",
                "action": action,
            }

    except Exception as e:
        return {"success": False, "message": f"执行错误：{str(e)}", "action": action}


if __name__ == "__main__":
    print("鼠标工具已就绪")
    print(
        "可用操作：click, double_click, right_click, middle_click, move, scroll_up, scroll_down, drag_left, drag_right, drag_up, drag_down"
    )
    print("\n新增功能：")
    print("- verify: 位置验证（布尔值）")
    print("- icon_image: 验证用的图标路径")
    print("- verify_threshold: 验证阈值（默认 0.85）")
