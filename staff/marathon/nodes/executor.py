"""
Executor 节点 —— 业务动作执行

调用SSC大脑执行当前子步骤的业务动作。
大脑统一拥有 RAG 搜索工具 + execute_skill 执行工具，
像 Claude Code 一样在搜索和执行之间无缝切换。
"""

import json
import re
import sys
import os
import io
import warnings
from datetime import datetime
from pathlib import Path

# ==================== 用户角色映射（从 users.json 加载） ====================
_user_role_cache = None


def _load_user_role_map():
    """从数据库加载 SSC 用户的角色→人员映射（懒加载，缓存）"""
    global _user_role_cache
    if _user_role_cache is not None:
        return _user_role_cache

    _user_role_cache = {}
    try:
        from src.security.auth import get_all_ssc_specializations

        users = get_all_ssc_specializations()
        for user in users:
            role = user.get("role", "")
            if role:
                _user_role_cache[role] = {
                    "username": user.get("username", ""),
                    "display_name": user.get("display_name", ""),
                    "role": role,
                    "specialization": user.get("specialization", ""),
                }
    except Exception:
        pass

    return _user_role_cache


def _find_user_by_role(target_role: str, assignee_name: str = "") -> dict | None:
    """根据角色名查找对应用户。支持 assignee_name 精确匹配和模糊匹配。
    优先匹配 assignee_name（大脑指定的具体人），其次匹配 target_role。
    """
    role_map = _load_user_role_map()

    # 如果指定了 assignee_name，优先按姓名查找
    if assignee_name:
        for role_name, user_info in role_map.items():
            if user_info.get("display_name", "") == assignee_name:
                return user_info

    # 精确匹配角色
    if target_role in role_map:
        return role_map[target_role]

    # 模糊匹配：target_role 包含在 role 中，或 role 包含在 target_role 中
    target_lower = target_role.lower().replace("_", "")
    for role_name, user_info in role_map.items():
        role_lower = role_name.lower().replace("_", "")
        if target_lower in role_lower or role_lower in target_lower:
            return user_info
    return None


def _get_ssc_team_context() -> str:
    """从数据库读取 SSC 团队成员信息（角色+职责），注入到大脑 prompt 让它精确分派。"""
    try:
        from src.security.auth import get_all_ssc_specializations

        users = get_all_ssc_specializations()
    except Exception:
        return ""

    if not users:
        return ""

    lines = []
    for user in users:
        name = user.get("display_name", "")
        role = user.get("role", "")
        spec = user.get("specialization", "")
        if spec:
            spec = spec.replace("处理上级或大脑发来的", "").replace(
                "处理上级或大脑发来", ""
            )
            if len(spec) > 80:
                spec = spec[:80] + "..."
        line = f"- {name} ({role})"
        if spec:
            line += f": {spec}"
        lines.append(line)

    return "[SSC团队成员]\n创建工单时必须指定 assignee_name（从下方人员中选择最匹配的人）：\n" + "\n".join(
        lines
    )


# ==================== execute_skill 工具 ====================
# 这是一个 LangChain @tool，大脑在 agent loop 中可以像调用 search_policy 一样调用它。
# 内部在员工终端本地创建 deepagents agent 执行 Skill，结果自动返回给大脑。

_execute_skill_cache = {"agent": None}


