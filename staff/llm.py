"""
SSC员工端 - LLM 工具兼容层

[大模型名称] 返回工具调用时 args 可能是 list 而非 dict，
需要在 langchain 验证前修正格式。
"""
import json
from langchain_openai import ChatOpenAI


class ToolCallFixChatOpenAI(ChatOpenAI):
    """修复非标准工具调用格式的 ChatOpenAI 封装"""
    
    def _create_chat_result(self, response, generation_info=None):
        try:
            for choice in getattr(response, 'choices', []):
                msg = getattr(choice, 'message', None)
                if msg and getattr(msg, 'tool_calls', None):
                    for tc in msg.tool_calls:
                        func = getattr(tc, 'function', None)
                        if func:
                            args = func.arguments
                            # 处理 list 格式（OpenAI SDK 可能已解析为 list）
                            if isinstance(args, list):
                                if args and isinstance(args[0], dict):
                                    merged = {}
                                    for item in args:
                                        if isinstance(item, dict):
                                            merged.update(item)
                                    func.arguments = json.dumps(merged, ensure_ascii=False)
                            # 处理 JSON 字符串格式
                            elif isinstance(args, str):
                                try:
                                    parsed = json.loads(args)
                                    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                                        merged = {}
                                        for item in parsed:
                                            if isinstance(item, dict):
                                                merged.update(item)
                                        func.arguments = json.dumps(merged, ensure_ascii=False)
                                except (json.JSONDecodeError, TypeError):
                                    pass
        except Exception:
            pass
        
        return super()._create_chat_result(response, generation_info)


def get_llm(config: dict = None) -> ToolCallFixChatOpenAI:
    """获取带工具兼容补丁的 LLM 实例"""
    from staff.settings import LLM_CONFIG
    cfg = config or LLM_CONFIG
    return ToolCallFixChatOpenAI(**cfg)