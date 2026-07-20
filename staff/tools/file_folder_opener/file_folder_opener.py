# 【版本标记】v2.0 - 2026-04-24 - 移除 interrupt() 调用，改为返回 JSON 消息
import sys
import os
import json
from typing import Literal
import pandas as pd
import re
from pathlib import Path

# .env 加载已移至 path_adapter.init_data_dirs() 统一处理，此处移除避免重复加载
from langchain_openai import ChatOpenAI

# 路径适配：使用 path_adapter 统一处理打包环境路径
# 🔴 修改：使用当前项目路径
_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent.parent.parent  # staff/tools/file_folder_opener -> project root

project_root = str(_project_root)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def get_file_folder_config_path(filename: str) -> str:
    """获取配置文件路径（基于当前文件目录）"""
    return str(_current_dir / filename)


# 环境变量已由 init_data_dirs() 加载

# 配置模型（与 thomas_agent.py 保持一致）
main_model = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL"),
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=float(os.getenv("OPENAI_TEMPERATURE", 0.0)),
)

from langgraph.graph import StateGraph, START, END
from langchain.agents import create_agent, AgentState
from langchain.agents.middleware import LLMToolSelectorMiddleware
from langgraph.checkpoint.memory import InMemorySaver
from langchain.tools import tool
from langgraph.types import interrupt, Command


class SubAgentState(AgentState):
    file_path: str
    file_keywords: list[str]
    total_path: list[str]
    human_decision: str
    control_type: str


@tool
def extract_file_info(file_path: str, file_keywords: list[str]) -> dict:
    """
    保存文件信息工具，将提取到的文件路径和关键词保存到状态中。
    Args:
        file_path (str): 提取到的文件路径
        file_keywords (list[str]): 提取到的文件关键词列表
    Returns:
        dict: 包含ToolMessage和状态更新的字典
    """

    # 创建状态更新字典
    state_update = {
        "file_path": file_path,
        "file_keywords": file_keywords,
        "total_path": [],
        "human_decision": "",
        "control_type": "",
    }

    return state_update


# 状态更新节点
def update_state_from_tool_result(state: SubAgentState) -> SubAgentState:
    """
    从Agent的工具调用结果中更新状态
    这是关键节点：将工具结果应用到状态中
    """
    # 查找最新的工具消息并转换为字典
    try:
        tool_dict = json.loads(state["messages"][-2].content)
        print(f"🔧 [update_state_from_tool_result] 工具调用结果: {tool_dict}")
        # 创建状态更新字典
        state_update = {
            "file_path": tool_dict.get("file_path", "").lower(),
            "file_keywords": tool_dict.get("file_keywords", []),
            "total_path": tool_dict.get("total_path", []),
            "human_decision": tool_dict.get("human_decision", "").lower(),
            "control_type": tool_dict.get("control_type", "").lower(),
        }
        print(
            f"🔧 [update_state_from_tool_result] 解析后: file_path='{state_update['file_path']}', file_keywords={state_update['file_keywords']}"
        )
    except Exception as e:
        print(f"⚠️ [update_state_from_tool_result] JSON解析失败: {e}")
        print(
            f"⚠️ [update_state_from_tool_result] 消息内容: {state['messages'][-2].content if len(state.get('messages', [])) >= 2 else 'N/A'}"
        )
        # 从state["messages"][-1].content中获取""或''中的内容作为file_keywords,且只要引号里面的内容
        # 匹配单引号、双引号或中文引号包围的内容
        file_keywords_match = re.search(
            r"['\u2018\u2019\"\u201c\u201d](.*?)['\u2018\u2019\"\u201c\u201d]",
            state["messages"][-1].content,
        )
        if file_keywords_match:
            state_update = {
                "file_path": "",
                "file_keywords": file_keywords_match.group(1).split(),
                "total_path": [],
                "human_decision": "",
                "control_type": "",
            }
            print(
                f"🔧 [update_state_from_tool_result] 正则解析关键词: {state_update['file_keywords']}"
            )
        else:
            print(f"⚠️ [update_state_from_tool_result] 正则解析也失败，返回空状态")
            state_update = {}
    return state_update


def search_by_direct_path(state: SubAgentState) -> SubAgentState:
    """第一层搜索：直接路径检查"""
    file_path = state.get("file_path", "")
    file_keywords = state.get("file_keywords", [])
    print(f"Subagent reports：正在使用您提供的路径 '{file_path}' 中进行搜索……")
    print(
        f"🔍 [search_by_direct_path] file_path='{file_path}', file_keywords={file_keywords}"
    )
    return {"control_type": "search_by_direct_path"}


