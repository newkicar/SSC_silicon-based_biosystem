"""
洞察子代理：创建、验证、重试

负责创建 HR SSC 数据洞察子代理，并提供输出验证和自动重试机制。
使用 deepagents create_deep_agent() 创建独立的洞察子代理。

无降级方案：子代理创建失败直接抛异常。
"""

import json
import re


def validate_insight_output(result: dict) -> list:
    """验证洞察输出是否符合要求，返回错误列表。

    Args:
        result: 大脑输出的 dict，包含 dispatch_actions 列表

    Returns:
        错误信息列表，空列表表示验证通过
    """
    errors = []

    if not result or "dispatch_actions" not in result:
        return ["输出格式错误：缺少 dispatch_actions 字段"]

    actions = result.get("dispatch_actions", [])
    if not actions:
        return ["输出格式错误：dispatch_actions 为空"]

    for i, action in enumerate(actions):
        prefix = f"action[{i}]"

        if action.get("type") != "create_notification":
            continue

        # 检查 insight_level
        insight_level = action.get("insight_level")
        if not insight_level:
            errors.append(f"{prefix}: 缺少 insight_level 字段")
        elif insight_level not in ("company", "center", "department"):
            errors.append(
                f"{prefix}: insight_level 值无效 '{insight_level}'，应为 company/center/department"
            )

        # 检查 insight_org
        if "insight_org" not in action:
            errors.append(f"{prefix}: 缺少 insight_org 字段")

        # 检查 insight_type
        insight_type = action.get("insight_type")
        if not insight_type:
            errors.append(f"{prefix}: 缺少 insight_type 字段")
        elif insight_type not in ("cost", "attendance", "headcount", "er", "hris"):
            errors.append(f"{prefix}: insight_type 值无效 '{insight_type}'")

        # 检查 target_user
        target_user = action.get("target_user", "")
        if target_user in ("all", "all_ssc"):
            errors.append(
                f"{prefix}: target_user 不能使用 'all' 或 'all_ssc'，必须指定具体用户名"
            )
        elif target_user.startswith("scope:"):
            errors.append(
                f"{prefix}: target_user 不能使用 'scope:xxx' 格式，必须指定具体用户名"
            )
        elif not target_user:
            errors.append(f"{prefix}: target_user 为空")

        # 检查 title
        title = action.get("title", "")
        if not title:
            errors.append(f"{prefix}: 缺少 title 字段")
        elif title in ("洞察A", "通知B", "成本洞察", "标题"):
            errors.append(
                f"{prefix}: title 过于空泛 '{title}'，必须直接点明观察对象和结论"
            )

        # 检查 content
        content = action.get("content", "")
        if not content:
            errors.append(f"{prefix}: 缺少 content 字段")
        elif content in ("内容A", "具体内容含数据", "请查看详情"):
            errors.append(f"{prefix}: content 过于空泛 '{content}'")

    return errors


