"""
SSC硅基生物系统 - 员工端配置

员工端与服务端分离部署，配置独立维护。
此文件定义员工端本地运行所需的所有配置项。
"""

# ==================== 服务端连接配置 ====================
# 支持通过环境变量 SSC_SERVER_URL 覆盖，方便局域网内其他用户连接
# 示例：set SSC_SERVER_URL=http://{{SSC_SERVER_HOST}}:8000 && python -m staff.terminal
import os

SERVER_URL = os.environ.get("SSC_SERVER_URL", "http://localhost:8000")

# ==================== 大模型配置 ====================
# 员工端 /skill 执行时，deepagents 需要直连内网大模型
# 普通聊天消息走服务端 API，不使用此配置
LLM_CONFIG = {
    "model": "model_name",
    "base_url": "LLM_API_URL",
    "temperature": 0,
    "max_tokens": 4096,
    "api_key": "LLM_API_KEY",
}

    "tracing": "true",
}
