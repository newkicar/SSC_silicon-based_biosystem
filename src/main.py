"""
SSC硅基生物系统 - 主入口

系统启动流程：
1. 初始化数据库（三层记忆的Database层 + 统一数据层）
2. 初始化记忆文件（三层记忆的MD层）
3. 创建大脑Agent
4. 启动控制台测试模式

完整信息流（v11.0 deepagents agent loop）：
  员工输入
    → 上行脊髓(身份识别+渠道标注+紧急度评估)
    → 中枢神经节(反射弧判断)
      → 匹配反射弧 → 直接响应
      → 未匹配 → 大脑agent loop（带搜索工具，自主搜索+推理）
    → 下行脊髓(任务编排) → 终端执行
    → 结果回传 → 保存记忆
"""

import sys
import os

# Windows GBK编码兼容：强制stdout使用UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        os.environ["PYTHONIOENCODING"] = "utf-8"

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import uuid
import json
from datetime import datetime

from src.config.settings import get_llm
from src.memory.database import init_db, save_conversation
from src.memory.md_memory import ensure_memory_file
from src.data.task_queue import (
    init_task_tables,
    insert_task_bs,
    claim_task_bs,
    insert_event,
)
from src.brain import create_brain_agent_with_tools
from src.spine.ascending import process_employee_inquiry, IntelligencePacket
from src.spine.descending import (
    generate_task_id,
    process_descending_task,
)
from src.spine.dispatcher import dispatch_actions
from src.ganglion.reflex import try_reflex
from src.security.immune import ImmuneChecker

from langchain_core.messages import HumanMessage

# ==================== 初始化 ====================
print("[SSC硅基生物系统] 正在初始化...")
init_db()
init_task_tables()
ensure_memory_file()

from src.data.cli_tasks import init_cli_task_table

init_cli_task_table()

from src.data.context_pool import init_context_pool, create_case, append_timeline

init_context_pool()

from src.scheduler.scheduler import Scheduler

scheduler = Scheduler()
scheduler.start()

print("[SSC硅基生物系统] 数据库已初始化（含统一数据层）")
print("[SSC硅基生物系统] 记忆文件已就绪")
print("[SSC硅基生物系统] 上下文池已初始化")
print("[SSC硅基生物系统] 定时调度器已启动")


# ==================== 辅助函数 ====================
def _strip_routing_prefixes(text: str) -> tuple:
    """剥离系统注入的路由前缀，返回 (原始消息, 提问人姓名, 提问人角色)。

    系统前缀格式（server.py 注入，死格式）：
    [渠道:web][安全规则] 我是{role}（{name}），

    这些前缀是给大脑的路由上下文和身份上下文，不应出现在人类可见的任务元数据中。
    """
    cleaned = text.strip()
    asker_name = ""
    asker_role = ""

    # 1. 移除 [渠道:xxx]（死格式：server.py 注入的渠道标记）
    if cleaned.startswith("[渠道:"):
        idx = cleaned.find("]")
        if idx >= 0:
            cleaned = cleaned[idx + 1 :].strip()

    # 2. 移除 [安全规则]（死格式：server.py 注入的安全前缀）
    if cleaned.startswith("[安全规则]"):
        cleaned = cleaned[len("[安全规则]") :].strip()

    # 3. 移除 [Marathon执行]（死格式：Marathon 注入的标记）
    if cleaned.startswith("[Marathon执行]"):
        cleaned = cleaned[len("[Marathon执行]") :].strip()

    # 4. 提取并移除 "我是{role}（{name}），"（死格式：server.py 注入的身份前缀）
    if cleaned.startswith("我是"):
        paren_open = cleaned.find("（")
        paren_close = cleaned.find("）")
        if paren_open > 0 and paren_close > paren_open:
            asker_role = cleaned[2:paren_open]
            asker_name = cleaned[paren_open + 1 : paren_close]
            rest = cleaned[paren_close + 1 :]
            if rest.startswith("，") or rest.startswith(","):
                rest = rest[1:]
            cleaned = rest.strip()

    # 5. 清理开头可能残留的其他 [xxx] 标记
    while cleaned.startswith("["):
        idx = cleaned.find("]")
        if idx >= 0:
            cleaned = cleaned[idx + 1 :].strip()
        else:
            break

    return cleaned if cleaned else text, asker_name, asker_role