def search_in_memory(state: SubAgentState) -> SubAgentState:
    """第二层搜索：在filepath_record.txt中搜索"""
    file_keywords = state.get("file_keywords", [])
    print(
        f"Subagent reports：正在filepath_record.txt中搜索已保存的文件路径，关键词为：{file_keywords}……"
    )
    if not file_keywords:
        print("⚠️ 未找到关键词，无法进行搜索")
        return state

    memory_file = get_file_folder_config_path("filepath_record.txt")
    if not os.path.exists(memory_file):
        return state

    with open(memory_file, "r", encoding="utf-8", errors="ignore") as f:
        total_path = []
        for line in f:
            line = line.strip()
            if "|" not in line:
                continue
            common_name, path = line.split("|", 1)
            for keyword in file_keywords:
                if keyword.lower() in common_name.lower() and os.path.exists(path):
                    total_path.append(path)
        return {"total_path": total_path, "control_type": "search_in_memory"}


def search_in_reference(state: SubAgentState, max_depth: int = 3) -> SubAgentState:
    """第三层搜索：在reference.txt路径中搜索（简化迭代版本）"""
    file_keywords = state.get("file_keywords", [])
    print(
        f"Subagent reports：正在reference.txt中搜索已保存的文件路径，关键词为：{file_keywords}……"
    )
    if not file_keywords:
        print("⚠️ 未找到关键词，无法进行搜索")
        return state

    reference_file = get_file_folder_config_path("filepath_preference.txt")
    if not os.path.exists(reference_file):
        return state

    found_paths = []
    with open(reference_file, "r", encoding="utf-8", errors="ignore") as f:
        base_paths = [line.strip() for line in f if line.strip()]

    from collections import deque

    # 🔧 简化：只用队列，不加额外检查
    queue = deque()
    for base_path in base_paths:
        if os.path.exists(base_path) and os.path.isdir(base_path):
            queue.append((base_path, 1))

    print(f"开始参考路径搜索，共 {len(queue)} 个根目录待搜索...")
    i = 0

    while queue:
        path, depth = queue.popleft()

        # 🔧 只保留必要的路径长度检查
        if len(path) > 240:
            continue

        i += 1
        if i % 5000 == 0:
            print(f"正在搜索参考路径：{path} (已搜索 {i} 个目录)")

        if depth > max_depth:
            continue

        try:
            items = os.listdir(path)

            for item in items:
                if item.startswith(".") or item.startswith("$"):
                    continue

                full_path = os.path.join(path, item)

                if len(full_path) > 240:
                    continue

                try:
                    if os.path.isdir(full_path):
                        # 🔧 修复：同时匹配文件夹名
                        for keyword in file_keywords:
                            if keyword.lower() in item.lower():
                                found_paths.append(full_path)
                                break
                        queue.append((full_path, depth + 1))
                    elif os.path.isfile(full_path):
                        for keyword in file_keywords:
                            if keyword.lower() in item.lower():
                                found_paths.append(full_path)
                                break
                except (PermissionError, OSError, FileNotFoundError):
                    continue
        except (PermissionError, OSError):
            continue

    print(
        f"\n✅ 参考路径搜索完成！共搜索 {i} 个目录，找到 {len(found_paths)} 个匹配文件"
    )
    return {"total_path": found_paths, "control_type": "search_in_reference"}


