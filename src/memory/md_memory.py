"""
第三层记忆：MD记忆（长期/核心记忆）
存储在/memories/AGENTS.md中，2000字以内，每天凌晨2:30从Database提炼更新。
每轮对话自动注入到agent的memory参数中。
"""
from pathlib import Path
from src.config.settings import MEMORY_DIR


MEMORY_FILE = MEMORY_DIR / "AGENTS.md"

DEFAULT_CONTENT = """# SSC大脑长期记忆
# 最后更新：尚未初始化

## 组织结构与关键人员
[待填充]

## 当前进行中的重要事项
[待填充]

## 近期决策记录与经验
[待填充]

## 发现的模式与趋势
[待填充]

## 组织偏好与规则
[待填充]

## 需要持续关注的事项
[待填充]
"""


def ensure_memory_file() -> Path:
    """确保记忆文件存在，不存在则创建默认内容"""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_FILE.exists():
        MEMORY_FILE.write_text(DEFAULT_CONTENT, encoding="utf-8")
    return MEMORY_FILE


def read_memory() -> str:
    """读取MD记忆内容"""
    ensure_memory_file()
    return MEMORY_FILE.read_text(encoding="utf-8")


def update_memory(content: str):
    """更新MD记忆内容（覆盖写入）"""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(content, encoding="utf-8")