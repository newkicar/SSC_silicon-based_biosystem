# 🔴 新增：智能导入依赖库，提供友好的安装指导
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("⚠️ 警告：未找到 opencv-python 或 numpy 库")

from PIL import Image
import pyautogui
from typing import Optional, Literal
from pydantic import BaseModel, Field
from typing import Literal
import time

# 🔴 修改：使用当前项目路径
import sys
import os
from pathlib import Path

_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent.parent.parent  # staff/tools/find_click_input -> project root
_skills_root = _project_root / "staff" / "skills"

project_root = str(_project_root)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class FindIconInput(BaseModel):
    """查找图标的输入参数"""

    icon_name: str = Field(
        ..., description="图标截图的路径（相对于 skills 目录或完整相对路径）"
    )
    threshold: float = Field(0.8, description="模板匹配置信度阈值（0-1），默认 0.8")
    method: Literal["template", "orb"] = Field(
        "template", description="定位方法：template(模板匹配) 或 orb(特征点匹配)"
    )
    match_ratio: float = Field(
        0.75, description="特征点匹配的筛选比例（仅 ORB 方法使用）"
    )
    min_matches: int = Field(
        10, description="成功定位所需的最少匹配点对数量（仅 ORB 方法使用）"
    )


class FindIconResult(BaseModel):
    """查找图标的结果"""

    success: bool = Field(..., description="操作是否成功")
    found: bool = Field(..., description="是否找到图标")
    position: Optional[tuple] = Field(None, description="图标右下角坐标 (x, y)")
    message: str = Field(..., description="结果描述信息")
    match_confidence: Optional[float] = Field(
        None, description="匹配度（仅模板匹配方法返回）"
    )


