"""
Error Handler 节点 —— 错误处理与重试决策

验证失败时决定：重试 / 暂停等人类 / 终止
"""
import time
from datetime import datetime


def error_handler_node(state):
    """LangGraph 节点：处理验证失败"""
    from staff.marathon.state import save_state, save_progress
    from staff.marathon.config import (
        STEP_FAILED, MARATHON_FAILED, MARATHON_PAUSED,
        MAX_RETRIES_PER_STEP, MAX_GLOBAL_RETRIES, RETRY_WAIT_SECONDS, HITL_ON_MAX_RETRIES,
    )

    step = state.get_current_step()
    now = datetime.now().isoformat()
    validation = state.current_validation or {}
    # validation 可能是 dict 或对象
    error_msg = (validation.get("error") if isinstance(validation, dict) else getattr(validation, "error", "")) or "未知错误"

    if step:
        step.error_log = error_msg
        step.error_history.append(f"[attempt {step.attempts}] {error_msg}")

    state.execution_log.append(f"[{now}] Step {(step.id + 1) if step else '?'} 错误处理: {error_msg[:80]}")

    # 全局错误上限
    if state.global_error_count >= MAX_GLOBAL_RETRIES:
        state.execution_log.append(f"[{now}] 全局错误次数已达上限({MAX_GLOBAL_RETRIES})，终止任务")
        if state.state_dir:
            save_state(state, state.state_dir)
            save_progress(state)
        return {"status": MARATHON_FAILED, "is_complete": True, "execution_log": state.execution_log,
                "human_message": f"任务失败：全局错误次数已达上限。最后错误：{error_msg[:200]}"}

    # 当前步骤重试上限
    if step and step.attempts >= MAX_RETRIES_PER_STEP:
        if HITL_ON_MAX_RETRIES:
            state.execution_log.append(f"[{now}] Step {step.id + 1} 重试超限，等待人类决策")
            if state.state_dir:
                save_state(state, state.state_dir)
                save_progress(state)
            return {"status": MARATHON_PAUSED, "requires_human": True,
                    "human_message": f"Step {step.id + 1} 已重试 {step.attempts} 次仍失败。\n错误：{error_msg[:300]}\n请选择：[r]重试 / [s]跳过 / [e]终止",
                    "execution_log": state.execution_log}
        else:
            step.status = STEP_FAILED
            return {"plan": state.plan, "current_step_index": state.current_step_index + 1, "step_error_count": 0, "execution_log": state.execution_log}

    # 可以重试
    wait_index = min(step.attempts - 1 if step else 0, len(RETRY_WAIT_SECONDS) - 1)
    wait_time = RETRY_WAIT_SECONDS[wait_index] if wait_index >= 0 else 3
    state.execution_log.append(f"[{now}] 等待 {wait_time} 秒后重试")
    if state.state_dir:
        save_state(state, state.state_dir)
    time.sleep(wait_time)

    # 注入错误上下文供重试时修正
    error_context = f"\n\n⚠️ 上次执行失败，错误原因：{error_msg}\n请分析失败原因，修正后重新执行。"
    state.context_summary = (state.context_summary or "") + error_context

    # plan 必须转为 dict 列表
    plan_dicts = [s.to_dict() if hasattr(s, "to_dict") else s for s in state.plan]

    return {
        "step_error_count": state.step_error_count + 1,
        "global_error_count": state.global_error_count + 1,
        "context_summary": state.context_summary,
        "plan": plan_dicts,
        "execution_log": state.execution_log,
    }