def _build_fallback_dispatch(
    response: str,
    original_message: str,
    packet,
    asker_name: str = "",
    asker_role: str = "",
) -> list:
    """兜底分派：大脑说了"转交"但没输出 dispatch_actions 时自动创建工单。

    参数：
        response: 大脑的清理后回复（给人看的）
        original_message: 原始用户消息（已剥离系统前缀）
        packet: 情报包
        asker_name: 真实提问人姓名（从路由前缀中提取）
        asker_role: 真实提问人角色

    v13: 任务元数据使用清理后的原始消息，不包含系统路由标记。
    """
    # v15: 兜底分配已彻底禁用。检测到转交意图但无 dispatch_actions 时，
    # 打印详细异常日志供调试，但不自动创建工单。
    transfer_keywords = [
        "转交",
        "转给",
        "分配给",
        "交由",
        "安排",
        "负责处理",
        "跟进处理",
    ]
    has_transfer_intent = any(kw in response for kw in transfer_keywords)
    if has_transfer_intent:
        print(f"[分派异常] 大脑回复包含转交意图但未输出 dispatch_actions")
        print(f"  ├─ 大脑回复: {response[:200]}")
        print(f"  ├─ 原始消息: {original_message[:100]}")
        print(f"  ├─ 提问人: {asker_name}({asker_role})")
        print(f"  └─ 原因: 大脑未按格式C输出 dispatch_actions JSON，工单不会被创建")
    return []


def _apply_dispatch_results(response: str, dispatch_summary: dict) -> str:
    """从 dispatch 结果中提取 reply_employee 消息，拼接到回复中。"""
    if not dispatch_summary:
        return response

    for r in dispatch_summary.get("results", []):
        if r.get("type") == "reply" and r.get("message"):
            msg = r["message"].strip()
            # 避免重复：如果回复消息已在主文本中，不重复追加
            if msg and msg not in response:
                if response:
                    response = response + "\n\n" + msg
                else:
                    response = msg

    has_reply = any(
        r.get("type") == "reply" for r in dispatch_summary.get("results", [])
    )
    if not has_reply and dispatch_summary.get("cli_tasks_dispatched", 0) > 0:
        # 优先用 assignee_name（具体人名），回退到 target_role（角色名）
        target_names = []
        for r in dispatch_summary.get("results", []):
            if r.get("type") in ("cli_task", "ticket"):
                name = r.get("assignee_name", "") or r.get("target_role", "")
                if name:
                    target_names.append(name)
        if target_names:
            target_str = "、".join(set(target_names))
            status_msg = (
                f"\n\n📋 已自动创建工单并分派给{target_str}处理，会尽快为您办理。"
            )
            response = (response + status_msg) if response else status_msg

    return response


def _extract_dispatch_json(raw_response: str) -> tuple:
    """从大脑回复中提取 dispatch_actions JSON 块。返回 (clean_text, actions_list)。"""
    import re

    json_pattern = r"```json\s*\n?([\s\S]*?)\n?```"
    matches = re.findall(json_pattern, raw_response)

    actions = []
    clean_text = raw_response

    for match in matches:
        try:
            parsed = json.loads(match)
            if "dispatch_actions" in parsed:
                actions = parsed["dispatch_actions"]
                clean_text = clean_text.replace(f"```json\n{match}```", "").strip()
                clean_text = clean_text.replace(f"```json\n{match}\n```", "").strip()
                clean_text = clean_text.replace(f"```json{match}```", "").strip()
                break
        except json.JSONDecodeError:
            continue

    return clean_text, actions


