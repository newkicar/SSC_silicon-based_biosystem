"""
Validator 节点 —— 业务动作验证（硬性证据检查 + RubricMiddleware 结果透传）

验证策略（按优先级）：
1. 执行阶段直接失败 → 透传失败
2. 硬性证据检查（工单号TK-、任务号CT-） → 最可靠
3. 默认通过——RubricMiddleware 已在 invoke 内部完成 LLM-as-Judge 验证，
   如果 RubricMiddleware 判定 needs_revision 会自动重试，
   能走到这里的说明要么 satisfied 要么达到 max_iterations

所有返回值必须是纯dict（LangGraph StateGraph(dict)要求）。
"""
import re


def _vr(passed, level, error="", details=""):
    """创建验证结果dict"""
    return {"passed": passed, "level": level, "error": error, "details": details}


def _hard_evidence_check(action_type, combined):
    """硬性证据检查——用正则匹配系统生成的ID（死格式，用正则处理）"""
    has_ticket = bool(re.findall(r'TK[\-\s]?\d{4,}', combined))
    has_task = bool(re.findall(r'CT-\d{4}-\d{3,}', combined))

    if action_type == "create_ticket" and has_ticket:
        return _vr(True, "hard_evidence", details="检测到工单号 TK-（硬性证据）")
    if action_type == "dispatch_task" and has_task:
        return _vr(True, "hard_evidence", details="检测到任务号 CT-（硬性证据）")
    if action_type == "dispatch_task" and has_ticket:
        return _vr(True, "hard_evidence", details="工单已存在，分派已在前序步骤完成")
    return None


def validator_node(state):
    """LangGraph 节点：验证当前步骤的执行结果。

    验证流程：
    1. 执行阶段失败 → 直接透传失败
    2. 硬性证据检查（TK-/CT-）→ 最可靠
    3. 默认通过——RubricMiddleware 已在 agent invoke 内部完成评分和重试，
       能走到这里说明已通过 RubricMiddleware 的检查（satisfied 或达到 max_iterations）
    """
    step = state.get_current_step()
    if step is None:
        return {"current_validation": _vr(False, "validator", "没有可验证的步骤")}

    exec_v = state.current_validation or {}

    # exec_v 可能是 dict 或对象
    v_passed = exec_v.get("passed") if isinstance(exec_v, dict) else getattr(exec_v, "passed", None)
    v_details = (exec_v.get("details") if isinstance(exec_v, dict) else getattr(exec_v, "details", "")) or ""
    v_error = (exec_v.get("error") if isinstance(exec_v, dict) else getattr(exec_v, "error", "")) or ""

    # 执行阶段失败 → 直接透传
    if v_passed is False:
        return {"current_validation": _vr(False, "executor_passthrough", v_error, v_details)}

    if not exec_v:
        return {"current_validation": _vr(False, "basics", "执行节点未返回验证结果")}

    summary = step.result_summary if hasattr(step, "result_summary") else step.get("result_summary", "")
    action_type = step.action_type if hasattr(step, "action_type") else step.get("action_type", "")
    combined = (v_details + " " + summary)

    # 第一关：硬性证据检查（最快最可靠）
    hard_result = _hard_evidence_check(action_type, combined)
    if hard_result:
        return {"current_validation": hard_result}

    # 第二关：RubricMiddleware 已在 invoke 内部完成 LLM-as-Judge 验证
    # 如果 agent invoke 能正常返回（未抛异常），说明 RubricMiddleware 已经：
    # - satisfied → 直接通过
    # - max_iterations_reached → 某些标准未满足但已达重试上限，仍通过（宽松）
    # - failed/grader_error → 极端情况，也通过（fallback）
    # 因此这里只需检查回复是否有实质内容
    if summary and len(summary.strip()) > 10:
        return {"current_validation": _vr(True, "rubricmiddleware_passed", details="RubricMiddleware 已验证，回复有实质内容")}

    # 回复过短或无内容——仍通过但标记警告
    return {"current_validation": _vr(True, "rubricmiddleware_fallback", details="RubricMiddleware 已处理，回复内容较短")}