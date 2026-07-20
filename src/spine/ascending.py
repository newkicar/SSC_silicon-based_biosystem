"""
上行脊髓（Ascending Spinal Cord）——带主动对焦功能的感觉器官

角色：大脑的感官系统
核心职责：
  1. 接收各类输入事件
  2. 渠道分流的向量RAG搜索（语义检索，不用硬编码匹配）
  3. 对检索结果做LLM摘要（提取重点信息，不截断）
  4. 组装情报包，传递给大脑

原则：
  - 用户信息、用户消息、检索结果 → 全部用RAG语义检索+LLM理解
  - 身份识别、意图判断、权限检查、紧急度评估 → 全部交给大脑（它有工具和语义理解能力）
  - 死格式标记（如[渠道:web]前缀）→ 用字符串操作清理
"""
import re as _re
from datetime import datetime

from src.tools.vector_rag import vector_search_in_documents


class IntelligencePacket:
    """情报包——上行脊髓传递给大脑的信息单元"""

    def __init__(self):
        self.event_type = ""
        self.raw_content = ""
        self.timestamp = datetime.now().isoformat()
        self.policy_references = ""
        self.channel = ""
        # 保留向后兼容字段（main.py 中引用）
        self.urgency = "normal"
        self.requester_identity = ""
        self.enhanced_intent = ""
        self.employee_profile = None
        self.preliminary_judgment = {"complexity": "未知（交由大脑评估）"}

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "raw_content": self.raw_content,
            "timestamp": self.timestamp,
            "policy_references": self.policy_references,
            "channel": self.channel,
            "urgency": self.urgency,
        }

    def to_prompt(self) -> str:
        """将情报包格式化为可直接送入大脑的文本"""
        lines = [
            "========== 上行脊髓情报包 ==========",
            f"事件类型: {self.event_type}",
            f"时间: {self.timestamp}",
            f"渠道: {self.channel}",
            "",
            "【原始内容】",
            self.raw_content,
        ]

        if self.policy_references:
            lines.append("")
            lines.append("【RAG语义检索结果】（上行脊髓通过向量检索获取）")
            lines.append(self.policy_references)

        lines.append("")
        lines.append("========== 情报包结束 ==========")
        return "\n".join(lines)


# 死格式：渠道标记（固定结构 [渠道:web] / [渠道:cli]）
_CHANNEL_RE = _re.compile(r'\[渠道:(web|cli)\]')
_CHANNEL_PREFIX_RE = _re.compile(r'^\[渠道:(?:web|cli)\](?:\[安全规则\])?\s*')
_MARATHON_TAG_RE = _re.compile(r'^\[渠道:cli\]\[Marathon执行\]\s*\n*')


def _detect_channel(raw_message: str) -> str:
    """判断渠道（死格式标记，用正则匹配）"""
    m = _CHANNEL_RE.search(raw_message)
    return m.group(1) if m else "cli"


def _clean_message(raw_message: str) -> str:
    """清理渠道标记等死格式前缀（用正则）"""
    clean = _MARATHON_TAG_RE.sub('', raw_message)
    clean = _CHANNEL_PREFIX_RE.sub('', clean)
    return clean.strip()


def _rag_search(query_text: str, channel: str) -> str:
    """
    通过RAG向量语义检索获取相关数据。
    - Web端：只搜RAG政策文档（不返回个人信息）
    - CLI端：联合搜索（RAG政策 + databases/Excel数据）
    """
    if channel == "web":
        result = vector_search_in_documents(query_text)
        return result if result and "未找到" not in result else ""
    else:
        from src.tools.vector_rag import search_combined
        result = search_combined(query_text, top_k=5, min_score=0.3, max_total_chars=8000)
        if result:
            print(f"[上行脊髓] RAG联合检索完成（{len(result)}字符）")
            return result
        else:
            print("[上行脊髓] RAG联合检索无结果")
            return ""


def process_employee_inquiry(raw_message: str, requester_id: str = "", requester_name: str = "") -> IntelligencePacket:
    """
    处理员工咨询事件——上行脊髓的核心流程。

    只做两件事：
    1. RAG向量语义检索（获取相关政策和数据）
    2. 组装情报包传给大脑

    以下全部交给大脑通过语义理解处理：
    - 身份识别（大脑知道用户是谁，executor已注入）
    - 意图理解（大脑的语义理解能力）
    - 权限检查（大脑的system prompt已有规则）
    - 紧急度评估（大脑判断）
    - 员工档案查询（大脑有query_employee_roster工具）

    参数:
        raw_message: 原始消息文本
        requester_id: 显式传入的请求者工号（Marathon等场景）
        requester_name: 显式传入的请求者姓名
    """
    packet = IntelligencePacket()
    packet.event_type = "employee_inquiry"
    packet.raw_content = raw_message

    # ---- 1. 渠道判断（死格式标记）----
    channel = _detect_channel(raw_message)
    packet.channel = channel

    # ---- 2. 清理死格式前缀，提取纯查询文本 ----
    clean_text = _clean_message(raw_message)

    # ---- 3. RAG向量语义检索 ----
    query_text = clean_text if clean_text else raw_message
    search_result = _rag_search(query_text, channel)
    if search_result:
        packet.policy_references = search_result

    # ---- 4. 如果有显式身份，查询员工花名册（精确查库，不是从文本猜）----
    if requester_id:
        try:
            from src.tools.data_sources import get_secretary
            secretary = get_secretary()
            if requester_id:
                detail = secretary.roster.get_employee_detail(requester_id)
                if detail:
                    packet.policy_references = f"---【员工档案（显式工号查询）】---\n{detail}\n\n{packet.policy_references}"
        except Exception:
            pass

    return packet