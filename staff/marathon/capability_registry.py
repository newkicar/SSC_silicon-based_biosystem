"""
能力清单（Capability Registry）—— Marathon 能力感知规划的核心

聚合系统所有可用能力，生成结构化的能力清单文本，
供 Planner 在规划前阅读，实现"先盘点能力，再拆解任务"。

能力来源：
1. 客户端 Skills（staff/skills/） — 可执行的本地业务操作
2. 大脑搜索工具（src/brain.py） — 可查询的信息
3. 系统能力（executor 内置） — 工单/通知/分派
4. SSC 团队成员 — 可分派的人力资源
"""

import re
from pathlib import Path


def get_client_skills() -> list[dict]:
    """从 staff/skills/ 目录读取所有客户端 Skill 的详细能力信息。
    自动解析 SKILL.md 的 YAML frontmatter + 正文中的关键信息。
    """
    skills_dir = Path(__file__).resolve().parent.parent / "skills"
    if not skills_dir.exists():
        return []

    skills = []
    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir() or item.name.startswith("_") or item.name.startswith("."):
            continue
        skill_md = item / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            content = skill_md.read_text(encoding="utf-8")
            # 解析 YAML frontmatter（死格式：--- 包裹）
            fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if not fm_match:
                continue
            fm_text = fm_match.group(1)
            meta = {}
            for line in fm_text.split('\n'):
                stripped = line.strip()
                # 支持多行值（description: >- 块）
                if stripped.startswith('description:') or stripped.startswith('title:'):
                    key_match = re.match(r'^(\w[\w_]*)\s*:\s*(.*)', stripped)
                    if key_match:
                        meta[key_match.group(1)] = key_match.group(2).strip().strip('"').strip("'")
                elif stripped.startswith('when_to_use:'):
                    # when_to_use 是多行块，取后续内容
                    continue
                else:
                    kv = re.match(r'^(\w[\w_]*)\s*:\s*(.*)', stripped)
                    if kv:
                        meta[kv.group(1)] = kv.group(2).strip().strip('"').strip("'")

            name = meta.get("name", "")
            if not name:
                continue

            title = meta.get("title", "")
            description = meta.get("description", "")
            # 组合 title + description 作为能力说明
            capability = title if title else description
            if title and description and title not in description:
                capability = f"{title}。{description}"

            # 从正文中提取适用场景（when_to_use 或正文开头的列表）
            use_cases = _extract_use_cases(content)

            skills.append({
                "name": name,
                "capability": capability[:200] if capability else "",
                "use_cases": use_cases,
                "target_roles": _extract_target_roles(fm_text),
            })
        except Exception:
            pass
    return skills


def _extract_use_cases(content: str) -> list[str]:
    """从 SKILL.md 正文中提取适用场景列表"""
    use_cases = []
    # 尝试找 when_to_use 块
    wtu_match = re.search(r'when_to_use\s*:\s*\|\s*\n((?:\s+-\s+.+\n?)+)', content)
    if wtu_match:
        for line in wtu_match.group(1).strip().split('\n'):
            line = line.strip()
            if line.startswith('-'):
                use_cases.append(line.lstrip('- ').strip())
        return use_cases[:5]

    # 备选：找正文中的"当用户"或"当需要"开头的列表
    for match in re.finditer(r'^\s*[-*]\s*(.+当用户.+|.+当需要.+)', content, re.MULTILINE):
        use_cases.append(match.group(1).strip()[:80])
    return use_cases[:5]


def _extract_target_roles(fm_text: str) -> list[str]:
    """从 frontmatter 中提取 target_roles 列表"""
    roles = []
    in_roles = False
    for line in fm_text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('target_roles:'):
            in_roles = True
            continue
        if in_roles:
            if stripped.startswith('- '):
                roles.append(stripped[2:].strip().strip('"').strip("'"))
            elif stripped and not stripped.startswith('#'):
                break
    return roles


