"""
SSC硅基生物系统 - 全局配置
"""
from pathlib import Path
from langchain_openai import ChatOpenAI

# ==================== 路径配置 ====================
BASE_DIR = Path(__file__).resolve().parent.parent.parent
SRC_DIR = BASE_DIR / "src"
RAG_DIR = BASE_DIR / "RAG_files"
MEMORY_DIR = BASE_DIR / "memories"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "ssc_memory.db"
DB_DIR = BASE_DIR / "databases"
SKILLS_DIR = BASE_DIR / "skills"

# ==================== 大模型配置 ====================
LLM_CONFIG = {
    "model": "your_model_name",
    "base_url": "your_base_url_here",
    "temperature": 0,
    "max_tokens": 1024,
    "api_key": "your_api_key_here",
    "request_timeout": 120,
    "max_retries": 2,
}


class ToolCallFixChatOpenAI(ChatOpenAI):
    """修复非标准工具调用格式的 ChatOpenAI 封装
    
    MODEL_NAME 返回 tool_calls 时 args 可能是 list 而非 dict，
    需要在 langchain 验证前修正格式。
    """
    def _create_chat_result(self, response, generation_info=None):
        import json as _json
        try:
            for choice in getattr(response, 'choices', []):
                msg = getattr(choice, 'message', None)
                if msg and getattr(msg, 'tool_calls', None):
                    for tc in msg.tool_calls:
                        func = getattr(tc, 'function', None)
                        if func:
                            args = func.arguments
                            if isinstance(args, list):
                                if args and isinstance(args[0], dict):
                                    merged = {}
                                    for item in args:
                                        if isinstance(item, dict):
                                            merged.update(item)
                                    func.arguments = _json.dumps(merged, ensure_ascii=False)
                            elif isinstance(args, str):
                                try:
                                    parsed = _json.loads(args)
                                    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                                        merged = {}
                                        for item in parsed:
                                            if isinstance(item, dict):
                                                merged.update(item)
                                        func.arguments = _json.dumps(merged, ensure_ascii=False)
                                except (_json.JSONDecodeError, TypeError):
                                    pass
        except Exception:
            pass
        return super()._create_chat_result(response, generation_info)


def get_llm() -> ToolCallFixChatOpenAI:
    """获取带工具兼容补丁的大模型实例"""
    return ToolCallFixChatOpenAI(**LLM_CONFIG)


# ==================== 上行脊髓配置 ====================
ASCENDING_SPINE = {
    "heartbeat_interval_minutes": 30,  # 定时巡检间隔
    "ack_timeout_minutes": 5,          # ACK超时时间
}