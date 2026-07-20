"""
中枢神经节（Central Ganglion）——反射弧预检索

角色：连接上行脊髓与大脑的决策节点。

职责：将上行脊髓（src/spine/ascending.py）已预取的政策参考
     （packet.policy_references）整理为反射弧上下文，供 main.py
     注入大脑提示词作为「参考」。

设计要点（ponytail：删除优于堆砌）：
  - 政策 RAG 检索已由上行脊髓完成（packet.policy_references），
    本模块**不重复检索**，避免与上行脊髓 / 大脑 search_policy 三重冗余。
  - 原 REFLEX_PATTERNS 硬编码表（§3.2 泛化原则违规）、
    requires_employee / response_template 死分支（档案无对应字段永不命中）、
    legacy knowledge_base 导入、short_lines 质量启发式——均已删除。
  - 大脑始终是最终决策者（反射弧仅提供参考，不替代大脑）。
"""
from src.spine.ascending import IntelligencePacket


class ReflexResult:
    """反射弧处理结果。"""

    def __init__(self, handled: bool, response: str = "", forward_to_brain: bool = True):
        self.handled = handled
        self.response = response
        self.forward_to_brain = forward_to_brain

    def __repr__(self):
        if self.handled:
            return f"ReflexResult(handled=True, response='{self.response[:50]}...')"
        return f"ReflexResult(handled=False, forward_to_brain={self.forward_to_brain})"


def try_reflex(packet: IntelligencePacket) -> ReflexResult:
    """
    尝试用反射弧为大脑提供政策参考上下文。

    不做任何 RAG 检索——packet.policy_references 已由上行脊髓
    填充（含政策文档片段与显式工号查询结果）。本函数仅做
    可用性判断与格式化，无命中则直接交还大脑决策。
    """
    policy = (packet.policy_references or "").strip()
    if not policy:
        return ReflexResult(handled=False, forward_to_brain=True)
    return ReflexResult(handled=True, response=policy)