def get_brain_tools() -> list[dict]:
    """从 src/brain.py 动态读取大脑工具的能力描述。
    自动提取所有 @tool 装饰器定义的函数的 name 和 docstring，
    新增工具时只需在 brain.py 中定义 @tool 函数，无需修改此文件。
    """
    tools = []
    try:
        from src.brain import search_policy, search_employee_database, query_employee_roster, query_attendance
        # 从 brain.py 导入所有工具函数，提取 name + docstring
        # 新增工具只需在 brain.py 中定义 @tool 函数并加入 create_brain_agent_with_tools()
        tool_funcs = [search_policy, search_employee_database, query_employee_roster, query_attendance]
        # 兼容：如果 brain.py 中新增了工具但还没加入上面的列表，从 create_brain_agent_with_tools 的源码动态发现
        # 简单方案：直接读取 brain.py 中所有 @tool 装饰的函数
        import inspect
        import src.brain as brain_module
        for name, obj in inspect.getmembers(brain_module):
            if hasattr(obj, 'name') and hasattr(obj, 'description') and callable(obj):
                # LangChain @tool 创建的对象有 .name 和 .description 属性
                desc = obj.description or ""
                # 从 docstring 中提取更详细的说明（第一段作为 capability）
                doc = inspect.getdoc(obj) or desc
                capability = doc.split("\n\n")[0].replace("\n", " ").strip()[:120]
                # 从 docstring 中提取"参数"部分作为 use_cases 提示
                tools.append({
                    "name": obj.name,
                    "capability": capability,
                    "limitations": "详情请查看工具定义",
                })
    except Exception:
        # 导入失败时返回空列表（能力清单中会显示"暂无大脑搜索工具"）
        pass
    return tools


def get_system_capabilities() -> list[dict]:
    """返回系统内置能力（executor 层面的能力）"""
    return [
        {
            "name": "create_ticket",
            "capability": "创建工单并分派给指定SSC成员",
            "use_cases": [
                "需要将任务正式记录并跟踪",
                "需要分派任务给特定同事",
                "涉及审批、申请等需要工单流转的场景",
            ],
        },
        {
            "name": "create_notification",
            "capability": "发送系统通知给指定用户或全部SSC成员",
            "use_cases": [
                "通知相关人员某事项已完成",
                "发送提醒通知",
            ],
        },
        {
            "name": "dispatch_cli_task",
            "capability": "分派CLI任务给SSC成员，可附带skill_name实现自动执行",
            "use_cases": [
                "需要角色终端自动执行某个Skill",
                "分派任务并让对方的AI自动完成",
            ],
        },
    ]


def get_ssc_team() -> list[dict]:
    """从数据库读取SSC团队成员信息"""
    try:
        from src.security.auth import get_all_ssc_specializations
        users = get_all_ssc_specializations()
    except Exception:
        return []

    team = []
    for user in users:
        name = user.get("display_name", "")
        role = user.get("role", "")
        spec = user.get("specialization", "")
        if spec:
            spec = spec.replace("处理上级或大脑发来的", "").replace("处理上级或大脑发来", "")
        team.append({
            "name": name,
            "role": role,
            "specialization": spec[:100] if spec else "",
        })
    return team


