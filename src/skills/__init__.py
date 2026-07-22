"""
技能系统（Skill System）—— 基于 SKILL.md 标准的角色能力封装

每个技能是一个目录，包含：
- SKILL.md: 技能说明文件（YAML frontmatter + Markdown正文）
- execute.py: 可选的执行脚本

SKILL.md 格式：
```yaml
---
name: skill_name
display_name: 显示名称
description: 技能描述
target_roles:
  - 角色1
  - 角色2
input_schema:
  param1:
    type: string
    required: true
    description: 参数说明
---
# 技能说明（Markdown正文）
```

技能发现机制：
- 扫描 src/skills/ 目录下的子目录
- 每个子目录必须包含 SKILL.md
- 如果有 execute.py，则该技能可自动执行
"""

import os
import re
import importlib
from pathlib import Path

# 技能注册表: {skill_name: {meta, module, skill_dir}}
SKILL_REGISTRY = {}


def _parse_frontmatter(content: str) -> tuple:
    """
    解析 SKILL.md 的 YAML frontmatter。
    返回 (meta_dict, markdown_body)
    """
    # 匹配 --- 开头和结尾之间的内容
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not fm_match:
        return {}, content

    fm_text = fm_match.group(1)
    body = content[fm_match.end() :]

    # 简易YAML解析（不依赖外部库）
    meta = _simple_yaml_parse(fm_text)
    return meta, body


def _simple_yaml_parse(text: str) -> dict:
    """
    简易YAML解析器，处理SKILL.md frontmatter中常见的格式。
    支持：键值对、列表、多行字符串（>和|）
    """
    result = {}
    current_key = None
    current_list = None
    multiline_buf = None
    multiline_key = None
    indent_level = 0

    for line in text.split("\n"):
        # 跳过空行（除非在多行字符串中）
        if not line.strip():
            if multiline_buf is not None:
                multiline_buf += "\n"
            continue

        # 检测缩进
        stripped = line.lstrip()
        current_indent = len(line) - len(stripped)

        # 多行字符串续行
        if multiline_buf is not None:
            if current_indent > indent_level:
                multiline_buf += stripped + "\n"
                continue
            else:
                # 多行字符串结束
                result[multiline_key] = multiline_buf.strip()
                multiline_buf = None
                multiline_key = None

        # 列表项
        if stripped.startswith("- "):
            if current_key and current_list is not None:
                current_list.append(stripped[2:].strip().strip('"').strip("'"))
            continue

        # 键值对
        kv_match = re.match(r"^(\w[\w_]*)\s*:\s*(.*)", stripped)
        if kv_match:
            key = kv_match.group(1)
            value = kv_match.group(2).strip()

            # 保存之前的列表
            if current_list is not None:
                result[current_key] = current_list
                current_list = None

            current_key = key

            # 多行字符串标记
            if value in (">", "|"):
                multiline_buf = ""
                multiline_key = key
                indent_level = current_indent
                continue

            # 空值 → 可能后面跟着列表或子内容
            if not value:
                current_list = []
                continue

            # 普通值
            value = value.strip('"').strip("'")
            # 布尔值
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            # 数字
            elif value.isdigit():
                value = int(value)

            result[key] = value

    # 处理最后的列表或多行字符串
    if multiline_buf is not None:
        result[multiline_key] = multiline_buf.strip()
    elif current_list is not None and current_key:
        result[current_key] = current_list

    return result


def register_skill(name, meta, module, skill_dir):
    """注册一个技能"""
    SKILL_REGISTRY[name] = {
        "meta": meta,
        "module": module,
        "skill_dir": skill_dir,
    }


def get_skill(name):
    """获取已注册的技能"""
    return SKILL_REGISTRY.get(name)


def get_skills_for_role(role_name):
    """获取某个角色可用的所有技能"""
    result = []
    for name, skill in SKILL_REGISTRY.items():
        target_roles = skill["meta"].get("target_roles", [])
        if role_name in target_roles:
            result.append({"name": name, **skill["meta"]})
    return result


def get_all_skills_summary():
    """获取所有技能的摘要（供大脑引用）"""
    lines = []
    for name, skill in SKILL_REGISTRY.items():
        meta = skill["meta"]
        desc = meta.get("description", "")
        if isinstance(desc, str):
            desc = desc.replace("\n", " ").strip()
        roles = meta.get("target_roles", [])
        has_executor = "可自动执行" if skill.get("module") else "需人工处理"
        lines.append(f"- {name}: {desc} [角色: {', '.join(roles)}] [{has_executor}]")
    return "\n".join(lines)


def auto_discover_skills():
    """
    自动发现并注册 src/skills/ 目录下的所有技能。
    每个子目录必须包含 SKILL.md 文件。
    如果有 execute.py，则加载为可执行模块。
    """
    skills_dir = Path(__file__).parent

    for item in skills_dir.iterdir():
        if not item.is_dir() or item.name.startswith("_"):
            continue

        skill_md = item / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            # 读取并解析 SKILL.md
            content = skill_md.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(content)

            if not meta.get("name"):
                print(f"[技能系统] 跳过 {item.name}: SKILL.md 缺少 name 字段")
                continue

            # 将Markdown正文也保存到meta中
            meta["_body"] = body
            meta["_skill_dir"] = str(item)

            # 尝试加载 execute.py
            module = None
            execute_py = item / "execute.py"
            if execute_py.exists():
                try:
                    module_name = f"src.skills.{item.name}.execute"
                    module = importlib.import_module(module_name)
                    if not hasattr(module, "execute"):
                        print(
                            f"[技能系统] 警告: {item.name}/execute.py 缺少 execute() 函数"
                        )
                        module = None
                except Exception as e:
                    print(f"[技能系统] 加载 {item.name}/execute.py 失败: {e}")
                    module = None

            skill_name = meta["name"]
            register_skill(skill_name, meta, module, str(item))

            exec_status = "✅ 可自动执行" if module else "⚠️ 仅说明文档"
            print(
                f"[技能系统] 已注册技能: {skill_name} ({meta.get('display_name', '')}) [{exec_status}]"
            )

        except Exception as e:
            print(f"[技能系统] 加载技能 {item.name} 失败: {e}")


# 启动时自动发现
auto_discover_skills()
