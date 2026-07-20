"""
组织架构路由模块

根据洞察的 insight_level + insight_org + insight_type，
结合组织架构 Excel 文件 + 用户数据库，自动匹配通知接收人。

不依赖大脑输出具体用户名，避免人员变动导致代码失效。
"""

import pandas as pd
import re
from pathlib import Path

# 组织架构路径
ORG_XLSX_PATH = (
    Path(__file__).parent.parent.parent / "databases" / "元数据-公司组织架构.xlsx"
)

# 缓存组织架构数据
_org_cache = None


def load_org_structure() -> pd.DataFrame:
    """加载组织架构 Excel 文件，返回 DataFrame"""
    global _org_cache
    if _org_cache is not None:
        return _org_cache

    try:
        df = pd.read_excel(ORG_XLSX_PATH)
        _org_cache = df
        return df
    except Exception as e:
        print(f"[组织架构] 加载失败: {e}")
        return pd.DataFrame(columns=["公司", "中心", "部门"])


def build_org_hierarchy() -> dict:
    """
    构建组织架构树：公司 → 中心 → 部门
    返回嵌套字典结构
    """
    df = load_org_structure()
    hierarchy = {}

    for _, row in df.iterrows():
        company = row["公司"]
        center = row["中心"]
        dept = row["部门"]

        if company not in hierarchy:
            hierarchy[company] = {}
        if center not in hierarchy[company]:
            hierarchy[company][center] = []
        if dept not in hierarchy[company][center]:
            hierarchy[company][center].append(dept)

    return hierarchy


def get_all_companies() -> list:
    """获取所有公司名称列表"""
    df = load_org_structure()
    return sorted(df["公司"].unique().tolist())


def get_all_centers(company: str = None) -> list:
    """获取所有中心列表，可按公司过滤"""
    df = load_org_structure()
    if company:
        centers = df[df["公司"] == company]["中心"].unique().tolist()
    else:
        centers = df["中心"].unique().tolist()
    return sorted(centers)


def get_all_depts(company: str = None, center: str = None) -> list:
    """获取所有部门列表，可按公司和中心过滤"""
    df = load_org_structure()
    filtered = df
    if company:
        filtered = filtered[filtered["公司"] == company]
    if center:
        filtered = filtered[filtered["中心"] == center]
    depts = filtered["部门"].unique().tolist()
    return sorted(depts)


def get_company_by_center(center: str) -> str:
    """根据中心名称反查所属公司"""
    df = load_org_structure()
    matches = df[df["中心"] == center]
    if len(matches) > 0:
        return matches.iloc[0]["公司"]
    return ""


def get_company_by_dept(dept: str) -> str:
    """根据部门名称反查所属公司"""
    df = load_org_structure()
    matches = df[df["部门"] == dept]
    if len(matches) > 0:
        return matches.iloc[0]["公司"]
    return ""


def get_center_by_dept(dept: str) -> str:
    """根据部门名称反查所属中心"""
    df = load_org_structure()
    matches = df[df["部门"] == dept]
    if len(matches) > 0:
        return matches.iloc[0]["中心"]
    return ""


def normalize_org_name(name: str) -> str:
    """标准化组织名称，去除常见变体"""
    if not name:
        return ""
    # 去除空格
    name = name.strip()
    # 标准化"制造一中心"等
    name = re.sub(r"制造[一二]中心", lambda m: f"制造{m.group()[-2:-1]}中心", name)
    return name


def infer_insight_scope(insight_level: str, insight_org: str) -> dict:
    """
    根据洞察级别和组织名称，推断完整的作用范围。

    Returns:
        {"company": "虚拟公司A", "center": "虚拟中心", "dept": "虚拟部门"}
    """
    result = {"company": "", "center": "", "dept": ""}

    if not insight_level or not insight_org:
        return result

    # 公司级：无具体组织
    if insight_level == "company":
        result["company"] = insight_org if insight_org else ""
        return result

    # 中心级
    if insight_level == "center":
        result["center"] = insight_org
        result["company"] = get_company_by_center(insight_org)
        return result

    # 部门级
    if insight_level == "department":
        result["dept"] = insight_org
        result["center"] = get_center_by_dept(insight_org)
        result["company"] = get_company_by_dept(insight_org)
        return result

    return result


def match_insight_type_to_specialization(insight_type: str) -> list:
    """
    根据洞察类型，返回匹配的 specialization 关键词列表。

    Args:
        insight_type: cost / attendance / headcount / er / hris

    Returns:
        ["薪酬", "人力成本"] 等 specialization 关键词
    """
    mapping = {
        "cost": ["薪酬", "薪资", "人工成本", "人力成本"],
        "attendance": ["考勤", "加班", "出勤", "排班"],
        "headcount": ["招聘", "入离职", "编制", "HC", "离职"],
        "er": ["员工关系", "合同", "社保", "公积金"],
        "hris": ["HRIS", "系统", "数据", "信息化"],
    }
    return mapping.get(insight_type, [])