def build_capability_prompt() -> str:
    """构建完整的能力清单文本，注入到 Planner 的 prompt 中。
    
    这是核心方法——将所有能力聚合为一份结构化文档，
    让 Planner LLM 在规划前能"看到"自己的完整能力边界。
    """
    lines = [
        "# 你的完整能力清单",
        "",
        "在规划任务之前，请先了解你能做什么、不能做什么。",
        "**每个规划步骤必须使用下方列出的具体能力，不能规划超出能力范围的步骤。**",
        "",
    ]

    # ── 1. 客户端 Skills ──
    client_skills = get_client_skills()
    if client_skills:
        lines.extend([
            "## 🔧 可执行的自动化操作（通过 execute_skill 工具调用）",
            "",
            "这些是系统已注册的客户端 Skill，可以执行具体的本地业务操作。",
            "当任务涉及下方操作时，应规划为 `skill_execution` 类型的步骤。",
            "",
            "| Skill 名称 | 能力说明 | 适用场景 | 限制角色 |",
            "|------------|---------|---------|---------|",
        ])
        for s in client_skills:
            use_cases_text = "、".join(s["use_cases"][:3]) if s["use_cases"] else "通用"
            roles_text = "、".join(s["target_roles"][:3]) if s["target_roles"] else "全部"
            capability = s["capability"][:60]
            lines.append(f"| {s['name']} | {capability} | {use_cases_text} | {roles_text} |")
        lines.append("")
    else:
        lines.extend([
            "## 🔧 可执行的自动化操作",
            "",
            "（当前无已注册的客户端 Skill）",
            "",
        ])

    # ── 2. 大脑搜索工具 ──
    brain_tools = get_brain_tools()
    lines.extend([
        "## 🔍 可查询的信息（通过大脑搜索工具）",
        "",
        "这些是大脑内置的数据查询工具，在步骤执行时可直接调用。",
        "当任务涉及查询数据、查找制度时，应规划为 `query_data` 类型的步骤。",
        "",
        "| 工具名 | 能查什么 | 适用场景 | 限制 |",
        "|--------|---------|---------|------|",
    ])
    for t in brain_tools:
        use_cases_text = "、".join(t.get("use_cases", [])[:2]) if t.get("use_cases") else t.get("capability", "")[:30]
        lines.append(f"| {t['name']} | {t['capability']} | {use_cases_text} | {t.get('limitations', '-')} |")
    lines.append("")

    # ── 3. 系统能力 ──
    sys_caps = get_system_capabilities()
    lines.extend([
        "## 📋 系统内置能力（通过 dispatch_actions 格式C 调用）",
        "",
        "这些是系统级的执行能力，通过输出 JSON 指令触发。",
        "",
        "| 能力 | 说明 | 适用场景 |",
        "|------|------|---------|",
    ])
    for c in sys_caps:
        use_cases_text = "、".join(c["use_cases"][:2])
        lines.append(f"| {c['name']} | {c['capability']} | {use_cases_text} |")
    lines.append("")

    # ── 4. SSC 团队 ──
    team = get_ssc_team()
    if team:
        lines.extend([
            "## 👥 可分派的 SSC 团队成员",
            "",
            "创建工单时必须从以下人员中选择最匹配的处理人。",
            "",
            "| 姓名 | 角色 | 职责范围 |",
            "|------|------|---------|",
        ])
        for m in team:
            spec_text = m["specialization"][:40] if m["specialization"] else "-"
            lines.append(f"| {m['name']} | {m['role']} | {spec_text} |")
        lines.append("")

    # ── 5. 能力边界（最重要） ──
    lines.extend([
        "## ⚠️ 能力边界（不能做什么）",
        "",
        "| 不能做的事 | 原因 | 替代方案 |",
        "|-----------|------|---------|",
        "| 直接操作 SAP 系统（录入社保、薪资核算等） | 无 SAP 写入权限 | 创建工单分派给薪酬专员 |",
        "| 直接修改数据库记录 | 大脑无数据库写入权限 | 通过系统 API 或工单流程 |",
        "| 发送外部邮件（非 Outlook） | 只有 Outlook 自动化 Skill | 使用 skill-outlook-controller |",
        "| 直接进行人员招聘（面试、录用） | 需要人类判断 | 创建工单分派给招聘主管 |",
        "| 处理敏感事件（仲裁/举报） | 需要人类专业判断 | 立即创建 urgent 工单转交员工关系主管 |",
        "",
        "**规划铁律：每个步骤必须能对应到上方某个具体能力。如果找不到对应能力，该步骤应标记为 `requires_human` 或改为创建工单分派。**",
    ])

    return "\n".join(lines)