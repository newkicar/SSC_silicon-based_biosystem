"""
Marathon Agent — 执行引擎

Sprint 1: 手动驱动循环（不依赖LangGraph的state merge）
每个节点函数仍然保留LangGraph接口，但由我们自己管理状态传递。

后续Sprint可升级为真正的LangGraph StateGraph。
"""
import time
from datetime import datetime

from staff.marathon.state import MarathonState, ensure_state_dir, save_state, save_progress, load_state
from staff.marathon.nodes.planner import planner_node
from staff.marathon.nodes.executor import executor_node
from staff.marathon.nodes.validator import validator_node
from staff.marathon.nodes.committer import committer_node
from staff.marathon.nodes.error_handler import error_handler_node
from staff.marathon.config import (
    MARATHON_PLANNING, MARATHON_DONE, MARATHON_FAILED, MARATHON_PAUSED, MARATHON_CANCELLED,
    STEP_SKIPPED, MAX_RETRIES_PER_STEP, MAX_GLOBAL_RETRIES
)


def _apply_update(state, updates):
    """将节点返回的dict更新应用到MarathonState"""
    for k, v in updates.items():
        if k == "plan":
            # plan 是 dict 列表，需要重建 SubTask 对象
            from staff.marathon.state import SubTask
            state.plan = [SubTask.from_dict(s) if isinstance(s, dict) else s for s in v]
        elif k == "current_validation":
            from staff.marathon.state import ValidationResult
            if isinstance(v, dict):
                state.current_validation = ValidationResult.from_dict(v)
            else:
                state.current_validation = v
        elif hasattr(state, k):
            setattr(state, k, v)
    return state


def run_marathon(task_description, username, display_name, project_root, stream_callback=None):
    """运行一个完整的 Marathon 任务"""
    marathon_id = f"marathon-{int(time.time())}"
    state_dir = ensure_state_dir(marathon_id, project_root)

    state = MarathonState(
        marathon_id=marathon_id, task_description=task_description,
        username=username, display_name=display_name,
        status=MARATHON_PLANNING, state_dir=state_dir,
    )
    save_state(state, state_dir)
    save_progress(state)

    # ── Step 1: 规划 ──
    if stream_callback:
        stream_callback("planner", {}, state.to_dict())

    updates = planner_node(state)
    state = _apply_update(state, updates)
    if stream_callback:
        stream_callback("planner", updates, state.to_dict())

    if not state.plan:
        state.status = MARATHON_FAILED
        state.is_complete = True
        save_state(state, state_dir)
        save_progress(state)
        return state

    # ── Step 2: 逐步执行 ──
    while state.current_step_index < len(state.plan):
        step = state.get_current_step()
        if step is None:
            break

        # Executor
        updates = executor_node(state)
        state = _apply_update(state, updates)
        if stream_callback:
            stream_callback("executor", updates, state.to_dict())

        # 检查执行是否成功
        exec_v = state.current_validation
        exec_passed = exec_v.passed if exec_v else False

        if not exec_passed:
            # 执行失败 → Error Handler
            updates = error_handler_node(state)
            state = _apply_update(state, updates)
            if stream_callback:
                stream_callback("error_handler", updates, state.to_dict())

            if state.status in (MARATHON_PAUSED, MARATHON_FAILED):
                break
            continue

        # Validator
        updates = validator_node(state)
        state = _apply_update(state, updates)
        if stream_callback:
            stream_callback("validator", updates, state.to_dict())

        # 检查验证是否通过
        val_v = state.current_validation
        val_passed = val_v.passed if val_v else False

        if not val_passed:
            # 验证失败 → Error Handler
            updates = error_handler_node(state)
            state = _apply_update(state, updates)
            if stream_callback:
                stream_callback("error_handler", updates, state.to_dict())

            if state.status in (MARATHON_PAUSED, MARATHON_FAILED):
                break
            continue

        # Committer（验证通过 → 提交检查点 + 推进到下一步）
        updates = committer_node(state)
        state = _apply_update(state, updates)
        if stream_callback:
            stream_callback("committer", updates, state.to_dict())

        # 重置步骤错误计数（成功步骤后）
        state.step_error_count = 0

    # ── Step 3: 最终保存 ──
    if state.current_step_index >= len(state.plan) and state.status != MARATHON_FAILED:
        state.status = MARATHON_DONE
        state.is_complete = True
        state.completed_at = datetime.now().isoformat()

    save_state(state, state_dir)
    save_progress(state)
    return state


def resume_marathon(state_dir, user_decision="r", stream_callback=None):
    """恢复一个暂停的 Marathon"""
    state = load_state(state_dir)
    if state is None:
        raise ValueError(f"无法从 {state_dir} 加载状态")

    if user_decision == "e":
        state.status = MARATHON_CANCELLED
        state.is_complete = True
        save_state(state)
        save_progress(state)
        return state

    if user_decision == "s":
        step = state.get_current_step()
        if step:
            step.status = STEP_SKIPPED
            step.result_summary = "人类选择跳过"
        state.current_step_index += 1
        state.step_error_count = 0
        state.requires_human = False
        state.human_message = ""
        state.status = "executing"
        save_state(state)
        save_progress(state)

    if user_decision == "r":
        state.step_error_count = 0
        state.requires_human = False
        state.human_message = ""
        state.status = "executing"

    # 从当前状态继续执行剩余步骤
    while state.current_step_index < len(state.plan):
        step = state.get_current_step()
        if step is None:
            break

        # Executor
        if stream_callback:
            stream_callback("executor", {}, state.to_dict())
        updates = executor_node(state)
        state = _apply_update(state, updates)
        if stream_callback:
            stream_callback("executor", updates, state.to_dict())

        exec_v = state.current_validation
        exec_passed = exec_v.passed if exec_v else False

        if not exec_passed:
            if stream_callback:
                stream_callback("error_handler", {}, state.to_dict())
            updates = error_handler_node(state)
            state = _apply_update(state, updates)
            if stream_callback:
                stream_callback("error_handler", updates, state.to_dict())
            if state.status in (MARATHON_PAUSED, MARATHON_FAILED):
                break
            continue

        # Validator
        if stream_callback:
            stream_callback("validator", {}, state.to_dict())
        updates = validator_node(state)
        state = _apply_update(state, updates)
        if stream_callback:
            stream_callback("validator", updates, state.to_dict())

        val_v = state.current_validation
        val_passed = val_v.passed if val_v else False

        if not val_passed:
            if stream_callback:
                stream_callback("error_handler", {}, state.to_dict())
            updates = error_handler_node(state)
            state = _apply_update(state, updates)
            if stream_callback:
                stream_callback("error_handler", updates, state.to_dict())
            if state.status in (MARATHON_PAUSED, MARATHON_FAILED):
                break
            continue

        # Committer
        if stream_callback:
            stream_callback("committer", {}, state.to_dict())
        updates = committer_node(state)
        state = _apply_update(state, updates)
        if stream_callback:
            stream_callback("committer", updates, state.to_dict())

        state.step_error_count = 0

    if state.current_step_index >= len(state.plan) and state.status != MARATHON_FAILED:
        state.status = MARATHON_DONE
        state.is_complete = True
        state.completed_at = datetime.now().isoformat()

    save_state(state, state_dir)
    save_progress(state)
    return state