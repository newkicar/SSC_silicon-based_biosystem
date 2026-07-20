"""洞察通知语义查重模块

使用 LLM 对洞察通知进行语义相似度比较，判断是否为重复通知。
遵循 00-core.md 设计规范：
- 配置外置：阈值、权重从 config 读取
- 参数化 SQL：禁止字符串拼接
- 单一职责：每个函数只做一件事
"""

import json
from src.config.insight_dedup import DUPLICATE_THRESHOLD, WEIGHTS
from src.config.settings import get_llm


def calculate_similarity(
    new_title,
    new_content,
    new_summary,
    old_records,
):
    """计算新洞察与历史记录的语义相似度

    Args:
        new_title: 新洞察标题
        new_content: 新洞察内容
        new_summary: 新洞察AI总结
        old_records: 历史记录列表，每项包含 title/content/summary 等

    Returns:
        相似度得分列表，每项为 (record_id, score, details)
        score >= DUPLICATE_THRESHOLD 视为重复
    """
    llm = get_llm()

    # 构建简化的历史记录列表，只包含关键字段
    simplified_records = []
    for rec in old_records:
        simplified_records.append(
            {
                "id": rec.get("id"),
                "title": rec.get("title", ""),
                "summary": rec.get("summary", ""),
                "content": rec.get("content", "")[:100],  # 截断内容避免token过多
            }
        )

    topic_weight = WEIGHTS["topic"]
    data_weight = WEIGHTS["data"]
    org_weight = WEIGHTS["org"]
    action_weight = WEIGHTS["action"]

    prompt = f"""你是一个通知查重助手。请比较以下新通知与历史通知的相似度。

## 新通知
标题: {new_title}
总结: {new_summary}

## 历史通知列表
{json.dumps(simplified_records, ensure_ascii=False, indent=2)}

## 打分规则
请按以下维度打分（0-100分）：
1. 主题一致性（权重{topic_weight}）：是否说的是同一件事、同一个部门、同一个指标
2. 数据相似性（权重{data_weight}）：涉及的数据/数值是否相同
3. 组织范围（权重{org_weight}）：是否针对同一组织/部门
4. 建议行动（权重{action_weight}）：是否需要相同的处理方式

## 输出格式
必须输出 JSON，格式如下：
{{
  "scores": [
    {{
      "id": 历史记录id,
      "score": 总分（0-100整数）,
      "topic_score": 主题得分,
      "data_score": 数据得分,
      "org_score": 组织得分,
      "action_score": 行动得分,
      "is_duplicate": true/false
    }}
  ]
}}

is_duplicate 判断标准：总分 >= {DUPLICATE_THRESHOLD} 则为 true
"""

    from langchain_core.messages import HumanMessage

    response = llm.invoke([HumanMessage(content=prompt)])
    response_text = response.content if hasattr(response, "content") else str(response)

    # 提取 JSON
    scores = _parse_similarity_result(response_text)
    return scores


def _parse_similarity_result(response_text):
    """解析查重结果"""
    # 尝试从 markdown 代码块中提取 JSON
    cleaned = response_text.strip()
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

    start = cleaned.find("{")
    if start >= 0:
        try:
            decoder = json.JSONDecoder()
            result = decoder.decode(cleaned[start:])
            return result.get("scores", [])
        except json.JSONDecodeError:
            pass

    return []


def check_is_duplicate(
    target_user,
    new_title,
    new_content,
    new_summary,
    recent_records,
):
    """检查是否为重复通知

    Args:
        target_user: 接收人工号
        new_title: 新洞察标题
        new_content: 新洞察内容
        new_summary: 新洞察AI总结
        recent_records: 该用户最近的洞察通知记录

    Returns:
        True 表示重复（不应发送），False 表示不重复（可以发送）
    """
    if not recent_records:
        print(f"[洞察查重] 无历史记录: target_user={target_user}")
        return False

    print(
        f"[洞察查重] 查询到 {len(recent_records)} 条历史记录: target_user={target_user}"
    )
    for rec in recent_records:
        print(
            f"  历史记录 id={rec.get('id')}, title={rec.get('title')}, summary={rec.get('summary')}"
        )

    print(f"[洞察查重] 新通知: title={new_title}, summary={new_summary}")

    scores = calculate_similarity(new_title, new_content, new_summary, recent_records)

    print(f"[洞察查重] LLM返回的评分结果: {json.dumps(scores, ensure_ascii=False)}")

    for score_info in scores:
        if score_info.get("is_duplicate", False):
            print(
                f"[洞察查重] 发现重复通知: target_user={target_user}, "
                f"score={score_info['score']}, "
                f"record_id={score_info['id']}"
            )
            return True

    print(f"[洞察查重] 无重复通知: target_user={target_user}")
    return False