def format_errors_as_guidance(errors: list) -> str:
    """将验证错误转换为友好的指导说明。

    Args:
        errors: validate_insight_output 返回的错误列表

    Returns:
        格式化的指导文本，AI 可以直接理解并修正
    """
    if not errors:
        return ""

    guidance_parts = ["你的输出格式有误，请按以下说明修正：\n"]

    for err in errors:
        # 解析错误类型
        if "insight_level" in err and "值无效" in err:
            guidance_parts.append(
                "❌ insight_level 的值不正确。\n"
                "   只能使用：company（公司级）/ center（中心级）/ department（部门级）\n"
                '   例：公司级洞察 → "insight_level": "company"'
            )
        elif "缺少 insight_level" in err:
            guidance_parts.append(
                "❌ 缺少 insight_level 字段。\n"
                "   必须标明洞察级别：company / center / department\n"
                '   例：全公司数据 → "insight_level": "company"'
            )
        elif "缺少 insight_org" in err:
            guidance_parts.append(
                "❌ 缺少 insight_org 字段。\n"
                "   填写洞察涉及的组织名称：\n"
                '   - 公司级 → 留空 ""\n'
                '   - 中心级 → 中心名（如 "制造一中心"）\n'
                '   - 部门级 → 部门名（如 "总装部"）'
            )
        elif "insight_type" in err and "值无效" in err:
            guidance_parts.append(
                "❌ insight_type 的值不正确。\n"
                "   只能使用：cost / attendance / headcount / er / hris\n"
                "   cost=成本, attendance=考勤, headcount=编制, er=员工关系, hris=系统"
            )
        elif "缺少 insight_type" in err:
            guidance_parts.append(
                "❌ 缺少 insight_type 字段。\n"
                "   必须标明洞察类型：cost / attendance / headcount / er / hris"
            )
        elif "target_user" in err and ("all" in err or "scope:" in err):
            guidance_parts.append(
                "❌ target_user 使用了禁止的值。\n"
                '   禁止使用 "all"、"all_ssc" 或 "scope:xxx"\n'
                '   必须指定具体用户名，如 "110031"\n'
                "   可通过系统提供的用户名列表查找对应人员"
            )
        elif "target_user" in err and "为空" in err:
            guidance_parts.append(
                "❌ target_user 为空。\n"
                "   必须指定接收通知的具体用户名\n"
                "   公司级 → 总经理、副总经理、HR_SSC学科经理的工号\n"
                "   中心级 → 该中心总监、HRBP 的工号"
            )
        elif "title" in err and "空泛" in err:
            guidance_parts.append(
                "❌ title 过于空泛。\n"
                "   必须直接点明观察对象和结论，如：\n"
                '   ✅ "[考勤]制造一中心人均出勤65小时"\n'
                '   ❌ "洞察A" / "成本洞察" / "通知B"'
            )
        elif "缺少 title" in err:
            guidance_parts.append(
                "❌ 缺少 title 字段。\n"
                "   格式：[类型]具体内容（20字以内）\n"
                "   例：[考勤]全公司人均出勤59小时"
            )
        elif "content" in err and "空泛" in err:
            guidance_parts.append(
                "❌ content 过于空泛。\n"
                "   必须包含：具体数据 + 变化趋势 + 关注要点（40-200字）\n"
                '   例："6月全公司人均出勤59.95小时，较上月上升12%。建议关注..."'
            )
        elif "缺少 content" in err:
            guidance_parts.append(
                "❌ 缺少 content 字段。\n" "   写清：具体数据 + 变化趋势 + 关注要点"
            )
        else:
            # 兜底：原样保留
            guidance_parts.append(f"❌ {err}")

        guidance_parts.append("")  # 空行分隔

    # 添加好的示例
    guidance_parts.append("✅ 正确示例：")
    guidance_parts.append("""{
  "dispatch_actions": [{
    "type": "create_notification",
    "target_user": "110031",
    "title": "[考勤]XX心人均出勤xx小时",
    "content": "2026年6月XX心人均出勤xx小时...",
    "priority": "high",
    "notif_type": "alert",
    "insight_level": "center",
    "insight_org": "XX中心",
    "insight_type": "attendance"
  }]
}""")

    return "\n".join(guidance_parts)


def _fix_truncated_json(json_str: str) -> str:
    """尝试修复被截断的 JSON。"""
    last_quote = json_str.rfind('"')
    if last_quote >= 0:
        after = json_str[last_quote + 1 :]
        if after and not after.strip().startswith('"'):
            pos = last_quote - 1
            backslash_count = 0
            while pos >= 0 and json_str[pos] == "\\":
                backslash_count += 1
                pos -= 1
            if backslash_count % 2 == 0:
                json_str = json_str + '"'

    json_str = json_str + "]" * (json_str.count("[") - json_str.count("]"))
    json_str = json_str + "}" * (json_str.count("{") - json_str.count("}"))
    return json_str


def parse_json_from_response(response: str) -> dict:
    """从洞察子代理回复中提取 JSON 数据。

    直接使用 json 库解析，支持多种格式：
    1. 纯 JSON：{"dispatch_actions": [...]}
    2. markdown 代码块包裹：```json {...} ```
    3. 前后有其他文本：some text ```json {...} ``` more text
    4. 被截断的 JSON（自动尝试修复）

    如果解析失败返回空 dict，不会抛出异常。
    """
    print(f"\n{'='*60}")
    print(f"[JSON解析] ========== 开始解析 ==========")
    print(f"[JSON解析] 原始输出长度: {len(response)} 字符")
    print(f"[JSON解析] 原始输出前1000字符:")
    print(f"---")
    print(response[:1000])
    print(f"---")

    try:
        result = _extract_json_from_text(response)
        if result and "dispatch_actions" in result:
            print(
                f"[JSON解析] ✅ 解析成功，包含 {len(result.get('dispatch_actions', []))} 个 action"
            )
            print(f"[JSON解析] ========== 解析完成 ==========\n")
            return result
        else:
            print(f"[JSON解析] ⚠️ 未找到 dispatch_actions 字段")
            print(f"[JSON解析] ========== 解析失败 ==========\n")
            return {}
    except Exception as e:
        print(f"[JSON解析] ❌ 解析异常: {e}")
        print(f"[JSON解析] ========== 解析失败 ==========\n")
        return {}


