"""
Committer 节点 —— 检查点 + 持久化

验证通过后：更新步骤状态、持久化、推进下一步。
"""
from datetime import datetime


def committer_node(state):
    """LangGraph 节点：验证通过后提交检查点"""
    from staff.marathon.state import save_state, save_progress
    from staff.marathon.config import STEP_DONE, MARATHON_DONE

    step = state.get_current_step()
    now = datetime.now().isoformat()

    if step and step.status != STEP_DONE:
        step.status = STEP_DONE
        step.completed_at = now
        if not step.result_summary:
            step.result_summary = "验证通过"

    if state.state_dir:
        save_state(state, state.state_dir)
        save_progress(state)

    if step:
        state.execution_log.append(f"[{now}] Step {step.id + 1} 已提交检查点")

    next_index = state.current_step_index + 1

    # plan 必须转为 dict 列表（LangGraph 要求）
    plan_dicts = [s.to_dict() if hasattr(s, "to_dict") else s for s in state.plan]

    if next_index >= len(state.plan):
        state.completed_at = now
        state.execution_log.append(f"[{now}] 所有步骤完成！")
        if state.state_dir:
            save_state(state, state.state_dir)
            save_progress(state)
        return {
            "current_step_index": next_index,
            "is_complete": True,
            "status": MARATHON_DONE,
            "completed_at": now,
            "plan": plan_dicts,
            "execution_log": state.execution_log,
        }

    return {
        "current_step_index": next_index,
        "step_error_count": 0,
        "plan": plan_dicts,
        "execution_log": state.execution_log,
    }
