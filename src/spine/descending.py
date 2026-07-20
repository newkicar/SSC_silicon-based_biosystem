"""
下行脊髓（Descending Spinal Cord）——简化版（MVP）

角色：被动传令——将大脑的回复推送给员工/专员
核心职责（MVP简化版）：
  1. 接收大脑的任务指令（通过 task_bs 队列认领）
  2. 将指令翻译为具体的终端任务（task_st）
  3. 通过消息推送工具将结果发送给员工

关键约束：
  - 下行脊髓绝不自行做决策
  - 绝不修改大脑的指令意图
  - 如果指令模糊，向上报告而不是自己猜测
"""
import uuid
from datetime import datetime

from src.data.task_queue import (
    claim_task_bs,
    update_task_bs_status,
    insert_task_st,
    claim_task_st,
    update_task_st_status,
    get_child_tasks,
    are_all_child_tasks_completed,
    insert_event,
)


def generate_task_id(prefix: str = "BS") -> str:
    """生成唯一的任务ID"""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    return f"{prefix}-{ts}-{short_uuid}"


def translate_brain_decision(brain_task: dict) -> list[dict]:
    """
    将大脑的抽象指令翻译为具体的原子任务列表（MVP简化版）
    
    在完整版中，这里会有复杂的任务编排逻辑（并行/串行/条件）。
    MVP阶段：直接将大脑回复作为消息推送任务。
    """
    payload = brain_task.get("payload", {})
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)

    brain_response = payload.get("brain_response", "")
    original_inquiry = payload.get("original_inquiry", "")
    recipient = payload.get("recipient", "员工")

    # MVP阶段：单个消息推送任务
    sub_tasks = [
        {
            "target_terminal_type": "wecom",
            "payload": {
                "action": "push_reply",
                "recipient": recipient,
                "message": brain_response,
                "original_inquiry": original_inquiry,
            },
        }
    ]

    return sub_tasks


def process_descending_task(brain_task: dict) -> dict:
    """
    处理一个下行任务的完整流程（同步版本，用于MVP）
    
    流程：
    1. 认领大脑任务 (task_bs)
    2. 翻译为原子任务 (task_st)
    3. 执行原子任务（MVP中直接模拟执行）
    4. 更新状态
    
    返回处理结果
    """
    task_id = brain_task["task_id"]
    print(f"[下行脊髓] 认领任务 {task_id}，开始编排...")

    # 更新大脑任务状态为 IN_PROGRESS
    update_task_bs_status(task_id, "IN_PROGRESS")

    # 翻译为原子任务
    sub_tasks_spec = translate_brain_decision(brain_task)
    print(f"[下行脊髓] 已翻译为 {len(sub_tasks_spec)} 个原子任务")

    # 创建并执行子任务
    results = []
    for i, spec in enumerate(sub_tasks_spec):
        st_id = generate_task_id("ST")
        insert_task_st(
            task_id=st_id,
            parent_task_id=task_id,
            target_terminal_type=spec["target_terminal_type"],
            payload=spec["payload"],
        )
        print(f"[下行脊髓] 子任务 {st_id} 已写入 task_st（目标终端: {spec['target_terminal_type']}）")

        # MVP阶段：直接执行消息推送（模拟终端认领+执行）
        terminal_result = execute_terminal_task(spec["target_terminal_type"], spec["payload"])
        update_task_st_status(st_id, "COMPLETED", result=terminal_result)
        results.append(terminal_result)
        print(f"[下行脊髓] 子任务 {st_id} 执行完成")

    # 所有子任务完成，更新大脑任务状态
    update_task_bs_status(task_id, "COMPLETED", result={
        "sub_tasks_count": len(sub_tasks_spec),
        "all_completed": True,
        "results": results,
    })

    # 发布完成事件
    insert_event(
        event_id=generate_task_id("EVT"),
        event_type="task_completed",
        source="descending_spine",
        payload={
            "task_id": task_id,
            "sub_tasks_count": len(sub_tasks_spec),
        },
    )

    print(f"[下行脊髓] 任务 {task_id} 全部完成。")
    return {"task_id": task_id, "results": results}


def execute_terminal_task(terminal_type: str, payload: dict) -> dict:
    """
    MVP阶段的终端任务执行器（同步模拟）
    
    在完整版中，这里应该是终端轮询认领+ReAct执行。
    MVP阶段：直接调用消息推送工具模拟执行。
    """
    action = payload.get("action", "")

    if action == "push_reply":
        recipient = payload.get("recipient", "员工")
        message = payload.get("message", "")

        # MVP：控制台输出
        print(f"\n{'='*50}")
        print(f"[终端执行] 渠道: wecom | 收件人: {recipient}")
        print(f"[终端执行] 回复内容:")
        # 缩进显示回复内容
        for line in message.split("\n"):
            print(f"  {line}")
        print(f"{'='*50}\n")

        return {
            "status": "sent",
            "channel": "wecom",
            "recipient": recipient,
            "timestamp": datetime.now().isoformat(),
        }

    else:
        return {
            "status": "unknown_action",
            "action": action,
            "message": f"未识别的终端动作: {action}",
        }