class IconLocator:
    def __init__(self, match_ratio=0.75, min_matches=10, method="template"):
        self.orb = cv2.ORB_create(nfeatures=1000)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        self.match_ratio = match_ratio
        self.min_matches = min_matches
        self.method = method

    def find_icon(self, screen_shot, icon_shot, threshold=0.8):
        if self.method == "template":
            return self._find_by_template(screen_shot, icon_shot, threshold)
        else:
            return self._find_by_orb(screen_shot, icon_shot)

    def _find_by_template(self, screen_shot, icon_shot, threshold=0.8):
        screen_gray = self._load_and_convert(screen_shot)
        icon_gray = self._load_and_convert(icon_shot)

        h, w = icon_gray.shape

        if screen_gray.shape[0] < h or screen_gray.shape[1] < w:
            return None

        result = cv2.matchTemplate(screen_gray, icon_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            # 返回图标的右下角坐标
            bottom_right = (int(max_loc[0] + w), int(max_loc[1] + h))

            if threshold < 1.0:
                self._visualize_template(screen_gray, icon_gray, max_loc, max_val)

            return bottom_right
        else:
            return None

    def _find_by_orb(self, screen_shot, icon_shot):
        screen_gray = self._load_and_convert(screen_shot)
        icon_gray = self._load_and_convert(icon_shot)

        kp1, des1 = self.orb.detectAndCompute(icon_gray, None)
        kp2, des2 = self.orb.detectAndCompute(screen_gray, None)

        if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
            return None

        matches = self.matcher.knnMatch(des1, des2, k=2)

        good_matches = []
        for m, n in matches:
            if m.distance < self.match_ratio * n.distance:
                good_matches.append(m)

        if len(good_matches) < self.min_matches:
            return None

        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(
            -1, 1, 2
        )
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(
            -1, 1, 2
        )

        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if H is None:
            return None

        h, w = icon_gray.shape
        icon_corners = np.float32(
            [[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]
        ).reshape(-1, 1, 2)

        screen_corners = cv2.perspectiveTransform(icon_corners, H)

        x_coords = screen_corners[:, 0, 0]
        y_coords = screen_corners[:, 0, 1]
        x1, y1 = int(np.min(x_coords)), int(np.min(y_coords))
        x2, y2 = int(np.max(x_coords)), int(np.max(y_coords))

        # 返回右下角坐标（与模板匹配方法保持一致）
        bottom_right_corner = (x2, y2)

        self._visualize_matches(
            icon_gray, kp1, screen_gray, kp2, good_matches, screen_corners
        )

        return bottom_right_corner

    def _load_and_convert(self, image_input):
        """将多种格式的输入转换为灰度 numpy 数组"""
        if isinstance(image_input, str):
            # 使用 cv2.imdecode 处理中文路径
            img_array = np.fromfile(image_input, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise FileNotFoundError(f"无法读取图片：{image_input}")
        elif isinstance(image_input, Image.Image):
            img = cv2.cvtColor(np.array(image_input), cv2.COLOR_RGB2GRAY)
        elif isinstance(image_input, np.ndarray):
            if len(image_input.shape) == 3:
                img = cv2.cvtColor(image_input, cv2.COLOR_BGR2GRAY)
            else:
                img = image_input
        else:
            raise TypeError("不支持的图片输入格式")
        return img

    def _visualize_template(self, screen_gray, icon_gray, top_left, match_val):
        screen_bgr = cv2.cvtColor(screen_gray, cv2.COLOR_GRAY2BGR)
        h, w = icon_gray.shape
        bottom_right = (int(top_left[0] + w), int(top_left[1] + h))
        center = (int(top_left[0] + w / 2), int(top_left[1] + h / 2))

        cv2.rectangle(screen_bgr, top_left, bottom_right, (0, 255, 0), 2)
        cv2.circle(screen_bgr, center, 10, (0, 0, 255), -1)

        from PIL import Image

        vis_img = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2RGB)

        icon_bgr = cv2.cvtColor(icon_gray, cv2.COLOR_GRAY2BGR)
        icon_small = cv2.resize(icon_bgr, (0, 0), fx=3, fy=3)
        icon_rgb = cv2.cvtColor(icon_small, cv2.COLOR_BGR2RGB)

        vis_img[: icon_small.shape[0], : icon_small.shape[1]] = icon_rgb

        # Image.fromarray(vis_img).show(title="模板匹配结果")

    def _visualize_matches(
        self, img1, kp1, img2, kp2, good_matches, screen_corners=None
    ):
        match_img = cv2.drawMatches(
            img1, kp1, img2, kp2, good_matches[:50], None, flags=2
        )

        if screen_corners is not None:
            dst_img = cv2.cvtColor(img2, cv2.COLOR_GRAY2BGR)
            corners_int = np.int32(screen_corners)
            cv2.polylines(
                dst_img, [corners_int], isClosed=True, color=(0, 255, 0), thickness=3
            )
            br_corner = tuple(corners_int[2][0])
            cv2.circle(dst_img, br_corner, 10, (0, 0, 255), -1)
            vis_img = np.hstack((match_img, cv2.cvtColor(dst_img, cv2.COLOR_BGR2RGB)))
        else:
            vis_img = match_img

        from PIL import Image

        Image.fromarray(vis_img).show(title="特征匹配与定位结果")


def find_icon(
    icon_name,
    threshold=0.8,
    method="template",
    match_ratio=0.75,
    min_matches=10,
    max_retries=30,  # 最大重试次数（30次 × 2秒 = 1分钟，给软件足够启动时间）
    retry_interval=2.0,  # 重试间隔（秒）
) -> dict:
    """在屏幕中查找指定图标的位置并返回其右下角坐标

    支持两种定位方法：
    - template: 模板匹配（适合完全相同的图标）
    - orb: 特征点匹配（适合有旋转、缩放的图标）

    Args:
        icon_name: 图标截图文件名（在 icon_shot 目录中）
        threshold: 模板匹配置信度阈值（0-1），默认 0.8。值越高越严格，1.0 表示完全匹配
        method: 定位方法，'template'（模板匹配）或 'orb'（特征点匹配）
        match_ratio: 特征点匹配的筛选比例（仅 ORB 方法使用），默认 0.75。值越低筛选越严格
        min_matches: 成功定位所需的最少匹配点对数量（仅 ORB 方法使用），默认 10
        max_retries: 最大重试次数，默认 30 次（30×2秒=1分钟）
        retry_interval: 重试间隔（秒），默认 2 秒

    Returns:
        dict: {
            "success": bool,  # 是否成功
            "found": bool,    # 是否找到图标
            "coords": list,   # 坐标 [x, y]（仅当 found=True 时存在）
            "error": str,     # 错误信息（仅当 success=False 时存在）
            "retries": int,   # 实际重试次数
            "message": str    # 详细描述
        }

    Examples:
        # 不重试，直接查找
        result = find_icon(icon_name="wechat_icon.png", threshold=0.8)

        # 重试 6 次，每次间隔 5 秒（适合等待图标出现）
        result = find_icon(
            icon_name="download_button.png",
            max_retries=6,
            retry_interval=5.0
        )
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
        from pathlib import Path

        # 🔴 修改：构建图标路径 - 基于 staff/skills/ 目录
        skills_root = Path(_skills_root)

        # 尝试两种路径构建方式
        # 方式 1：直接使用 icon_name（如果已经是完整相对路径）
        full_icon_path = skills_root / icon_name
        # 方式 1.5：兼容旧格式（icon_name 已包含完整相对路径）
        if not full_icon_path.exists():
            # 尝试从当前工作目录解析
            cwd_path = Path.cwd() / icon_name
            if cwd_path.exists():
                full_icon_path = cwd_path

        # 检查文件是否存在
        if not full_icon_path.exists():
            # 方式 2：如果 icon_name 不包含路径分隔符，尝试从技能目录查找
            if not any(sep in icon_name for sep in ["/", "\\"]):
                # 遍历所有技能目录查找图标
                for skill_dir in skills_root.iterdir():
                    if skill_dir.is_dir():
                        test_path = skill_dir / "icon_shot" / icon_name
                        if test_path.exists():
                            full_icon_path = test_path
                            break

        # 最终检查
        if not full_icon_path.exists():
            available_paths = []
            for p in skills_root.rglob("*.png"):
                available_paths.append(str(p.relative_to(skills_root)))

            return {
                "success": False,
                "found": False,
                "error": f"图标文件不存在：{icon_name}\n搜索路径：{full_icon_path}\n可用的图标路径：{', '.join(available_paths[:10])}",
                "retries": 0,
                "message": "图标文件不存在",
            }

        # 截取当前屏幕
        screen_img = pyautogui.screenshot()

        # 创建定位器实例
        locator = IconLocator(
            method=method, match_ratio=match_ratio, min_matches=min_matches
        )

        # 🔴 新增：重试循环
        for attempt in range(1, max_retries + 1):
            # 查找图标（传递字符串路径）
            target_coord = locator.find_icon(
                screen_img, str(full_icon_path), threshold=threshold
            )

            if target_coord:
                x2, y2 = target_coord

                # 成功了！
                return {
                    "success": True,
                    "found": True,
                    "coords": [x2, y2],
                    "retries": attempt,
                    "message": f"在第 {attempt} 次尝试时找到图标",
                }

            # 没找到，判断是否需要重试
            if attempt < max_retries:
                # 等待一段时间后再次尝试
                time.sleep(retry_interval)

                # 重新截屏（屏幕可能已经变化）
                screen_img = pyautogui.screenshot()

                # 打印调试信息（只在前几次和接近上限时打印，避免日志过多让agent误判失败）
                if attempt <= 2 or attempt >= max_retries - 1 or attempt % 5 == 0:
                    print(
                        f"⏳ 第 {attempt}/{max_retries} 次查找未找到图标，等待 {retry_interval}秒后重试..."
                    )

        # 🔴 所有尝试都失败了
        return {
            "success": True,  # 工具执行成功，但没找到
            "found": False,
            "error": f"未找到图标 {icon_name}（路径：{full_icon_path}）",
            "retries": max_retries,
            "message": f"已尝试 {max_retries} 次，每次间隔 {retry_interval}秒，仍未找到图标",
        }

    except Exception as e:
        return {
            "success": False,
            "found": False,
            "error": f"查找失败：{str(e)}",
            "retries": 0,
            "message": f"异常：{str(e)}",
        }


if __name__ == "__main__":
    # 测试示例
    time.sleep(2)
    result = find_icon(
        icon_name="skill-sap-employee-roster-download/icon_shot/1SAP.png",
        threshold=0.8,
        method="template",
    )

    print(f"查找结果：{result}")

    # 根据返回值判断结果
    if result["success"] and result["found"]:
        print(f"图标位置：{result['coords']}")
    else:
        print(f"查找失败：{result.get('error', '未知错误')}")