def search_globally(state: SubAgentState, max_depth: int = 5) -> SubAgentState:
    """第四层搜索：全局搜索（DFS版本，严格按顺序搜索，C盘最后）"""
    file_keywords = state.get("file_keywords", [])
    print(f"Subagent reports：正在全局搜索所有文件路径，关键词为：{file_keywords}……")
    if not file_keywords:
        print("⚠️ 未找到关键词，无法进行搜索")
        return state

    import string

    drives = []
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive):
            drives.append(drive)

    if "C:\\" in drives:
        drives.remove("C:\\")
        drives.append("C:\\")

    found_paths = []
    i = 0

    print(f"开始全局搜索，共 {len(drives)} 个磁盘待搜索...")
    print(f"磁盘搜索顺序: {drives}")

    def dfs_search(start_path, current_depth):
        nonlocal i

        if current_depth > max_depth:
            return

        try:
            items = os.listdir(start_path)

            for item in items:
                if item.startswith(".") or item.startswith("$"):
                    continue

                full_path = os.path.join(start_path, item)

                if len(full_path) > 240:
                    continue

                try:
                    if os.path.isdir(full_path):
                        i += 1
                        if i % 10000 == 0:
                            print(f"正在搜索路径：{full_path} (已搜索 {i} 个目录)")

                        if i % 30000 == 0:
                            whether_goon = input(
                                f"已搜索 {i} 个目录，是否还要继续等待？(y/n)"
                            )
                            if whether_goon.lower() != "y":
                                return True

                        # 🔧 修复：同时匹配文件夹名
                        for keyword in file_keywords:
                            if keyword.lower() in item.lower():
                                found_paths.append(full_path)
                                break

                        should_stop = dfs_search(full_path, current_depth + 1)
                        if should_stop:
                            return True

                    elif os.path.isfile(full_path):
                        for keyword in file_keywords:
                            if keyword.lower() in item.lower():
                                found_paths.append(full_path)
                                break
                except (PermissionError, OSError, FileNotFoundError):
                    continue
        except (PermissionError, OSError):
            pass

        return False

    for drive in drives:
        print(f"\n🔍 开始搜索磁盘: {drive}")
        should_stop = dfs_search(drive, 1)
        if should_stop:
            print("\n⚠️ 用户中断搜索")
            break

    print(f"\n✅ 全局搜索完成！共搜索 {i} 个目录，找到 {len(found_paths)} 个匹配文件")
    return {"total_path": found_paths, "control_type": "search_globally"}


def input_a_number(state: SubAgentState) -> SubAgentState:
    """偏好搜索和全局搜索时，可能会返回多个文件，所以需要用户输入编号以确认是哪个文件"""
    print("\n" + "=" * 80)
    print("🚨🚨🚨 [input_a_number] 节点被调用！ 🚨🚨🚨")
    print("=" * 80)

    total_paths = state.get("total_path", [])
    print(f"🔍 [input_a_number] 收到 total_paths: {total_paths}")
    print(f"🔍 [input_a_number] total_paths 类型: {type(total_paths)}")
    print(f" [input_a_number] total_paths 长度: {len(total_paths)}")

    if not total_paths:
        print("️  [input_a_number] total_paths 为空，返回原状态")
        return state

    # 【修改】使用 interrupt() 中断执行,但返回特殊格式的消息
    # 这样可以在 GUI 环境下正确显示文件选择对话框
        
    # 【修复】手动格式化表格,避免 pandas.to_markdown() 的 tabulate 版本检测问题
    def format_file_table(paths):
        """手动格式化文件列表为表格字符串"""
        if not paths:
            return "未找到文件"
            
        # 计算列宽
        num_width = max(len(str(i)) for i in range(1, len(paths) + 1))
        path_width = max(len(p) for p in paths)
            
        # 构建表头
        header = f"{'编号':<{num_width}}  {'路径':<{path_width}}"
        separator = "-" * len(header)
            
        # 构建表格行
        rows = [header, separator]
        for i, path in enumerate(paths, 1):
            rows.append(f"{i:<{num_width}}  {path:<{path_width}}")
            
        return "\n".join(rows)
        
    table_str = format_file_table(total_paths)
        
    # 返回特殊格式,GUI 客户端会识别并显示选择对话框
    file_list_json = json.dumps(
        {
            "type": "file_selection_required",
            "files": total_paths,
            "message": "找到多个文件,请选择要打开的文件编号:",
            "form": table_str,  # 使用手动格式化的表格
        },
        ensure_ascii=False,
    )
    
    print(f"\n📦 [input_a_number] 生成的 JSON: {file_list_json[:200]}...")
    print("=" * 80 + "\n")
    
    # 调用 interrupt() 中断执行,等待用户输入
    user_choice = interrupt(
        {
            "prompt": "请根据表格选择要打开的文件(夹)编号:",
            "form": table_str,
            "files": total_paths,  # 添加 files 字段供 GUI 客户端解析
            "json_data": file_list_json,  # 添加完整的 JSON 数据
        }
    )

    print(f"🔍 [input_a_number] 用户选择: {user_choice}")

    return {
        "total_path": total_paths,
        "human_decision": user_choice,
        "messages": [{"role": "assistant", "content": file_list_json}],
    }