def resolve_notification_targets_v2(
    insight_type: str = "",
    insight_level: str = "",
    insight_org: str = "",
    user_context: dict = None,
) -> list:
    """
    基于组织架构的精准路由函数（V2 版本）。

    不再依赖大脑输出 target_user，而是：
    1. 大脑只输出 insight_level + insight_org + insight_type
    2. 代码根据组织架构匹配接收人

    Args:
        insight_type: cost / attendance / headcount / er / hris
        insight_level: company / center / department
        insight_org: 公司名称（公司级）/ 中心名称（中心级）/ 部门名称（部门级）
        user_context: 用户上下文（当前遍历的用户）

    Returns:
        应接收此通知的用户名列表
    """
    ctx = user_context or {}
    role = ctx.get("role", "")
    org = ctx.get("org", "")
    org_level = ctx.get("org_level", "")
    username = ctx.get("username", "")
    specialization = ctx.get("specialization", "")

    if not username:
        return []

    # === 1. 管理者路由 ===

    # 公司级 → 总经理、副总经理
    if insight_level == "company":
        if role in ("总经理", "副总经理"):
            return [username]
        # SSC 经理接收所有公司级洞察
        if role == "HR_SSC学科经理":
            return [username]
        # HRIS 工程师接收系统类
        if role in ("HRIS工程师", "高级HRIS工程师") and insight_type == "hris":
            return [username]
        return []

    # 中心级 → 中心总监、HRBP
    if insight_level == "center":
        if role == "总监" and org == insight_org:
            return [username]
        if role == "HRBP" and org == insight_org:
            return [username]
        return []

    # 部门级 → 部门经理、中心总监、HRBP
    if insight_level == "department":
        if role == "经理" and org == insight_org:
            return [username]
        # 也推送给中心总监和HRBP
        center = get_center_by_dept(insight_org)
        if center:
            if role == "总监" and org == center:
                return [username]
            if role == "HRBP" and org == center:
                return [username]
        return []

    # === 2. SSC 路由 ===

    # SSC 经理接收所有 SSC 相关洞察
    if role == "HR_SSC学科经理":
        return [username]

    # HRIS 工程师接收系统/数据类
    if role in ("HRIS工程师", "高级HRIS工程师"):
        if insight_type == "hris":
            return [username]
        # 预算数据异常也推送给 HRIS
        if "预算" in insight_org or "编制为0" in insight_org:
            return [username]
        return []

    # SSC 操作层员工：按 specialization 匹配
    if specialization:
        keywords = match_insight_type_to_specialization(insight_type)
        if keywords:
            for kw in keywords:
                if kw.lower() in specialization.lower():
                    return [username]

    return []


def check_notification_dedup(
    title: str, insight_type: str, insight_level: str, insight_org: str
) -> bool:
    """
    检查当月是否已有语义相似的通知。

    使用 Jaccard 相似度计算中文分词后的文本重合度。
    相似度 >= 0.5 视为重复。

    Args:
        title: 通知标题
        insight_type: 洞察类型
        insight_level: 洞察级别
        insight_org: 组织名称

    Returns:
        True = 已存在（应去重）
        False = 不存在（可创建）
    """
    import sqlite3
    from datetime import datetime

    conn = sqlite3.connect(
        str(Path(__file__).parent.parent.parent / "data" / "auth.db")
    )
    cursor = conn.cursor()

    # 获取当月第一天
    now = datetime.now()
    month_start = now.strftime("%Y-%m-01")
    month_end = now.strftime("%Y-%m-%d")

    # 简单中文分词：按字符切分 + 提取双字词
    def tokenize(text: str) -> set:
        """简单的中文分词器：提取所有双字组合"""
        text = re.sub(r"[^\u4e00-\u9fff]", "", text)
        tokens = set()
        for i in range(len(text) - 1):
            tokens.add(text[i : i + 2])
        return tokens

    new_tokens = tokenize(title)
    if not new_tokens:
        new_tokens = set(title[:10])

    # 获取当月所有通知标题
    cursor.execute(
        """
        SELECT id, title FROM notifications 
        WHERE created_at >= ? AND created_at <= ?
        """,
        (f"{month_start} 00:00:00", f"{month_end} 23:59:59"),
    )
    rows = cursor.fetchall()
    conn.close()

    # 计算 Jaccard 相似度
    for row in rows:
        existing_title = row["title"] or ""
        existing_tokens = tokenize(existing_title)

        if not existing_tokens:
            continue

        # Jaccard 相似度 = 交集 / 并集
        intersection = new_tokens & existing_tokens
        union = new_tokens | existing_tokens

        if not union:
            continue

        similarity = len(intersection) / len(union)

        if similarity >= 0.5:
            return True  # 发现相似通知

    return False
