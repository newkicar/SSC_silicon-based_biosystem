"""
Planner 节点 —— 任务规划（能力感知版本）

将用户的复杂HR业务需求拆解为可独立验证的子步骤。
规划前先读取完整能力清单，确保每个步骤都能对应到具体能力。
"""
import json
import re
from datetime import datetime


def planner_node(state):
    """LangGraph 节点：将大任务拆解为子步骤（基于能力清单）"""
    from staff.llm import get_llm
    from staff.marathon.state import SubTask, save_state, save_progress
    from staff.marathon.config import MARATHON_EXECUTING, STEP_PENDING, HITL_PLAN_REVIEW
    from staff.marathon.capability_registry import build_capability_prompt

    llm = get_llm()

    context_info = ""
    if state.context_summary:
        context_info = f"\n\n已有上下文信息：\n{state.context_summary}"

    # 生成完整能力清单（Skills + 搜索工具 + 系统能力 + 团队成员 + 能力边界）
    capability_prompt = build_capability_prompt()

    prompt = f"""你是一个HR业务流程规划器。将以下任务拆解为可独立验证的业务子步骤。

任务：{state.task_description}
{context_info}

{capability_prompt}

## 规划规则

1. **先看能力清单**——每个步骤必须能对应到上方某个具体能力（Skill/搜索工具/系统能力/团队成员）
2. **每个步骤必须可客观验证**——有明确的"通过/不通过"标准
3. **步骤粒度适中**——每步5-15分钟可完成
4. **步骤之间有逻辑顺序**——前一步的输出可能是后一步的输入
5. **包含验证性步骤**——关键步骤后安排"确认/检查"步骤
6. **优先使用 Skill**——当有匹配的 Skill 时，使用 skill_execution 动作类型，比手动操作更可靠
7. **超能力范围的步骤**——如果某个子任务需要的能力不在清单中，用 create_ticket 创建工单分派给合适的团队成员处理

## 可用的业务动作类型（action_type）

| 类型 | 说明 | 对应能力 |
|------|------|---------|
| query_data | 查询/检索数据 | 大脑搜索工具（search_policy/search_employee_database/query_employee_roster/query_attendance） |
| skill_execution | 执行客户端 Skill | 客户端自动化操作（见上方能力清单的🔧部分） |
| create_ticket | 创建工单 | 系统内置能力（dispatch_actions 格式C） |
| dispatch_task | 分派任务给特定角色 | 系统内置能力 |
| send_notification | 发送系统通知 | 系统内置能力 |
| check_status | 检查某项状态 | 大脑搜索工具 |
| generate_report | 生成报告/汇总 | 大脑搜索工具 |
| requires_human | 需要人工介入 | 能力清单中找不到对应能力时使用 |

**使用 skill_execution 时**，description 中必须写明：
1. 要执行哪个 Skill（从能力清单🔧部分选择）
2. 具体要做什么操作
3. 关键参数（收件人、会议室名、时间等）

## 输出格式

严格输出JSON数组，不要输出其他内容：

[
  {{
    "id": 0,
    "description": "步骤描述（做什么）",
    "acceptance_criteria": "验收标准（如何判断成功）",
    "action_type": "业务动作类型",
    "capability": "使用的具体能力名称（如 skill-outlook-controller / search_policy / create_ticket）"
  }},
  ...
]"""

    response = llm.invoke(prompt)
    raw_text = response.content if hasattr(response, "content") else str(response)

    plan = _parse_plan(raw_text)

    now = datetime.now().isoformat()
    step_objects = []
    for i, item in enumerate(plan):
        step_objects.append(SubTask(
            id=i,
            description=item.get("description", f"Step {i+1}"),
            acceptance_criteria=item.get("acceptance_criteria", ""),
            action_type=item.get("action_type", ""),
            capability=item.get("capability", ""),
            status=STEP_PENDING,
        ))

    if state.state_dir:
        save_state(state, state.state_dir)
        save_progress(state)

    # LangGraph StateGraph(dict) 要求所有值可序列化，必须转为 dict
    return {
        "plan": [s.to_dict() for s in step_objects],
        "current_step_index": 0,
        "step_error_count": 0,
        "global_error_count": 0,
        "started_at": now,
        "status": MARATHON_EXECUTING,
        "execution_log": [f"[{now}] 规划完成：{len(step_objects)} 个子步骤"],
    }


def _parse_plan(raw_text: str) -> list:
    """从LLM输出中提取JSON数组"""
    text = raw_text.strip()

    if text.startswith("```"):
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        text = text.strip()

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "steps" in result:
            return result["steps"]
        if isinstance(result, dict) and "plan" in result:
            return result["plan"]
    except json.JSONDecodeError:
        pass

    match = re.search(r'\[[\s\S]*\]', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    lines = [l.strip() for l in text.split("\n") if l.strip() and not l.strip().startswith("{")]
    steps = []
    for i, line in enumerate(lines[:20]):
        line = re.sub(r'^\d+[\.\)、]\s*', '', line)
        if line and len(line) > 5:
            steps.append({
                "id": i,
                "description": line,
                "acceptance_criteria": f"步骤'{line[:30]}...'执行成功",
                "action_type": "composite",
            })
    return steps