def _clean_response(raw_response: str) -> str:
    """清理大脑回复中的内部标记，确保用户只看到正常回复。"""
    import re

    if not raw_response:
        return "您的请求已收到，正在处理中。"

    response = raw_response

    # 移除JSON dispatch块
    json_pattern = r"```json\s*\n?[\s\S]*?dispatch_actions[\s\S]*?```"
    response = re.sub(json_pattern, "", response).strip()

    # 移除【秘书任务】标记
    if "【秘书任务】" in response:
        secretary_start = response.find("【秘书任务】")
        clean_part = response[:secretary_start].strip()
        response = (
            clean_part
            if clean_part
            else "您的请求已收到，正在为您采集相关信息，请稍候。"
        )

    # 移除【任务指令】标记
    if "【任务指令】" in response:
        task_start = response.find("【任务指令】")
        response = response[:task_start].strip()

    return response if response else "您的请求已收到，正在处理中。"


# ==================== 核心处理流程 ====================
def process_message(
    user_input: str, session_id: str = None, cross_round_seen: set = None
) -> str:
    """
    处理用户消息——deepagents agent loop 架构。

    上行脊髓做机械性预取 → 反射弧匹配 → 大脑agent loop（带搜索工具，自主搜索+推理）

    Args:
        user_input: 用户输入
        session_id: 会话ID
        cross_round_seen: 跨轮次通知去重集合（传递给 dispatch_actions）
    """
    if session_id is None:
        session_id = str(uuid.uuid4())

    immune_check = ImmuneChecker.check_data_quality({"content": user_input})
    if not immune_check["passed"]:
        return "您的输入存在问题，无法处理。"

    save_conversation(
        session_id=session_id,
        role="user",
        content=user_input,
        source="employee_chat",
        importance_score=0.5,
    )
    case_id = f"CASE-{session_id[:8]}"
    create_case(
        case_id=case_id,
        summary={"raw_input": user_input, "status": "processing"},
        related_info={"session_id": session_id},
    )
    append_timeline(case_id, {"action": "收到用户输入", "detail": user_input[:100]})
    insert_event(
        event_id=generate_task_id("EVT"),
        event_type="employee_query",
        source="employee_chat",
        payload={"content": user_input, "session_id": session_id},
    )

    # ---- 上行脊髓（机械性：身份识别+渠道标注+紧急度） ----
    print("\n[上行脊髓] 接收到员工消息，开始数据预取...")
    packet: IntelligencePacket = process_employee_inquiry(user_input)
    print(f"[上行脊髓] 情报包已生成，紧急度: {packet.urgency}")

    # ---- 中枢神经节（反射弧）----
    print("[中枢神经节] 尝试反射弧匹配...")
    reflex_result = try_reflex(packet)
    reflex_context = ""
    if reflex_result.handled:
        print("[中枢神经节] 反射弧命中！结果将作为上下文传递给大脑。")
        reflex_context = reflex_result.response

    # ---- 提前剥离路由前缀，获取提问人身份（供后续注入大脑 input 使用） ----
    original_message, asker_name, asker_role = _strip_routing_prefixes(user_input)

    # ---- 构建情报提示 ----
    intelligence_prompt = packet.to_prompt()
    if reflex_context:
        intelligence_prompt += f"\n\n## 反射弧预检索结果（仅供参考）\n{reflex_context}"

    try:
        from src.security.auth import get_all_ssc_specializations

        specs = get_all_ssc_specializations()
        if specs:
            spec_lines = [
                f"- {s['display_name']}（{s['role']}）：{s['specialization']}"
                for s in specs
            ]
            intelligence_prompt += (
                "\n\n## SSC操作人员岗位职责明细\n"
                + "\n".join(spec_lines)
                + "\n\n分派规则：\n1. 匹配 specialization 与任务最吻合的人员\n"
                "2. 角色只有一人时直接分派\n3. 用 target_username 指定具体人员\n"
            )
    except Exception:
        pass

    # 注入当前提问者身份+组织域，供洞察通知路由使用
    try:
        from src.security.auth import _get_auth_connection

        conn = _get_auth_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT username, display_name, role, department, center, company, specialization FROM users WHERE display_name = ? OR username = ?",
            (asker_name, asker_name),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            user_ctx = {
                "username": row["username"],
                "display_name": row["display_name"],
                "role": row["role"],
                "department": row["department"] or "",
                "center": row["center"] or "",
                "company": row["company"] or "",
                "specialization": row["specialization"] or "",
            }
            org_field = (
                user_ctx["center"] or user_ctx["department"] or user_ctx["company"]
            )
            org_level = (
                "center"
                if user_ctx["center"]
                else ("department" if user_ctx["department"] else "company")
            )
            intelligence_prompt += (
                "\n\n## 当前提问者身份（用于洞察通知路由）\n"
                f"- 姓名：{user_ctx['display_name']}（{user_ctx['username']}）\n"
                f"- 角色：{user_ctx['role']}\n"
                f"- 组织域：{org_field}（{org_level}）\n"
                f"- specialization：{user_ctx['specialization']}"
            )
    except Exception:
        pass

    # ---- 大脑 agent loop（带搜索工具）----
    print("[大脑] 使用 agent loop 模式（带搜索工具）...")
    brain_agent = create_brain_agent_with_tools()

    result = brain_agent.invoke(
        {"messages": [HumanMessage(content=intelligence_prompt)]},
        config={"configurable": {"thread_id": session_id}},
    )

    raw_response = ""
    if hasattr(result, "messages") and result.messages:
        raw_response = result.messages[-1].content
    elif isinstance(result, dict) and "messages" in result:
        raw_response = result["messages"][-1].content

    # ---- 分派处理（必须先提取 dispatch_actions，再清理回复文本）----
    clean_text, dispatch_list = _extract_dispatch_json(raw_response)
    response = _clean_response(clean_text if clean_text else raw_response)
    print(f"[大脑] agent loop 完成，生成 {len(response)} 字符回复")
    if not dispatch_list:
        dispatch_list = _build_fallback_dispatch(
            response, original_message, packet, asker_name, asker_role
        )
    dispatch_summary = None
    if dispatch_list:
        dispatch_summary = dispatch_actions(dispatch_list, session_id, cross_round_seen)
        response = _apply_dispatch_results(response, dispatch_summary)

    # ---- 下行脊髓 ----
    brain_task_id = generate_task_id("BS")
    insert_task_bs(
        task_id=brain_task_id,
        direction="DOWN",
        task_type="decision",
        priority="normal" if packet.urgency == "normal" else "high",
        from_layer="brain",
        payload={
            "brain_response": response,
            "original_inquiry": user_input,
            "recipient": "员工",
            "source": "brain_decision",
            "dispatch_summary": dispatch_summary,
        },
        context_ref=session_id,
    )
    brain_task = claim_task_bs(direction="DOWN", claimed_by="descending_spine")
    if brain_task:
        process_descending_task(brain_task)

    save_conversation(
        session_id=session_id,
        role="assistant",
        content=response,
        source="brain_decision",
        importance_score=0.7,
    )
    print("[系统] 处理完成。")
    return response