def should_goto_global_search(state: SubAgentState) -> SubAgentState:
    """调用interrupt，让用户确认是否需要全局搜索"""
    # 【修复】使用 interrupt() 中断执行,等待用户确认
    confirm_json = json.dumps(
        {
            "type": "confirmation_required",
            "message": "即将进行全局搜索，这将耗费一些时间，是否继续？",
            "options": ["y", "n"],
        },
        ensure_ascii=False,
    )

    print(f"\n📦 [should_goto_global_search] 生成的 JSON: {confirm_json}")
    print("=" * 80 + "\n")

    # 调用 interrupt() 中断执行,等待用户输入
    user_choice = interrupt(
        {
            "prompt": "即将进行全局搜索，这将耗费一些时间，是否继续？",
            "options": ["y", "n"],
            "json_data": confirm_json,  # 添加完整的 JSON 数据供 GUI 客户端解析
        }
    )

    print(f"🔍 [should_goto_global_search] 用户选择: {user_choice}")

    return {
        "human_decision": user_choice,
        "messages": [{"role": "assistant", "content": confirm_json}],
    }


def save_to_memory(state: SubAgentState):
    """将关键词和路径保存到filepath_record.txt"""
    open_type = state.get("control_type", "")
    if (open_type in ["search_in_reference", "search_globally"]) and state.get(
        "total_path"
    ):
        file_path = state.get("total_path")
        file_keywords = state.get("file_keywords")
        human_choice = int(state.get("human_decision")) - 1
        memory_file = get_file_folder_config_path("filepath_record.txt")
        with open(memory_file, "a", encoding="utf-8", errors="ignore") as f:
            f.write(f"{file_keywords}|{file_path[human_choice]}\n")
            print(
                f"Subagent reports：关键词“{file_keywords}”和路径“{file_path[human_choice]}”已保存到filepath_record.txt"
            )


def file_open_tool(state: SubAgentState) -> SubAgentState:
    """根据SubAgentState中的total_path字段打开文件或文件夹"""

    open_type = state.get("control_type", "")
    paths_found = []
    if open_type == "search_by_direct_path":
        file_path = state.get("file_path", "")
        file_keywords = state.get("file_keywords", [])
        for keyword in file_keywords:
            # 读取file_path路径下的文件名称或文件夹名称
            if os.path.exists(file_path):
                for item in os.listdir(file_path):
                    if keyword in item:
                        total_path = os.path.join(file_path, item)
                        if os.path.exists(total_path):
                            os.startfile(total_path)
                            paths_found.append(total_path)
                            print(
                                f"Subagent reports：文件（夹）“{keyword}”已打开，完整路径为“{total_path}”"
                            )
        paths_str = " | ".join(paths_found) if paths_found else "未找到匹配文件"
        return {
            "messages": [
                {
                    "role": "assistant",
                    "content": f"任务完成，文件（夹）已打开，文件地址为{paths_str}",
                }
            ]
        }
    if open_type == "search_in_memory":
        total_path = state.get("total_path", [])
        for path in total_path:
            if os.path.exists(path):
                os.startfile(path)
                paths_found.append(path)
                print(f"Subagent reports：文件（夹）已打开，完整路径为“{path}”")
        paths_str = " | ".join(paths_found) if paths_found else "未找到匹配文件"
        return {
            "messages": [
                {
                    "role": "assistant",
                    "content": f"任务完成，文件（夹）已打开，文件地址为{paths_str}",
                }
            ]
        }
    if open_type in ["search_in_reference", "search_globally"] and state.get(
        "total_path"
    ):
        total_paths = state.get("total_path", [])
        human_decision = state.get("human_decision", "")
        if human_decision:
            try:
                total_path = total_paths[int(human_decision) - 1]
            except (ValueError, IndexError):
                return {
                    "messages": [
                        {
                            "role": "assistant",
                            "content": "运行失败，未能打开文件，请向用户确认。",
                        }
                    ]
                }
            if os.path.exists(total_path):
                os.startfile(total_path)
                paths_found.append(total_path)
                print(f"Subagent reports：文件（夹）已打开，完整路径为“{total_path}”")

                paths_str = " | ".join(paths_found) if paths_found else "未找到匹配文件"
                return {
                    "messages": [
                        {
                            "role": "assistant",
                            "content": f"任务完成，文件（夹）已打开，文件地址为{paths_str}",
                        }
                    ]
                }


