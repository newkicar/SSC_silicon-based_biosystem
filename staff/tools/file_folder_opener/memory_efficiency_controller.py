"""验证filepath_record.txt文件中的路径是否有效，把无效和路径列出一个列表，让用户输入编号进行删除"""

import sys
import os
import pandas as pd
import re
from collections import Counter

# 统一文件路径处理（兼容打包环境）
def get_file_folder_config_path(filename: str) -> str:
    """获取配置文件路径（兼容打包环境）"""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        return os.path.join(exe_dir, "resources", "file_folder_opener", filename)
    else:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

MEMORY_FILE_PATH = get_file_folder_config_path("filepath_record.txt")

# 计算项目根目录路径
current_dir = os.path.dirname(__file__)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.insert(0, project_root)

from typing import Literal

from langgraph.graph import StateGraph, START, END
from langchain.agents import AgentState
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command


class EfficiencyState(AgentState):
    """效率状态"""

    invalid_paths: list[str]
    human_choice: list[str]


def validate_memory_paths(state: EfficiencyState) -> EfficiencyState:
    """验证filepath_record.txt文件中的路径是否有效"""
    print("Subagent reports：正在验证filepath_record.txt文件中的路径是否有效")
    invalid_paths = []
    try:
        # 读取filepath_record.txt文件
        with open(MEMORY_FILE_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

            # 统计每个路径的出现次数
            path_counter = Counter()
            for line in lines:
                line_stripped = line.strip()
                if line_stripped and "|" in line_stripped:
                    path = line_stripped.split("|")[1]
                    path_counter[path] += 1

            # 处理每一行
            for line in lines:
                line = line.strip()
                if line and "|" in line:
                    path = line.split("|")[1]
                    if not os.path.exists(path):
                        invalid_paths.append(path)
                    if path_counter[path] > 1:  # 检查路径是否重复
                        invalid_paths.append(path)

                    
    except FileNotFoundError:
        print(f"Subagent reports：错误：找不到文件 {MEMORY_FILE_PATH}")
    except Exception as e:
        print(f"Subagent reports：读取文件时出错：{e}")
    return {"invalid_paths": invalid_paths}


def human_decide(state: EfficiencyState) -> EfficiencyState:
    """让用户输入编号进行删除"""
    invalid_paths = state.get("invalid_paths", [])

    # 检查是否有无效路径
    if not invalid_paths:
        print("Subagent reports：没有发现无效路径，无需删除。")
        return {
            "messages": [
                {"role": "assistant", "content": "没有发现无效路径，无需删除。"}
            ],
            "human_choice": [],
        }

    # 把invalid_paths转换成列表，并在前面标上编号
    invalid_paths_df = pd.DataFrame(
        {"编号": range(1, len(invalid_paths) + 1), "路径": invalid_paths}
    )

    file_nums = interrupt(
        {
            "prompt": "请根据表格选择要删除的路径编号，多个编号之间有“，”或“,”或“、”或“空格”分隔：",
            "form": invalid_paths_df.to_markdown(index=False),
        }
    )

    human_choices = []
    try:
        # 使用正则表达式一次性分割多种分隔符
        file_nums_list = re.split(r"[,，、\s]+", file_nums)
        for file_num in file_nums_list:
            file_num = file_num.strip()
            if file_num:
                num = int(file_num)
                if 1 <= num <= len(invalid_paths):
                    if file_num not in human_choices:  # 避免重复添加
                        human_choices.append(file_num)
                else:
                    print(f"Subagent reports：有超范围的编号，超出的编号为：{num}！")
                    return {
                        "messages": {
                            "role": "assistant",
                            "content": f"任务失败，用户输入错误！",
                        },
                        "human_choice": [],
                        "invalid_paths": [],
                    }
            else:
                print(f"Subagent reports：未输入编号，已中止验证并退回主程序！")
                return {
                    "messages": {
                        "role": "assistant",
                        "content": f"任务失败，用户输入错误！",
                    },
                    "human_choice": [],
                    "invalid_paths": [],
                }
    except ValueError:
        print("Subagent reports：输入错误，已中止验证并退回主程序！")
        return {
            "messages": {
                "role": "assistant",
                "content": f"任务失败，用户输入错误！",
            },
            "human_choice": [],
            "invalid_paths": [],
        }
    except Exception as e:
        print(f"Subagent reports：处理输入时出错：{e}，已中止验证并退回主程序！")
        return {
            "messages": {
                "role": "assistant",
                "content": f"任务失败，处理输入时出错，已中止验证并退回主程序！",
            },
            "human_choice": [],
            "invalid_paths": [],
        }

    return {"human_choice": human_choices}


def execute_deletion(state: EfficiencyState) -> EfficiencyState:
    """执行删除操作"""
    human_choices = state.get("human_choice", [])
    invalid_paths = state.get("invalid_paths", [])

    # 检查是否有选择要删除的路径
    if not human_choices:
        print("Subagent reports：没有选择要删除的路径，程序已结束。")
        return {
            "messages": {
                "role": "assistant",
                "content": "任务失败，没有选择要删除的路径，程序已结束。",
            },
            "human_choice": [],
            "invalid_paths": [],
        }

    try:
        # 读取filepath_record.txt文件
        with open(MEMORY_FILE_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

        lines_to_keep = []
        for line in lines:
            line = line.strip()
            if line and "|" in line:
                path = line.split("|")[1]
                # 需要根据human_choices中的编号，匹配invalid_paths中的路径
                paths_to_delete = []
                for choice in human_choices:
                    try:
                        if choice.isdigit():
                            idx = int(choice) - 1
                            if 0 <= idx < len(invalid_paths):
                                paths_to_delete.append(invalid_paths[idx])
                    except Exception:
                        return {
                            "messages": {
                                "role": "assistant",
                                "content": "任务失败，处理输入时出错，已中止删除操作！",
                            },
                            "human_choice": [],
                            "invalid_paths": [],
                        }
                if path not in paths_to_delete:
                    lines_to_keep.append(line + "\n")

        # 写回文件
        with open(MEMORY_FILE_PATH, "w", encoding="utf-8") as f:
            f.writelines(lines_to_keep)

        print(f"Subagent reports：已成功删除 {len(human_choices)} 个无效路径！")
        return {
            "messages": {
                "role": "assistant",
                "content": f"任务完成，已成功删除 {len(human_choices)} 个无效路径！",
            },
            "human_choice": [],
            "invalid_paths": [],
        }
    except FileNotFoundError:
        print(f"Subagent reports：错误：找不到文件 {MEMORY_FILE_PATH}")
        return {
            "messages": {
                "role": "assistant",
                "content": f"任务失败，错误：找不到文件 {MEMORY_FILE_PATH}！",
            },
            "human_choice": [],
            "invalid_paths": [],
        }
    except Exception as e:
        print(f"Subagent reports：执行删除操作时出错：{e}")
        return {
            "messages": {
                "role": "assistant",
                "content": f"任务失败，执行删除操作时出错！",
            },
            "human_choice": [],
            "invalid_paths": [],
        }


def end_validation(state: EfficiencyState) -> Literal["execute_deletion", END]:
    """结束验证"""
    human_choices = state.get("human_choice", [])
    if human_choices:
        return "execute_deletion"
    else:
        return END


valid_graph = StateGraph(EfficiencyState)

valid_graph.add_node("validate_memory_paths", validate_memory_paths)
valid_graph.add_node("human_decide", human_decide)
valid_graph.add_node("execute_deletion", execute_deletion)

valid_graph.add_edge(START, "validate_memory_paths")
valid_graph.add_edge("validate_memory_paths", "human_decide")
valid_graph.add_conditional_edges(
    "human_decide",
    end_validation,
    ["execute_deletion", END],
)
valid_graph.add_edge("execute_deletion", END)

valid_graph = valid_graph.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "default"}}
    try:
        result = valid_graph.invoke(
            {
                "messages": [
                    {"role": "user", "content": "验证filepath_record.txt文件中的路径是否有效"}
                ]
            },
            config=config,
        )

        if result.get("__interrupt__"):
            # preference search断点
            try:
                print(result["__interrupt__"][0].value["prompt"])
                print(result["__interrupt__"][0].value["form"])
                decision = input("请输入：")
                result = valid_graph.invoke(Command(resume=decision), config=config)
            except Exception as e:
                print(f"处理中断时出错：{e}")
    except Exception as e:
        print(f"执行过程中出错：{e}")