def _extract_json_from_text(text: str) -> dict:
    """从文本中提取 JSON 对象。"""
    cleaned = text.strip()

    # 处理 markdown 代码块
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```"):
                if in_block:
                    break
                in_block = True
                continue
            if in_block:
                json_lines.append(line)
        if json_lines:
            cleaned = "\n".join(json_lines).strip()

    # 查找 JSON 对象
    start = cleaned.find("{")
    if start < 0:
        return None

    # 尝试直接解析
    try:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(cleaned, start)
        return obj
    except json.JSONDecodeError:
        pass

    # 尝试修复截断的 JSON
    json_str = cleaned[start:]
    fixed = _fix_truncated_json(json_str)
    try:
        decoder2 = json.JSONDecoder()
        obj2, _ = decoder2.raw_decode(fixed, 0)
        return obj2
    except json.JSONDecodeError:
        pass

    return None


def create_insight_agent(skills_path: str = None):
    """创建洞察子代理。

    使用 deepagents create_deep_agent() 创建独立的洞察子代理，
    加载 SKILL.md 作为 system prompt。
    必须传入 model，失败直接抛异常，无降级。

    Args:
        skills_path: Skill 文件路径，默认为 './src/insight_agent/insight-skill/'

    Returns:
        洞察子代理实例
    """
    import time
    from datetime import datetime

    start = time.time()
    print(f"[洞察代理] [{datetime.now().strftime('%H:%M:%S')}] 开始创建子代理...")

    # 步骤1: 导入
    t1 = time.time()
    print(
        f"[洞察代理] [{datetime.now().strftime('%H:%M:%S')}] 步骤1/4: 导入 deepagents..."
    )
    from deepagents import create_deep_agent

    print(
        f"[洞察代理] [{datetime.now().strftime('%H:%M:%S')}] 步骤1/4 完成 ({time.time()-t1:.1f}s)"
    )

    # 步骤2: 获取 LLM
    t2 = time.time()
    print(f"[洞察代理] [{datetime.now().strftime('%H:%M:%S')}] 步骤2/4: 获取 LLM...")
    from src.config.settings import get_llm

    print(
        f"[洞察代理] [{datetime.now().strftime('%H:%M:%S')}] 步骤2/4: 调用 get_llm()..."
    )
    llm = get_llm()
    print(
        f"[洞察代理] [{datetime.now().strftime('%H:%M:%S')}] 步骤2/4 完成 ({time.time()-t2:.1f}s)"
    )

    # 步骤3: 准备 skills
    t3 = time.time()
    if skills_path is None:
        skills_path = "./src/insight_agent/insight-skill/"
    print(f"[洞察代理] [{datetime.now().strftime('%H:%M:%S')}] 步骤3/4: 准备 skills...")
    print(
        f"[洞察代理] [{datetime.now().strftime('%H:%M:%S')}] 步骤3/4 完成 ({time.time()-t3:.1f}s)"
    )

    # 步骤4: 创建 agent（最耗时）
    t4 = time.time()
    print(
        f"[洞察代理] [{datetime.now().strftime('%H:%M:%S')}] 步骤4/4: 调用 create_deep_agent()..."
    )
    agent = create_deep_agent(
        model=llm,
        skills=[skills_path],
    )
    print(
        f"[洞察代理] [{datetime.now().strftime('%H:%M:%S')}] 步骤4/4 完成 ({time.time()-t4:.1f}s)"
    )

    print(
        f"[洞察代理] 子代理创建成功，技能路径: {skills_path}（总耗时: {time.time()-start:.1f}s）"
    )
    return agent


def run_insight_agent(agent, prompt: str) -> dict:
    """运行洞察子代理并返回结果。

    Args:
        agent: 洞察子代理实例（CompiledStateGraph）
        prompt: 发送给子代理的 prompt

    Returns:
        解析后的 dict，包含 dispatch_actions
    """
    import time
    from langchain_core.messages import HumanMessage

    print(f"[洞察代理] 调用 agent.invoke()...")
    t_start = time.time()

    # deepagents 使用 HumanMessage 包装用户输入
    result = agent.invoke(
        {"messages": [HumanMessage(content=prompt)]},
        config={"configurable": {"thread_id": "insight-agent"}},
    )

    elapsed = time.time() - t_start
    print(f"[洞察代理] agent.invoke() 完成 ({elapsed:.1f}s)")
    # 提取返回结果中的 content / output（参考 src/main.py 第396-400行）
    response_text = ""
    if hasattr(result, "messages") and result.messages:
        last_msg = result.messages[-1]
        response_text = last_msg.content
    elif isinstance(result, dict) and "messages" in result:
        messages = result["messages"]
        if messages and hasattr(messages[-1], "content"):
            response_text = messages[-1].content
        elif messages and isinstance(messages[-1], dict):
            response_text = messages[-1].get("content", "")
    elif isinstance(result, dict):
        response_text = result.get("output") or result.get("content") or str(result)
    else:
        response_text = str(result)

    # 调试：打印子代理原始输出和解析结果
    print(f"[洞察代理] 子代理原始输出：{response_text}")
    result_dict = parse_json_from_response(response_text)
    print(
        f"[洞察代理] 解析结果：{json.dumps(result_dict, ensure_ascii=False, indent=2)[:500]}"
    )
    return result_dict


def generate_insight_with_retry(agent, prompt_data: str, max_retries: int = 3) -> tuple:
    """带重试机制的洞察生成。

    工作流程：
    1. 调用洞察子代理生成洞察
    2. 验证输出格式
    3. 如果验证失败，将错误描述发给子代理重试
    4. 重试耗尽后返回最终结果

    Args:
        agent: 洞察子代理实例
        prompt_data: 发送给子代理的 prompt 数据（已拼接好的完整 prompt）
        max_retries: 最大重试次数

    Returns:
        (result_dict, success_bool, errors_list)
        - result_dict: 解析后的 dispatch_actions
        - success_bool: 是否验证通过
        - errors_list: 错误信息列表
    """
    import time

    last_result = {}
    last_errors = []
    last_response = ""

    print(
        f"[洞察代理] [{time.strftime('%H:%M:%S')}] 开始生成洞察 (max_retries={max_retries})..."
    )
    total_start = time.time()

    for attempt in range(max_retries):
        attempt_start = time.time()
        print(
            f"[洞察代理] [{time.strftime('%H:%M:%S')}] 第{attempt+1}/{max_retries} 次调用..."
        )

        if attempt == 0:
            current_prompt = prompt_data
        else:
            error_msg = format_errors_as_guidance(last_errors)
            current_prompt = (
                f"【修正要求】\n{error_msg}\n"
                f"直接输出正确的 JSON，不要输出任何其他内容。"
            )

        last_result = run_insight_agent(agent, current_prompt)

        attempt_elapsed = time.time() - attempt_start
        print(
            f"[洞察代理] [{time.strftime('%H:%M:%S')}] 第{attempt+1}次调用完成 (耗时: {attempt_elapsed:.1f}s)"
        )

        last_errors = validate_insight_output(last_result)

        if not last_errors:
            print(f"[洞察代理] [{time.strftime('%H:%M:%S')}] 第{attempt+1}次验证通过")
            total_elapsed = time.time() - total_start
            print(
                f"[洞察代理] [{time.strftime('%H:%M:%S')}] 洞察生成总耗时: {total_elapsed:.1f}s"
            )
            return last_result, True, []

        print(
            f"[洞察代理] [{time.strftime('%H:%M:%S')}] 第{attempt+1}次验证失败: {last_errors}"
        )

    total_elapsed = time.time() - total_start
    print(
        f"[洞察代理] [{time.strftime('%H:%M:%S')}] 重试耗尽 (总耗时: {total_elapsed:.1f}s)，最终错误: {last_errors}"
    )
    return last_result, False, last_errors