def _get_execute_skill_agent():
    """懒加载 deepagents agent（复用实例，避免每次调用都重新创建）"""
    if _execute_skill_cache["agent"] is not None:
        return _execute_skill_cache["agent"]

    # 注册 HarnessProfile：排除文件系统工具，防止 LLM 尝试读 SKILL.md 失败
    from deepagents.profiles import HarnessProfile, register_harness_profile

    register_harness_profile(
        "openai:[大模型名称]",
        HarnessProfile(
            excluded_tools=frozenset(
                {"ls", "read_file", "write_file", "edit_file", "glob", "grep"}
            ),
        ),
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from deepagents import create_deep_agent
        from deepagents.backends import LocalShellBackend
    from staff.llm import get_llm

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    backend = LocalShellBackend(root_dir=".", virtual_mode=True, env=env)

    staff_dir = Path(__file__).resolve().parent.parent.parent
    skills_dir = staff_dir / "skills"
    skills_rel = os.path.relpath(str(skills_dir), os.getcwd()).replace("\\", "/") + "/"

    from staff.tools import get_tools

    custom_tools = get_tools()

    agent = create_deep_agent(
        model=get_llm(),
        backend=backend,
        skills=[skills_rel],
        tools=custom_tools,
        system_prompt="""你是HR SSC执行代理。根据用户需求，使用你的工具和Skill能力完成任务。

重要规则：
- 你的 Skill 能力已自动加载，当任务匹配某个 Skill 时，deepagents 会自动读取 SKILL.md 并注入上下文。
- 不要手动读取任何文件——你的文件系统工具已被禁用。
- 直接根据任务描述和自动加载的 Skill 指令执行操作。
- 简洁直接，执行完成后简要说明结果。

你的能力范围：本地业务操作（发邮件、预约会议室、下载文件、GUI自动化等）。
不要创建工单、不要创建通知、不要分派任务——这些由其他系统处理。""",
    )
    _execute_skill_cache["agent"] = agent
    return agent


def _load_skill_content_for_task(task_description: str) -> tuple[str, str]:
    """根据任务描述匹配最可能的 Skill，读取其 SKILL.md 核心指令。
    返回 (skill_name, skill_content)。匹配不到时返回 ("", "")。
    """
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    if not skills_dir.exists():
        return "", ""

    task_lower = task_description.lower()
    best_name = ""
    best_content = ""
    best_score = 0

    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir() or item.name.startswith("_") or item.name.startswith("."):
            continue
        skill_md = item / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            content = skill_md.read_text(encoding="utf-8")
            # 评分：任务描述中的关键词在 SKILL.md 中出现的次数
            score = 0
            name = item.name
            # Skill 名称匹配（完全匹配或去掉前缀匹配）
            if (
                name.lower() in task_lower
                or name.replace("skill-", "").replace("-", " ") in task_lower
            ):
                score += 10
            # description 中的关键词匹配
            import re

            fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
            if fm_match:
                desc = fm_match.group(1).lower()
                # 中文关键词匹配：提取2-4字的中文词片段进行子串匹配
                chinese_chars = re.findall(r"[\u4e00-\u9fff]+", task_description)
                for segment in chinese_chars:
                    if len(segment) >= 2:
                        # 对长词拆分为2字子串（如"发一封邮件"→"发一","一封","封邮","邮件"）
                        for i in range(len(segment) - 1):
                            sub2 = segment[i : i + 2]
                            if sub2 in desc:
                                score += 3
                                break  # 每个segment只算一次
                # 整段中文在 SKILL.md 正文中匹配（更宽松）
                for segment in chinese_chars:
                    if len(segment) >= 2 and segment in content.lower():
                        score += 1
                # 英文关键词匹配
                for word in task_lower.split():
                    if len(word) > 2 and word in desc:
                        score += 2

            if score > best_score:
                best_score = score
                best_name = name
                # 取 SKILL.md 正文（去掉 frontmatter），截取前3000字符
                body_start = content.find("---", content.find("---") + 3) + 3
                best_content = content[body_start:].strip()[:3000]
        except Exception:
            pass

    if best_score > 0:
        return best_name, best_content
    return "", ""


def _ensure_str(content) -> str:
    """将 message.content（可能为 str 或 list[content_block]）统一转为 str。
    deepagents agent loop 中，LLM 返回的 content 可能是 list 格式：
    [{"type": "text", "text": "..."}, {"type": "tool_use", ...}]
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content) if content else ""


# ==================== execute_skill 幂等性缓存 ====================
# RubricMiddleware 重试时会重新执行整个 brain agent loop，导致 execute_skill 被重复调用。
# 对于有副作用的操作（发邮件、预约会议室等），重复执行会造成重复发送。
# 解决方案：用 dict 缓存最近的执行结果，以 (task_description, execution_context_id) 为 key，
# 确保不同步骤/不同 attempt 之间互不干扰。设置 LRU 上限防止长期运行内存泄漏。
from collections import OrderedDict

_skill_exec_cache = OrderedDict()  # OrderedDict 实现 LRU
_SKILL_CACHE_MAX_SIZE = 64  # 最多缓存64条，超出时淘汰最旧的

# 全局执行上下文 ID，由 _call_brain_direct 在执行前设置，_execute_skill_impl 读取
# 这样 tool 被 RubricMiddleware 重试调用时，相同上下文 ID 能命中缓存
_current_execution_id = None

# Rubric 已通过的 exec_id 集合
# 当 RubricMiddleware 评估结果为 satisfied 时，记录该 exec_id。
# 后续同一 exec_id 内的 execute_skill 调用将被跳过（返回缓存结果），
# 避免 Rubric 重试已通过后再次执行有副作用的操作（如重复发邮件）。
# Rubric 未通过时，exec_id 不在集合中，execute_skill 允许重新执行。
_rubric_passed_exec_ids = set()


def set_execution_context_id(exec_id: str):
    """设置当前执行上下文 ID（由 _call_brain_direct 调用前设置）。
    用于 execute_skill 的幂等性缓存隔离——同一 agent loop 内的重试共享缓存，
    不同步骤/不同 attempt 的调用互不干扰。
    """
    global _current_execution_id
    _current_execution_id = exec_id
    # 新 exec_id 开始，清除旧 exec_id 的 Rubric 通过标记
    # 这样不同 step/attempt 之间互不干扰
    _rubric_passed_exec_ids.clear()
    print(f"[execute_skill-DEBUG] set_execution_context_id = {exec_id}")


def _execute_skill_impl(task_description: str, context: str = "") -> str:
    """execute_skill 工具的实际实现（被 @tool 包装）。
    内置幂等性保护：RubricMiddleware 重试时，相同任务+相同执行上下文在本次 agent loop 内直接返回缓存结果。
    不同执行上下文（不同 step/attempt）的相同任务描述互不干扰。
    """
    import hashlib
    import time
    from langchain_core.messages import HumanMessage
    import uuid

    # 幂等性检查：key = (execution_context_id, task_description)
    # execution_context_id 由外部 _call_brain_direct 设置，隔离不同 step/attempt
    exec_id = _current_execution_id or "unknown"
    cache_key = hashlib.md5(f"{exec_id}||{task_description}".encode()).hexdigest()
    now = time.time()

    # === DEBUG: 记录每次 execute_skill 调用 ===
    cache_hit = cache_key in _skill_exec_cache
    cache_age = (
        f"{now - _skill_exec_cache[cache_key][1]:.1f}s"
        if cache_hit and now - _skill_exec_cache[cache_key][1] < 60
        else "expired" if cache_hit else "N/A"
    )
    print(
        f"[execute_skill-DEBUG] call | key={cache_key[:12]} | exec_id={exec_id[:30]} | cached={cache_hit} | age={cache_age} | task={task_description[:80]}"
    )

    if cache_hit:
        cached_result, cached_time = _skill_exec_cache[cache_key]
        # 同一 agent loop 内（RubricMiddleware 重试）约 60 秒内有效
        if now - cached_time < 60:
            print(f"[execute_skill-DEBUG] CACHE HIT (age={cache_age}) → 返回缓存结果")
            return cached_result

    # v2 Rubric 感知去重：仅当 RubricMiddleware 已评估通过（result=satisfied）时，
    # 后续同一 exec_id 内的 execute_skill 调用才跳过。
    # Rubric 未通过时，exec_id 不在 _rubric_passed_exec_ids 中，execute_skill 允许重新执行，
    # 以便 brain agent loop 重试时修正它的回答。
    # 这样既避免了 Rubric 已通过后重复执行有副作用的操作（如重复发邮件），
    # 又保留了 Rubric 未通过时重试的执行能力。
    if exec_id in _rubric_passed_exec_ids:
        print(
            f"[execute_skill-DEBUG] RUBRIC PASSED → exec_id={exec_id[:30]}, 跳过本次执行，返回上次结果"
        )
        # Rubric 已通过，直接返回已完成的标记。
        # 不需要从缓存找结果——如果缓存命中且有效，60s 窗口已在 line 319-324 提前返回；
        # 如果缓存过期，返回简短标记即可，不影响语义。
        return "操作已在之前执行完成（Rubric 已通过），无需重复执行。"

    agent = _get_execute_skill_agent()

    # 预加载匹配的 Skill 指令，注入到任务中
    # 这样 LLM 不需要手动读取 SKILL.md——指令已经在上下文中
    skill_name, skill_content = _load_skill_content_for_task(task_description)
    skill_hint = ""
    if skill_name and skill_content:
        skill_hint = (
            f"\n\n[{skill_name} 操作指南]\n{skill_content}\n[/{skill_name} 操作指南]"
        )

    user_msg = task_description + skill_hint
    if context:
        user_msg = f"{task_description}{skill_hint}\n\n上下文：{context}"

    thread_id = f"marathon-skill-{uuid.uuid4().hex[:8]}"

    # 抑制 deepagents 子进程的 stderr 编码错误
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        result = agent.invoke(
            {"messages": [HumanMessage(content=user_msg)]},
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as e:
        return f"Skill执行异常: {str(e)[:300]}"
    finally:
        sys.stderr = old_stderr

    raw_response = ""
    if hasattr(result, "messages") and result.messages:
        raw_response = _ensure_str(result.messages[-1].content)
    elif isinstance(result, dict) and "messages" in result:
        raw_response = _ensure_str(result["messages"][-1].content)

    if raw_response:
        raw_response = _clean_response_markers(raw_response)

    final_result = raw_response or "Skill执行完成（无返回内容）"

    # 缓存执行结果（供 RubricMiddleware 重试时使用，同一 agent loop 内有效）
    _skill_exec_cache[cache_key] = (final_result, now)
    # LRU 淘汰：超出上限时移除最旧的条目
    while len(_skill_exec_cache) > _SKILL_CACHE_MAX_SIZE:
        _skill_exec_cache.popitem(last=False)

    return final_result


def create_execute_skill_tool():
    """创建 execute_skill 工具实例（LangChain @tool）"""
    from langchain_core.tools import tool

    @tool
    def execute_skill(task_description: str) -> str:
        """执行具体的业务操作任务（发邮件、预约会议室、下载文件、请假申请、工作总结等）。
        内部会自动匹配并执行合适的Skill（如 skill-outlook-controller、skill-book-meeting-room 等）。
        当你需要"做某件事"（而不是"查某条信息"）时使用此工具。
        参数 task_description: 任务的自然语言描述，如"给li.shun@example.com发一封邮件，主题是SAP花名册"
        """
        return _execute_skill_impl(task_description)

    return execute_skill


# ==================== 事件回调（供 terminal 设置实时展示） ====================
# terminal.py 可设置此回调来接收 brain agent 的实时事件（tool calls 等）
_brain_event_callback = None


def set_brain_event_callback(callback):
    """设置大脑执行的实时事件回调。
    callback(event_type, event_data) 其中 event_type: 'tool_start'/'tool_end'/'llm_token'
    """
    global _brain_event_callback
    _brain_event_callback = callback


# ==================== Marathon 执行节点 ====================


def executor_node(state):
    """LangGraph 节点：执行当前子步骤"""
    from staff.marathon.config import STEP_EXECUTING, STEP_DONE, STEP_FAILED

    step = state.get_current_step()
    if step is None:
        return {
            "current_validation": {
                "passed": False,
                "level": "executor",
                "error": "没有可执行的步骤",
                "details": "",
            }
        }

    step.status = STEP_EXECUTING
    step.attempts += 1
    step.started_at = datetime.now().isoformat()

    # DEBUG: 记录节点执行
    print(
        f"[executor-DEBUG] step={step.id} attempts={step.attempts} capability={step.capability if hasattr(step, 'capability') else step.get('capability', '')}"
    )

    # 清除重试错误上下文，且不重新生成情报包（避免重复RAG累积token）
    is_retry = step.attempts > 1
    if is_retry:
        state.context_summary = ""

    try:
        exec_context = _build_execution_context(state, step, skip_intelligence=is_retry)
        brain_response = _call_brain_direct(exec_context, state)
        result_summary, action_data = _extract_action_result(brain_response, step)

        step.status = STEP_DONE
        step.result_summary = (
            brain_response[:2000] if brain_response else result_summary[:200]
        )
        step.completed_at = datetime.now().isoformat()

        now = datetime.now().isoformat()
        state.execution_log.append(
            f"[{now}] Step {step.id + 1} 执行成功: {result_summary[:80]}"
        )

        return {
            "plan": [s.to_dict() for s in state.plan],
            "current_validation": {
                "passed": True,
                "level": "executor",
                "details": brain_response[:1000] if brain_response else "",
                "error": "",
            },
            "step_error_count": 0,
            "execution_log": state.execution_log,
        }
    except Exception as e:
        error_msg = str(e)[:500]
        step.status = STEP_FAILED
        step.error_log = error_msg
        step.error_history.append(f"[attempt {step.attempts}] {error_msg}")

        now = datetime.now().isoformat()
        state.execution_log.append(
            f"[{now}] Step {step.id + 1} 执行失败: {error_msg[:80]}"
        )

        return {
            "plan": [s.to_dict() for s in state.plan],
            "current_validation": {
                "passed": False,
                "level": "executor",
                "error": error_msg,
                "details": "",
            },
            "step_error_count": state.step_error_count + 1,
            "global_error_count": state.global_error_count + 1,
            "execution_log": state.execution_log,
        }


def _build_execution_context(state, step, skip_intelligence=False):
    """为当前步骤构建执行上下文（含身份信息 + 上行脊髓情报包 + 员工Skills目录）。
    skip_intelligence=True 时跳过RAG检索，避免重试时token累积。"""
    prev_results = []
    for s in state.plan:
        if isinstance(s, dict):
            sid = s.get("id", 0)
            sstatus = s.get("status", "")
            sdesc = s.get("description", "")
            ssummary = s.get("result_summary", "")
        else:
            sid = s.id
            sstatus = s.status
            sdesc = s.description
            ssummary = s.result_summary
        if sid < step.id and sstatus == "done":
            prev_results.append(f"- Step {sid + 1} ({sdesc}): {ssummary}")

    prev_context = ""
    if prev_results:
        prev_context = "\n\n前面步骤的执行结果：\n" + "\n".join(prev_results[-5:])

    step_desc = (
        step.description
        if hasattr(step, "description")
        else step.get("description", "")
    )
    step_criteria = (
        step.acceptance_criteria
        if hasattr(step, "acceptance_criteria")
        else step.get("acceptance_criteria", "")
    )
    step_atype = (
        step.action_type
        if hasattr(step, "action_type")
        else step.get("action_type", "")
    )
    step_capability = (
        step.capability if hasattr(step, "capability") else step.get("capability", "")
    )
    step_id = step.id if hasattr(step, "id") else step.get("id", 0)
    plan_len = len(state.plan)

    # 注入用户身份
    user_context = f"""[用户身份]
工号: {state.username}
姓名: {state.display_name}
当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""

    # 调用上行脊髓做数据预取（传入已知身份，直接查库而非从文本猜）
    # 重试时跳过——情报包已在首次执行时注入，重复注入会累积token
    intelligence_context = ""
    if not skip_intelligence:
        try:
            from src.spine.ascending import process_employee_inquiry

            packet = process_employee_inquiry(
                state.task_description,
                requester_id=state.username,
                requester_name=state.display_name,
            )
            intelligence_context = f"\n\n{packet.to_prompt()}"
        except Exception:
            pass

    # 注入 SSC 团队成员信息（让大脑知道该分派给谁）
    ssc_team = _get_ssc_team_context()

    # 构建能力路由提示——根据 planner 标注的 capability，动态推断该用哪种执行路径
    # 通用规则：不硬编码工具名列表，而是根据 capability 前缀/特征动态判断
    capability_hint = ""
    if step_capability:
        # 动态获取大脑工具列表（避免硬编码）
        _brain_tool_names = set()
        try:
            from staff.marathon.capability_registry import get_brain_tools

            for t in get_brain_tools():
                _brain_tool_names.add(t["name"])
        except Exception:
            pass
        # 系统能力集合
        _system_cap_names = {
            "create_ticket",
            "create_notification",
            "dispatch_cli_task",
        }

        if step_capability.startswith("skill-"):
            capability_hint = f"""
[能力路由] 本步骤规划使用的具体能力：{step_capability}
→ 请调用 execute_skill 工具，task_description 中写明要执行的操作和参数。"""
        elif step_capability in _brain_tool_names:
            capability_hint = f"""
[能力路由] 本步骤规划使用的具体能力：{step_capability}
→ 请直接调用 {step_capability} 工具获取数据。"""
        elif step_capability in _system_cap_names:
            capability_hint = f"""
[能力路由] 本步骤规划使用的具体能力：{step_capability}
→ 请在回复末尾输出格式C的 dispatch_actions JSON 块。"""

    return f"""{user_context}
{intelligence_context}
{ssc_team}

[Marathon 执行指令]

原始任务：{state.task_description}

当前步骤（Step {step_id + 1}/{plan_len}）：{step_desc}
验收标准：{step_criteria}
动作类型：{step_atype}
{capability_hint}
{prev_context}

请执行以上步骤。
- 如果动作类型是 skill_execution 或 capability 以 skill- 开头，必须调用 execute_skill 工具。
- 如果需要查询信息（政策、数据、考勤），直接调用对应的搜索工具。
- 如果需要创建工单、创建通知、分派任务，必须在回复末尾输出格式C的 dispatch_actions JSON 块。
  ⚠️ 重要：纯文本中说"已创建工单"不会被系统识别——必须输出 ```json ... "dispatch_actions" ... ``` 格式。
- 执行完成后，简要说明执行了什么操作和结果。
- ⚠️ 严格步骤边界：只执行当前步骤！不要提前执行后续步骤的操作（如后续步骤才需要发邮件，当前步骤就别发）。后续步骤由系统独立调度执行。
注意：不要通过 execute_skill 创建工单——工单通过 dispatch_actions 格式C 创建。

⚠️ 数据研判原则（重要）：
当任务涉及"异常判定""合规性判断""是否符合标准"等需要解读数据的场景时：
1. **先查政策，再做判断**——必须先用 search_policy 查询相关制度（如考勤制度、审批流程等），了解判定标准后才能下结论
2. **数据要完整**——判断前确保已获取所有相关数据源（如考勤需同时看上班卡和下班卡，不能只看一个）
3. **不凭数据直觉判断**——打卡记录本身不说明"迟到"或"早退"，只有对照制度中的规定上下班时间才能判定"""


def _extract_final_text(result):
    """从 invoke 结果中提取最终文本回复。
    向后遍历消息列表，找到最近的有文本内容的消息。
    """
    messages = []
    if hasattr(result, "messages"):
        messages = result.messages
    elif isinstance(result, dict) and "messages" in result:
        messages = result["messages"]

    if not messages:
        return ""

    # 从最后一条消息开始向前搜索有文本的AI消息
    for msg in reversed(messages):
        content = _ensure_str(getattr(msg, "content", ""))
        if content and content.strip():
            return content

    return ""


def _replay_tool_calls_for_display(result):
    """从 invoke 结果中提取 tool call 信息，通过回调显示在终端。
    invoke 是同步的，执行完后一次性回放所有 tool call 记录。
    """
    if not _brain_event_callback:
        return

    messages = []
    if hasattr(result, "messages"):
        messages = result.messages
    elif isinstance(result, dict) and "messages" in result:
        messages = result["messages"]

    for msg in messages:
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            continue
        for tc in tool_calls:
            # tc 可能是 dict 或 ToolCall 对象
            if isinstance(tc, dict):
                tool_name = tc.get("name", "unknown")
                tool_args = tc.get("args", {})
            else:
                tool_name = getattr(tc, "name", "unknown")
                tool_args = getattr(tc, "args", {})
            input_summary = str(tool_args)[:100]
            _brain_event_callback(
                "tool_start", {"tool": tool_name, "input": input_summary}
            )
            _brain_event_callback(
                "tool_end", {"tool": tool_name, "output": "completed"}
            )


def _call_brain_direct(context, state):
    """
    直接调用大脑agent loop，根据当前步骤的 capability 动态注入工具。
    - query_data 类步骤：只给搜索工具（search_policy / query_employee_roster / query_attendance），
      不给 execute_skill，防止大脑越界提前执行后续步骤的操作（如发邮件）。
    - skill_execution 类步骤：给全部工具（搜索 + execute_skill），允许执行实际操作。
    - dispatch 类步骤（create_ticket 等）：给搜索工具，结果通过 dispatch_actions JSON 块输出。

    设计决策：始终使用 invoke（非 stream_events）获取结果，原因：
    1. stream_events 的 on_chat_model_stream 在 tool_calls 后可能不触发，导致丢失最终回复
    2. invoke 始终返回完整的 messages 列表，可靠提取最终文本
    3. tool call 信息从 invoke 结果的 messages 中提取，回放给回调做终端展示
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langchain_core.messages import HumanMessage

    # 根据当前步骤 capability 决定工具集，防止 query_data 步骤越界执行后续操作
    step = state.get_current_step()
    step_capability = ""
    if step:
        step_capability = (
            step.capability
            if hasattr(step, "capability")
            else step.get("capability", "")
        )

    brain_agent = _create_marathon_brain(step_capability=step_capability)

    # 构建用户消息
    user_msg = f"""[渠道:cli][Marathon执行]

{context}"""

    # 每次尝试使用独立thread_id，避免checkpointer累积历史导致token溢出
    step_id = step.id if step else 0
    step_attempts = step.attempts if step else 1
    thread_id = f"marathon-{state.marathon_id}-s{step_id}-a{step_attempts}"

    # 设置执行上下文 ID，使 execute_skill 的幂等性缓存能隔离不同 step/attempt
    set_execution_context_id(thread_id)

    # 抑制 stderr 编码错误
    # 构建 rubric（acceptance_criteria）—— RubricMiddleware 用它来评判结果
    step_obj = state.get_current_step()
    step_criteria = ""
    if step_obj:
        step_criteria = (
            step_obj.acceptance_criteria
            if hasattr(step_obj, "acceptance_criteria")
            else step_obj.get("acceptance_criteria", "")
        )

    invoke_input = {"messages": [HumanMessage(content=user_msg)]}
    if step_criteria:
        invoke_input["rubric"] = step_criteria

    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        result = brain_agent.invoke(
            invoke_input,
            config={"configurable": {"thread_id": thread_id}},
        )
    finally:
        sys.stderr = old_stderr

    # 回放 tool calls 给终端展示（invoke 完成后一次性回放）
    _replay_tool_calls_for_display(result)

    # 提取最终文本回复（向后遍历消息列表，跳过纯 tool_call 消息）
    raw_response = _extract_final_text(result)

    # 处理 dispatch_actions（创建工单/通知/分派任务）然后再清理标记
    if raw_response:
        action_results = _process_dispatch_actions(raw_response)
        if action_results:
            raw_response = _clean_response_markers(raw_response)
            raw_response += "\n\n" + action_results
        else:
            raw_response = _clean_response_markers(raw_response)

    return raw_response or "大脑未返回有效回复"


# ==================== Marathon 专用大脑（按 capability 动态工具集） ====================
_marathon_brain_cache = {}  # {工具集签名: agent实例}


def _on_rubric_evaluation(eval_data):
    """RubricMiddleware 的 on_evaluation 回调——每次评分后触发。
    通过 _brain_event_callback 推送给 terminal 展示。

    v2 Rubric 感知去重：当 Rubric 评估结果为 satisfied 时，
    记录当前 exec_id 到 _rubric_passed_exec_ids 集合。
    后续同一 exec_id 内的 execute_skill 调用将被跳过，避免重复执行有副作用的操作（如重复发邮件）。

    Rubric 未通过时，exec_id 不在集合中，execute_skill 仍允许重新执行。
    """
    # 检测 Rubric 是否通过 → 记录 exec_id，后续 execute_skill 使用此标记跳过执行
    # 用在 RubricMiddleware 重试场景：Rubric 已通过的步骤不应该再次执行有副作用的操作
    result = eval_data.get("result", "unknown")
    if result == "satisfied":
        exec_id = _current_execution_id
        if exec_id:
            _rubric_passed_exec_ids.add(exec_id)
            print(
                f"[Rubric-DEBUG] PASSED → record exec_id={exec_id[:30]}, "
                f"_rubric_passed_exec_ids size={len(_rubric_passed_exec_ids)}"
            )

    if not _brain_event_callback:
        return
    explanation = eval_data.get("explanation", "")
    iteration = eval_data.get("iteration", 0)
    criteria = eval_data.get("criteria", [])

    # === DEBUG: 记录每次 Rubric 评分 ===
    print(
        f"[Rubric-DEBUG] iter={iteration} | result={result} | "
        f"criteria={[{'name': c.get('name',''), 'passed': c.get('passed',False), 'gap': c.get('gap','')} for c in criteria]}"
    )
    if explanation:
        print(f"[Rubric-DEBUG] explanation={explanation[:200]}")

    _brain_event_callback(
        "rubric_evaluation",
        {
            "result": result,
            "explanation": explanation,
            "iteration": iteration,
            "criteria": [
                {
                    "name": c.get("name", ""),
                    "passed": c.get("passed", False),
                    "gap": c.get("gap", ""),
                }
                for c in criteria
            ],
        },
    )


def _create_marathon_brain(step_capability: str = ""):
    """创建 Marathon 专用大脑 agent（带 RAG + RubricMiddleware，execute_skill 按需注入）。

    按步骤 capability 动态裁剪工具集，防止 brain agent 越界执行后续步骤的操作：
    - query_data 类步骤（capability 为搜索工具名或 search_policy/query_* 等）：
      只给搜索工具，不给 execute_skill——物理上无法提前发邮件/约会议室。
    - skill_execution 类步骤（capability 以 skill- 开头）：
      给全部工具（搜索 + execute_skill），允许发邮件、预约会议室等实际操作。
    - dispatch 类步骤（capability 为 create_ticket/create_notification 等）：
      给搜索工具，结果通过 dispatch_actions JSON 块输出。

    按工具集签名缓存实例，避免完全相同的配置重复创建。
    禁用文件系统工具（write_file/edit_file/delete_file），防止创建垃圾文件或误删。
    """
    # 判定是否需要 execute_skill：只有 capability 以 skill- 开头时注入
    has_execute_skill = bool(step_capability) and step_capability.startswith("skill-")

    cache_key = f"skill={has_execute_skill}"
    if cache_key in _marathon_brain_cache:
        return _marathon_brain_cache[cache_key]

    from src.brain import (
        create_deep_agent,
        get_llm,
        _get_brain_checkpointer,
        search_policy,
        search_employee_database,
        query_employee_roster,
        query_attendance,
        SYSTEM_PROMPT,
        MEMORY_DIR,
    )
    from deepagents.backends import StateBackend
    from deepagents.profiles import HarnessProfile, register_harness_profile
    from deepagents import RubricMiddleware

    # 禁用文件系统工具，防止创建垃圾文件或误删
    register_harness_profile(
        "openai:[大模型名称]",
        HarnessProfile(
            excluded_tools=frozenset(
                {"ls", "read_file", "write_file", "edit_file", "glob", "grep"}
            ),
        ),
    )

    # 基础搜索工具列表
    tools = [
        search_policy,
        search_employee_database,
        query_employee_roster,
        query_attendance,
    ]

    # 只有 skill_execution 类步骤才注入 execute_skill
    if has_execute_skill:
        execute_skill_tool = create_execute_skill_tool()
        tools.append(execute_skill_tool)

    agent = create_deep_agent(
        model=get_llm(),
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
        middleware=[
            RubricMiddleware(
                model=get_llm(),
                max_iterations=3,
                on_evaluation=_on_rubric_evaluation,
            ),
        ],
        backend=StateBackend(),
        checkpointer=_get_brain_checkpointer(),
        memory=[str(MEMORY_DIR / "AGENTS.md")],
    )
    _marathon_brain_cache[cache_key] = agent
    return agent


def _process_dispatch_actions(text: str) -> str:
    """从大脑回复中提取 dispatch_actions JSON 并执行。
    返回执行结果摘要字符串（追加到大脑回复末尾）。
    """
    # 提取 ```json 和 ``` 之间的全部内容（死格式：``` 包裹）
    match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if not match:
        return ""

    raw_json = match.group(1).strip()

    # 大脑可能输出截断的 JSON，尝试修复
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        # 尝试修复：大模型常在 description 中截断，导致 JSON 不完整
        # 尝试补全缺失的括号
        try:
            # 移除末尾的不完整内容，找到最后一个完整的 } 或 ]
            for i in range(len(raw_json) - 1, -1, -1):
                if raw_json[i] in ("}", "]", '"'):
                    try:
                        data = json.loads(raw_json[: i + 1])
                        break
                    except json.JSONDecodeError:
                        continue
            else:
                return ""
        except Exception:
            return ""

    actions = data.get("dispatch_actions", [])
    if not actions:
        return ""

    results = []
    for action in actions:
        action_type = action.get("type", "")
        try:
            if action_type == "create_ticket":
                result = _exec_create_ticket(action)
                if result:
                    results.append(result)
            elif action_type == "create_notification":
                result = _exec_create_notification(action)
                if result:
                    results.append(result)
            elif action_type == "dispatch_cli_task":
                result = _exec_create_ticket(action)
                if result:
                    results.append(result)
            elif action_type == "reply_employee":
                pass
        except Exception:
            pass

    if results:
        return "📋 系统执行结果:\n" + "\n".join(results)
    return ""


def _exec_create_ticket(action) -> str:
    """调用服务端 API 创建工单。从 users.json 查找角色对应的具体人员。
    返回执行结果字符串。
    """
    import requests

    title = action.get("title", "")
    target_role = action.get("target_role", "员工关系专员")
    description = action.get("description", "")
    priority = action.get("priority", "normal")
    category = action.get("category", "")

    # 大脑可能在 action 中指定了 assignee_name（精确到人）
    brain_assignee = action.get("assignee_name", "")
    # 从 users.json 查找：优先 assignee_name，其次 target_role
    assignee_info = _find_user_by_role(target_role, assignee_name=brain_assignee)
    assignee_name = ""
    if assignee_info:
        assignee_name = assignee_info.get("display_name", "")

    # 从环境变量获取服务端 URL 和 Token
    server_url = os.environ.get("SSC_SERVER_URL", "http://localhost:8000")
    token = os.environ.get("SSC_TOKEN", "")

    url = f"{server_url}/api/tickets"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = {
        "title": title,
        "description": description,
        "priority": priority,
        "category": category or target_role,
    }
    if assignee_name:
        body["assignee"] = assignee_name

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        if resp.status_code < 300:
            result = resp.json()
            ticket_no = result.get("ticket_no", "")
            assignee_text = (
                f"，指派给{assignee_name}"
                if assignee_name
                else f"，待分派({target_role})"
            )
            return f"✅ 工单 {ticket_no} 已创建: {title[:40]}{assignee_text}"
        else:
            return f"⚠️ 工单创建失败: HTTP {resp.status_code}"
    except Exception as e:
        return f"⚠️ 工单创建异常: {str(e)[:100]}"


def _exec_create_notification(action) -> str:
    """调用服务端 API 创建通知。返回执行结果字符串。"""
    import requests

    title = action.get("title", "")
    content = action.get("content", "")
    target_user = action.get("target_user", "all_ssc")
    notif_type = action.get("notif_type", "info")

    server_url = os.environ.get("SSC_SERVER_URL", "http://localhost:8000")
    token = os.environ.get("SSC_TOKEN", "")

    url = f"{server_url}/api/notifications"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = {
        "title": title,
        "content": content,
        "target_user": target_user,
        "type": notif_type,
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        if resp.status_code < 300:
            return f"✅ 通知已创建: {title[:40]}"
        else:
            return f"⚠️ 通知创建失败: HTTP {resp.status_code}"
    except Exception as e:
        return f"⚠️ 通知创建异常: {str(e)[:100]}"


def _clean_response_markers(text: str) -> str:
    """移除响应中的结构化标记（死格式，用正则处理）。
    - dispatch_actions JSON 块：```json ... "dispatch_actions" ... ```
    - 秘书任务标记：【秘书任务】...【/秘书任务】
    """
    # 移除 ```json ... ``` 代码块（死格式：``` 包裹）
    text = re.sub(r"```json\s*\n.*?\n\s*```", "", text, flags=re.DOTALL)
    # 移除秘书任务标记（死格式：中文书名号包裹）
    text = re.sub(r"【秘书任务】[\s\S]*?【/秘书任务】", "", text)
    return text.strip()


def _extract_action_result(brain_response, step):
    """从大脑回复中提取摘要（用于执行日志记录）。
    摘要是活信息，但此处仅用于内部日志，取前100字符做概览即可。
    """
    if not brain_response:
        return "执行完成（无回复内容）", {}
    summary = brain_response[:100].replace("\n", " ").strip()
    return summary, {}