def process_message_stream(user_input: str, session_id: str = None):
    """流式版本——使用 brain agent with tools（非流式 invoke，统一架构）。"""
    if session_id is None:
        session_id = str(uuid.uuid4())

    immune_check = ImmuneChecker.check_data_quality({"content": user_input})
    if not immune_check["passed"]:
        yield ("error", "您的输入存在问题，无法处理。")
        return

    save_conversation(
        session_id=session_id,
        role="user",
        content=user_input,
        source="employee_chat",
        importance_score=0.5,
    )
    case_id = f"CASE-{session_id[:8]}"
    create_case(
        case_id=case_id,
        summary={"raw_input": user_input, "status": "processing"},
        related_info={"session_id": session_id},
    )
    append_timeline(case_id, {"action": "收到用户输入", "detail": user_input[:100]})
    insert_event(
        event_id=generate_task_id("EVT"),
        event_type="employee_query",
        source="employee_chat",
        payload={"content": user_input, "session_id": session_id},
    )

    yield ("status", "[上行脊髓] 接收到员工消息，开始数据预取...")
    packet: IntelligencePacket = process_employee_inquiry(user_input)
    yield ("status", f"[上行脊髓] 情报包已生成，紧急度: {packet.urgency}")

    yield ("status", "[中枢神经节] 尝试反射弧匹配...")
    reflex_result = try_reflex(packet)
    reflex_context = ""
    if reflex_result.handled:
        yield ("status", "[中枢神经节] 反射弧命中！结果将作为上下文传递给大脑。")
        reflex_context = reflex_result.response

    intelligence_prompt = packet.to_prompt()
    if reflex_context:
        intelligence_prompt += f"\n\n## 反射弧预检索结果（仅供参考）\n{reflex_context}"

    try:
        from src.security.auth import get_all_ssc_specializations

        specs = get_all_ssc_specializations()
        if specs:
            spec_lines = [
                f"- {s['display_name']}（{s['role']}）：{s['specialization']}"
                for s in specs
            ]
            intelligence_prompt += (
                "\n\n## SSC操作人员岗位职责明细\n"
                + "\n".join(spec_lines)
                + "\n\n分派规则：\n1. 匹配 specialization 与任务最吻合的人员\n"
                "2. 角色只有一人时直接分派\n3. 用 target_username 指定具体人员\n"
            )
    except Exception:
        pass

    yield ("status", "[大脑] 使用 agent loop 模式（带搜索工具）...")
    print("[大脑] 使用 agent loop 模式（带搜索工具）...")
    brain_agent = create_brain_agent_with_tools()

    result = brain_agent.invoke(
        {"messages": [HumanMessage(content=intelligence_prompt)]},
        config={"configurable": {"thread_id": session_id}},
    )

    raw_response = ""
    if hasattr(result, "messages") and result.messages:
        raw_response = result.messages[-1].content
    elif isinstance(result, dict) and "messages" in result:
        raw_response = result["messages"][-1].content

    # 剥离系统路由前缀，提取原始消息和提问人身份
    original_message, asker_name, asker_role = _strip_routing_prefixes(user_input)

    # 分派（必须先提取 dispatch_actions，再清理回复文本）
    clean_text, dispatch_list = _extract_dispatch_json(raw_response)
    response = _clean_response(clean_text if clean_text else raw_response)
    print(f"[大脑] agent loop 完成，生成 {len(response)} 字符回复")
    if not dispatch_list:
        dispatch_list = _build_fallback_dispatch(
            response, original_message, packet, asker_name, asker_role
        )
    dispatch_summary = None
    if dispatch_list:
        dispatch_summary = dispatch_actions(dispatch_list, session_id)
        response = _apply_dispatch_results(response, dispatch_summary)

    # 下行脊髓
    brain_task_id = generate_task_id("BS")
    insert_task_bs(
        task_id=brain_task_id,
        direction="DOWN",
        task_type="decision",
        priority="normal" if packet.urgency == "normal" else "high",
        from_layer="brain",
        payload={
            "brain_response": response,
            "original_inquiry": user_input,
            "recipient": "员工",
            "source": "brain_decision",
            "dispatch_summary": dispatch_summary,
        },
        context_ref=session_id,
    )
    brain_task = claim_task_bs(direction="DOWN", claimed_by="descending_spine")
    if brain_task:
        process_descending_task(brain_task)

    save_conversation(
        session_id=session_id,
        role="assistant",
        content=response,
        source="brain_decision",
        importance_score=0.7,
    )
    yield ("done", response)


# ==================== 测试入口 ====================
if __name__ == "__main__":
    print("[SSC硅基生物系统] 正在构建向量索引...")
    from src.tools.vector_rag import build_index, _build_db_index

    rag_count = build_index()
    db_count = _build_db_index()
    print(
        f"[SSC硅基生物系统] 向量索引就绪：RAG文档 {rag_count} 个切片，数据库 {db_count} 行数据"
    )

    print("\n" + "=" * 60)
    print("SSC硅基生物系统 v11.0 - 控制台测试模式")
    print("完整信息流：员工 → 上行脊髓 → 反射弧 → 大脑agent loop → 下行脊髓")
    print("输入消息与系统交互，输入 'quit' 退出")
    print("=" * 60 + "\n")

    session_id = str(uuid.uuid4())

    while True:
        user_input = input("\n[员工] > ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            print("系统关闭。")
            break
        if not user_input:
            continue

        response = process_message(user_input, session_id)
        print(f"\n[系统回复]\n{response}")