# 路由后统一结果节点
def generate_search_result(state: SubAgentState) -> SubAgentState:
    """生成搜索结果消息"""
    total_paths = state.get("total_path", [])
    file_keywords = state.get("file_keywords", [])

    print(f"\n [generate_search_result] total_paths: {total_paths}")
    print(f"🔍 [generate_search_result] file_keywords: {file_keywords}")

    if total_paths:
        result = (
            f"已完成查找：找到{len(total_paths)}个关键字为 '{file_keywords}' 的文件，路径为：\n"
            + " | ".join(total_paths)
        )
        print(f"📝 [generate_search_result] 生成文本结果: {result[:200]}...")
        # if len(total_paths) > 5:
        #     result += f"\n... 还有 {len(total_paths)-5} 个"
    else:
        result = f"未找到关键字为 '{file_keywords}' 的文件"
        print(f"📝 [generate_search_result] 未找到文件")

    return {"messages": [{"role": "assistant", "content": result}]}


# 判断用户是否要求打开文件
def should_open_file(
    state: SubAgentState,
) -> Literal["file_open_tool", "save_to_memory", "generate_search_result"]:
    if (
        "打开" in state.get("messages", "")[0].content
        or "open" in state.get("messages", "")[0].content
    ):
        return "file_open_tool"
    else:
        if state.get("control_type", "") != "search_in_memory":
            return "save_to_memory"
        else:
            return "generate_search_result"


# 判断是否有 file_path
def route_after_file_agent(
    state: SubAgentState,
) -> Literal["search_by_direct_path", "search_in_memory"]:
    if state.get("file_path"):
        return "search_by_direct_path"
    else:
        return "search_in_memory"


# 判断记忆搜索后是否有 total_path
def route_after_memorysearch(
    state: SubAgentState,
) -> Literal[
    "file_open_tool", "save_to_memory", "search_in_reference", "generate_search_result"
]:
    # 这个路由函数会被复用在 memory_search 之后
    if state.get("total_path"):
        if (
            "打开" in state.get("messages", "")[0].content
            or "open" in state.get("messages", "")[0].content
        ):
            return "file_open_tool"
        else:
            if state.get("control_type", "") != "search_in_memory":
                return "save_to_memory"
            else:
                return "generate_search_result"
    else:
        # 如果记忆搜索没找到，继续进入偏好搜索
        return "search_in_reference"


def route_after_input_a_number(
    state: SubAgentState,
) -> Literal["file_open_tool", "save_to_memory", "generate_search_result"]:
    """处理 input_a_number 后的路由（此时 total_path 必定不为空）"""
    # 如果找到了文件，判断是打开还是保存
    if (
        "打开" in state.get("messages", "")[0].content
        or "open" in state.get("messages", "")[0].content
    ):
        return "file_open_tool"
    else:
        return "save_to_memory"


def should_global_search(
    state: SubAgentState,
) -> Literal["search_globally", "generate_search_result"]:
    if state.get("human_decision", "") == "y":
        return "search_globally"
    else:
        return "generate_search_result"


checkpointer = InMemorySaver()

SYSTEMPROMPT = """
你是一个工作好帮手，你的任务是根据用户的问题，调用工具来完成任务。
- 当用户需要打开文件、文件夹或运行程序时，调用extract_file_info工具
    - 其中参数file_path为要查找的路径，file_keywords为要查找的关键词列表
    - 你应该根据用户的问题，判断用户给出的路径和关键词：
        - 例一：user:在“d:\\uida0712\\Downloads”路径下打开文件“进一步达成”和“核心任务”，此时file_path为“d:\\uida0712\\Downloads\\”，file_keywords为[“进一步达成”，“核心任务”]；
        - 例二：user:打开文件夹“XX”->此时file_path为“”，file_keywords为[“XX”]；
        - 例三：user:打开文件“XX”->此时file_path为“”，file_keywords为[“XX”]；
    - **路径不是必须的**，当用户未给出路径时，file_path应为“”，你不要胡乱猜测路径；

关于返回值：
- 执行成功：返回"文件（夹）已打开，和完整路径“{total_path}”"
- 执行错误：返回"运行失败，未能打开文件，并告知原因。"
"""

file_agent = create_agent(
    name="file_agent",
    model=main_model,
    tools=[extract_file_info],
    system_prompt=SYSTEMPROMPT,
    middleware=[
        LLMToolSelectorMiddleware(
            model=main_model,
            always_include=["extract_file_info"],  # 始终包含某些工具
        )
    ],
    state_schema=SubAgentState,
    checkpointer=checkpointer,
)

