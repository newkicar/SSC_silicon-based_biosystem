"""
中枢神经节（Central Ganglion）——反射弧决策中心

角色：连接上行脊髓和下行脊髓的决策节点
核心职责：
  1. 接收上行脊髓的情报包
  2. 匹配已知的确定性模式（反射弧）
  3. 如果匹配成功 → 直接响应（不经过大脑）
  4. 如果匹配失败 → 传递给大脑做判断
"""
from src.spine.ascending import IntelligencePacket
from src.tools.knowledge_base import _search_in_documents


# 反射弧模式表：确定性查询的快速响应
REFLEX_PATTERNS = [
    # === 假期类 ===
    {
        "name": "年假查询",
        "keywords": ["年假", "年假几天", "还剩几天假", "剩余年假", "还有多少年假"],
        "requires_employee": True,
        "response_template": "根据系统记录，{name}当前剩余年假为{annual_leave_remaining}天。\n\n📌 政策依据：根据国家相关规定，法定年假按社会累计工作年限计算（1-10年：5天，10-20年：10天，20年以上：15天）。当年剩余年假可延期至次年3月31日，逾期未休自动作废。",
    },
    {
        "name": "婚假查询",
        "keywords": ["婚假", "结婚假", "婚假几天"],
        "requires_employee": False,
        "policy_search": "婚假",
    },
    {
        "name": "产假查询",
        "keywords": ["产假", "陪产假", "生育假", "产假多久"],
        "requires_employee": False,
        "policy_search": "产假",
    },
    {
        "name": "丧假查询",
        "keywords": ["丧假"],
        "requires_employee": False,
        "policy_search": "丧假",
    },
    {
        "name": "病假查询",
        "keywords": ["病假", "病假工资", "病假几天"],
        "requires_employee": False,
        "policy_search": "病假",
    },
    # === 薪酬社保类 ===
    {
        "name": "公积金查询",
        "keywords": ["公积金", "住房公积金", "公积金缴纳"],
        "requires_employee": False,
        "policy_search": "住房公积金",
    },
    {
        "name": "社会保险查询",
        "keywords": ["社会保险", "五险", "社保缴纳", "社保基数"],
        "requires_employee": False,
        "policy_search": "社会保险",
    },
    {
        "name": "工资发放查询",
        "keywords": ["工资什么时候发", "发工资", "发薪日", "几号发工资"],
        "requires_employee": False,
        "policy_search": "工资计算、发放方法",
    },
    {
        "name": "加班工资查询",
        "keywords": ["加班工资", "加班费", "加班怎么算"],
        "requires_employee": False,
        "policy_search": "加班工资",
    },
    # === 考勤类 ===
    {
        "name": "工作时间查询",
        "keywords": ["几点上班", "几点下班", "上班时间", "工作时间", "上下班"],
        "requires_employee": False,
        "policy_search": "工作时间规定",
    },
    {
        "name": "迟到早退查询",
        "keywords": ["迟到", "早退", "迟到扣钱"],
        "requires_employee": False,
        "policy_search": "迟到、早退、旷工",
    },
    {
        "name": "漏打卡查询",
        "keywords": ["漏打卡", "忘记打卡", "漏刷卡", "补卡"],
        "requires_employee": False,
        "policy_search": "漏刷卡",
    },
    # === 入离职类 ===
    {
        "name": "离职手续查询",
        "keywords": ["离职", "辞职", "离职手续", "怎么离职"],
        "requires_employee": False,
        "policy_search": "离职",
    },
    {
        "name": "试用期查询",
        "keywords": ["试用期", "试用期多久", "转正"],
        "requires_employee": False,
        "policy_search": "试用期规定",
    },
    # === 晋升培训类 ===
    {
        "name": "晋升机制查询",
        "keywords": ["晋升", "升职", "怎么晋升"],
        "requires_employee": False,
        "policy_search": "晋升机制",
    },
    {
        "name": "培训查询",
        "keywords": ["培训", "培训计划"],
        "requires_employee": False,
        "policy_search": "培训",
    },
]


class ReflexResult:
    """反射弧处理结果"""

    def __init__(self, handled: bool, response: str = "", forward_to_brain: bool = False):
        self.handled = handled
        self.response = response
        self.forward_to_brain = forward_to_brain

    def __repr__(self):
        if self.handled:
            return f"ReflexResult(handled=True, response='{self.response[:50]}...')"
        return f"ReflexResult(handled=False, forward_to_brain={self.forward_to_brain})"


def try_reflex(packet: IntelligencePacket) -> ReflexResult:
    """
    尝试用反射弧处理情报包。
    如果匹配到已知的确定性模式，直接返回结果。
    如果不匹配，标记需要传递给大脑。
    """
    text = packet.raw_content

    for pattern in REFLEX_PATTERNS:
        # 检查关键词匹配
        matched = any(kw in text for kw in pattern["keywords"])
        if not matched:
            continue

        # 如果需要员工数据但没有，不能用反射弧
        if pattern.get("requires_employee") and not packet.employee_profile:
            continue

        # 如果有政策搜索需求
        if pattern.get("policy_search"):
            policy_result = _search_in_documents(pattern["policy_search"])
            if policy_result and "未找到" not in policy_result:
                # 质量检查：如果返回内容主要是目录/标题（短行占比>70%），放弃反射弧，转大脑
                lines = [l for l in policy_result.split('\n') if l.strip() and not l.startswith('【') and not l.startswith('---')]
                short_lines = sum(1 for l in lines if len(l.strip()) < 25)
                if len(lines) > 3 and short_lines / len(lines) > 0.7:
                    continue  # RAG结果质量低，跳过此模式，尝试下一个或转大脑
                return ReflexResult(
                    handled=True,
                    response=f"关于{pattern['policy_search']}的政策信息：\n{policy_result}",
                )

        # 如果有模板响应
        if pattern.get("response_template") and packet.employee_profile:
            try:
                response = pattern["response_template"].format(**packet.employee_profile)
                return ReflexResult(handled=True, response=response)
            except KeyError:
                # 员工档案缺少模板所需字段（如real roster没有annual_leave_remaining），跳过反射弧，交给大脑处理
                continue

    # 没有匹配到反射弧模式，交给大脑
    return ReflexResult(handled=False, forward_to_brain=True)