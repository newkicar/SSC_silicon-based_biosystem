"""
知识库RAG工具（中枢调度工具）
上行脊髓和反射弧都通过此工具检索知识库。
知识库存储在 RAG_files/ 目录下，按文件类型和内容分类。
"""
from pathlib import Path
from langchain.tools import tool

from src.config.settings import RAG_DIR


def _load_all_documents() -> dict[str, str]:
    """加载RAG_files目录下所有文档"""
    docs = {}
    if not RAG_DIR.exists():
        return docs
    for f in RAG_DIR.iterdir():
        if f.is_file() and f.suffix in (".txt", ".md"):
            try:
                docs[f.name] = f.read_text(encoding="utf-8")
            except Exception:
                pass
    return docs


def _search_in_documents(query: str) -> str:
    """
    关键词匹配搜索，优先返回匹配位置之后的正文内容（而非目录）。
    改进：找到匹配后，返回匹配位置之后的800字符（即条文正文），
    而非匹配位置前后的片段（容易返回目录）。
    """
    docs = _load_all_documents()
    if not docs:
        return "知识库为空，未找到相关文档。"

    results = []
    query_lower = query.lower()
    for filename, content in docs.items():
        if query_lower in content.lower():
            # 提取匹配位置之后的正文内容（800字符）
            idx = content.lower().find(query_lower)
            # 从匹配位置开始，跳过标题行，取正文
            start = idx
            end = min(len(content), idx + 800)
            snippet = content[start:end].strip()
            # 如果结果主要是标题/目录（行数多但每行很短），尝试扩大范围
            lines = snippet.split('\n')
            short_lines = sum(1 for l in lines if len(l.strip()) < 20)
            if len(lines) > 5 and short_lines / len(lines) > 0.7:
                # 大部分是短行（目录），扩大检索范围到匹配位置后1500字符
                end = min(len(content), idx + 1500)
                snippet = content[start:end].strip()
            results.append(f"【{filename}】\n{snippet}\n")

    if not results:
        return f"未找到与'{query}'直接相关的内容。建议尝试其他关键词或查阅完整文档。"

    return "\n---\n".join(results[:3])  # 最多返回3条，减少噪音


@tool
def search_knowledge_base(query: str) -> str:
    """从SSC知识库中检索相关政策、SOP、制度文档。
    当需要查询政策条文、操作流程、制度规定时使用此工具。
    Args:
        query: 搜索关键词或问题描述
    """
    return _search_in_documents(query)