file_agent_graph = StateGraph(SubAgentState)
file_agent_graph.add_node("file_agent", file_agent)
file_agent_graph.add_node(
    "update_state_from_tool_result", update_state_from_tool_result
)
file_agent_graph.add_node("search_by_direct_path", search_by_direct_path)
file_agent_graph.add_node("search_in_memory", search_in_memory)
file_agent_graph.add_node("search_in_reference", search_in_reference)
file_agent_graph.add_node("should_goto_global_search", should_goto_global_search)
file_agent_graph.add_node("search_globally", search_globally)
file_agent_graph.add_node("input_a_number", input_a_number)
file_agent_graph.add_node("save_to_memory", save_to_memory)
file_agent_graph.add_node("file_open_tool", file_open_tool)
file_agent_graph.add_node("generate_search_result", generate_search_result)

file_agent_graph.add_edge(START, "file_agent")
file_agent_graph.add_edge("file_agent", "update_state_from_tool_result")

# 判断：是否有直接路径，有的话直接通过路径搜索，然后打开文件，否则进入记忆搜索
file_agent_graph.add_conditional_edges(
    "update_state_from_tool_result",
    route_after_file_agent,  # 条件路由函数
    {
        "search_by_direct_path": "search_by_direct_path",
        "search_in_memory": "search_in_memory",
    },
)

# 设置直接路径搜索后的固定流向
file_agent_graph.add_conditional_edges(
    "search_by_direct_path",
    should_open_file,
    {
        "file_open_tool": "file_open_tool",
        "save_to_memory": "save_to_memory",
        "generate_search_result": "generate_search_result",
    },
)

# 处理记忆搜索后的分支 (对应图中 memory_search 后的判断)
file_agent_graph.add_conditional_edges(
    "search_in_memory",
    route_after_memorysearch,
    {
        "file_open_tool": "file_open_tool",
        "save_to_memory": "save_to_memory",
        "generate_search_result": "generate_search_result",
        "search_in_reference": "search_in_reference",
    },
)
file_agent_graph.add_edge("file_open_tool", END)

# 处理偏好搜索后的分支 (对应图中 search_in_reference 后的判断)
# 【修复】添加条件路由：如果 total_path 为空，直接进入全局搜索询问，跳过 input_a_number
file_agent_graph.add_conditional_edges(
    "search_in_reference",
    lambda state: "input_a_number" if state.get("total_path") else "should_goto_global_search",
    {
        "input_a_number": "input_a_number",
        "should_goto_global_search": "should_goto_global_search",
    },
)
file_agent_graph.add_conditional_edges(
    "input_a_number",
    route_after_input_a_number,
    {
        "file_open_tool": "file_open_tool",
        "save_to_memory": "save_to_memory",
        "generate_search_result": "generate_search_result",
    },
)

# 设置全局搜索后的流向
file_agent_graph.add_conditional_edges(
    "should_goto_global_search",
    should_global_search,
    {
        "search_globally": "search_globally",
        "generate_search_result": "generate_search_result",
    },
)
file_agent_graph.add_edge("search_globally", "input_a_number")
# 【移除】不再重复定义 input_a_number 的条件边，使用上面统一的 route_after_input_a_number
file_agent_graph.add_edge("file_open_tool", "save_to_memory")
file_agent_graph.add_edge("file_open_tool", END)
file_agent_graph.add_edge("save_to_memory", END)
file_agent_graph.add_edge("generate_search_result", END)

print("\n" + "=" * 80)
print("🔧 [file_folder_opener] 正在编译 file_folder_graph...")
print("📝 [file_folder_opener] 版本: v2.0 - 已移除 interrupt() 调用")
print("=" * 80 + "\n")

file_folder_graph = file_agent_graph.compile(checkpointer=checkpointer)

print("✅ [file_folder_opener] file_folder_graph 编译完成\n")

if __name__ == "__main__":

    print(file_folder_graph.get_graph().draw_mermaid())

    user_input = input("请输入你的需求：")

    result = file_folder_graph.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": user_input,
                },
            ],
        },
        config=config,
    )

    if result.get("__interrupt__"):
        # preference search断点
        print(result["__interrupt__"][0].value["prompt"])
        print(result["__interrupt__"][0].value["form"])
        decision = input("请输入：")
        result = file_folder_graph.invoke(Command(resume=decision), config=config)

        # should_goto_global_search断点
        print(result["__interrupt__"][0].value["prompt"])
        decision = input("请输入：")
        result = file_folder_graph.invoke(Command(resume=decision), config=config)

        # global_search断点
        print(result["__interrupt__"][0].value["prompt"])
        print(result["__interrupt__"][0].value["form"])
        decision = input("请输入：")
        result = file_folder_graph.invoke(Command(resume=decision), config=config)
