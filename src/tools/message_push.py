"""
消息推送工具
下行脊髓通过此工具将结果推送给员工或SSC专员。
MVP阶段：打印到控制台（后续替换为企微/钉钉/邮件API）
"""
from langchain.tools import tool


@tool
def push_message(recipient: str, message: str, channel: str = "console") -> str:
    """向指定接收人推送消息通知。
    当需要向员工或SSC专员发送通知、回复、预警时使用。
    Args:
        recipient: 接收人标识（工号、姓名或邮箱）
        message: 消息内容
        channel: 推送渠道（console/webchat/email）
    """
    # MVP阶段：控制台输出
    print(f"\n{'='*50}")
    print(f"[消息推送] 渠道: {channel}")
    print(f"  收件人: {recipient}")
    print(f"  内容: {message}")
    print(f"{'='*50}\n")
    return f"消息已通过{channel}渠道发送给{recipient}。"