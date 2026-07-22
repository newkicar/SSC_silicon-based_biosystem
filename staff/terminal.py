"""
SSC硅基生物系统 - 员工终端（Staff Terminal）

启动方式：python -m staff.terminal [--server URL]
"""
import sys
import os
import json
import argparse
import time
import warnings
import threading
from datetime import datetime
from pathlib import Path

# 抑制所有第三方库的无害警告（必须在任何第三方库导入之前）.

warnings.simplefilter("ignore")
os.environ["PYTHONWARNINGS"] = "ignore"



if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        os.environ["PYTHONIOENCODING"] = "utf-8"

project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    import requests
except ImportError:
    print("请先安装requests: pip install requests")
    sys.exit(1)

import msvcrt  # Windows 专用：用于密码输入星号显示


def _input_password(prompt=""):
    """Windows 终端密码输入，显示星号(*)，支持退格删除"""
    print(prompt, end="", flush=True)
    password = ""
    while True:
        ch = msvcrt.getch()
        # Enter 键
        if ch in (b'\r', b'\n'):
            print()  # 换行
            return password
        # Backspace 键
        elif ch == b'\x08':
            if password:
                password = password[:-1]
                print('\b \b', end='', flush=True)  # 删除一个星号
        # Ctrl+C
        elif ch == b'\x03':
            print()
            raise KeyboardInterrupt
        # Escape 键
        elif ch == b'\x1b':
            continue
        # 普通字符
        elif len(ch) == 1 and ch >= b' ':
            password += ch.decode('utf-8', errors='ignore')
            print('*', end='', flush=True)


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    @staticmethod
    def disable():
        C.RESET = C.BOLD = C.DIM = C.RED = C.GREEN = C.YELLOW = ""
        C.BLUE = C.MAGENTA = C.CYAN = C.WHITE = ""


def colorize(text, color):
    return f"{color}{text}{C.RESET}"


def print_banner(): 
    print(f"""
{colorize("╔══════════════════════════════════════════════════════════╗", C.CYAN)}
{colorize("║", C.CYAN)}  {colorize("🧬 SSC硅基生物系统", C.BOLD + C.MAGENTA)}  {colorize("— 员工终端", C.DIM)}                     {colorize("║", C.CYAN)}
{colorize("║", C.CYAN)}  {colorize("Staff Terminal · /skill 本地执行 · deepagents", C.DIM)}       {colorize("║", C.CYAN)}
{colorize("╚══════════════════════════════════════════════════════════╝", C.CYAN)}
""")


def print_help():
    print(f"""
{colorize("命令体系：", C.BOLD)}
  {colorize("普通消息", C.CYAN)}           直接输入，与SSC大脑对话

  {colorize("/tasks", C.CYAN)}              查看待处理任务+接收的工单
  {colorize("/task exec", C.CYAN)}          自动处理任务
  {colorize("/task done <id>", C.CYAN)}     标记任务/工单完成(CT-或TK-)
  {colorize("/task info <CT/TK>", C.CYAN)}   查看任务/工单详情
  {colorize("/ticket", C.CYAN)}             提交新工单
  {colorize("/ticket cancel <TK>", C.CYAN)} 撤销我提的工单
  {colorize("/my ticket", C.CYAN)}          查看我提的工单

  {colorize("/skill <需求>", C.GREEN)}      执行Skill（AI自动匹配）
  {colorize("/skill list", C.GREEN)}        查看可用Skill列表

  {colorize("/marathon <任务>", C.MAGENTA)}  业务流程马拉松（多步骤自动执行）
  {colorize("/marathon status", C.MAGENTA)}  查看marathon进度
  {colorize("/marathon resume", C.MAGENTA)}  恢复暂停的marathon

  {colorize("/chat <姓名>", C.YELLOW)}       与同事实时聊天
  {colorize("/exit chat", C.YELLOW)}        结束当前聊天

  {colorize("/whoami", C.CYAN)}             用户信息
  {colorize("/change password", C.CYAN)}    修改密码
  {colorize("/logout", C.CYAN)}             登出
  {colorize("/quit", C.CYAN)}               退出
""")


class SSCClient:
    def __init__(self, server_url):
        self.server_url = server_url.rstrip("/")
        self.token = None
        self.user = None
        self.session_id = f"cli-{int(time.time())}"
        self.timeout = 60

    def _request(self, method, path, body=None, auth=True):
        url = f"{self.server_url}{path}"
        headers = {"Content-Type": "application/json"}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, params=body, timeout=self.timeout)
            elif method == "POST":
                resp = requests.post(url, headers=headers, json=body, timeout=self.timeout)
            elif method == "PUT":
                resp = requests.put(url, headers=headers, json=body, timeout=self.timeout)
            elif method == "DELETE":
                resp = requests.delete(url, headers=headers, timeout=self.timeout)
            else:
                return {"error": f"不支持: {method}"}
            data = resp.json() if "json" in resp.headers.get("content-type", "") else {"raw": resp.text}
            if resp.status_code == 401:
                self.token = None
                self.user = None
                return {"error": "认证已过期", "need_login": True}
            elif resp.status_code >= 400:
                return {"error": data.get("detail", f"HTTP {resp.status_code}")}
            return data
        except requests.exceptions.ConnectionError:
            return {"error": f"无法连接 {self.server_url}"}
        except Exception as e:
            return {"error": str(e)}

    def login(self, username, password):
        result = self._request("POST", "/api/auth/login", {"username": username, "password": password}, auth=False)
        if "error" in result:
            print(colorize(f"  ✗ {result['error']}", C.RED))
            return False
        user_data = result.get("user", {})
        channels = user_data.get("channels", "web")
        if "cli" not in [c.strip() for c in channels.split(",")]:
            print(colorize("  ✗ 无CLI访问权限", C.RED))
            return False
        self.token = result.get("token")
        self.user = user_data
        return True

    def logout(self):
        self._request("POST", "/api/auth/logout")
        self.token = None
        self.user = None

    def sync_skills(self):
        if not self.user or not self.token:
            return
        from staff.skill_sync import check_and_sync
        role = self.user.get("role", "")
        print(colorize("  📦 正在同步 Skill...", C.DIM))
        result = check_and_sync(self.server_url, self.token, role)
        if not result["success"]:
            for err in result.get("errors", []):
                print(colorize(f"    ⚠️ {err}", C.YELLOW))
            return
        synced = result["synced"]
        n = len(synced.get("new", []))
        u = len(synced.get("updated", []))
        d = len(synced.get("deleted", []))
        if n + u + d > 0:
            print(colorize(f"  ✅ Skill同步: {n}新增 {u}更新 {d}删除", C.GREEN))
        else:
            print(colorize("  ✅ Skill已是最新。", C.GREEN))

    def chat(self, message):
        result = self._request("POST", "/api/chat", {"message": message, "session_id": self.session_id, "source": "cli"})
        if "error" in result:
            return f"[错误] {result['error']}"
        return result.get("response", "未能生成回复。")

    def chat_stream(self, message):
        """流式调用大脑，通过 SSE 逐 token 返回回复。
        
        Yields:
            tuple(event_type, data): SSE 事件
        """
        import json as _json
        url = f"{self.server_url}/api/chat/stream"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
        body = {"message": message, "session_id": self.session_id, "source": "cli"}
        try:
            resp = requests.post(url, headers=headers, json=body, stream=True, timeout=300)
            if resp.status_code >= 400:
                yield ("error", f"HTTP {resp.status_code}")
                return
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data: "):
                    try:
                        payload = _json.loads(line[6:])
                        yield (payload.get("type", "chunk"), payload.get("data", ""))
                    except _json.JSONDecodeError:
                        continue
        except requests.exceptions.ConnectionError:
            yield ("error", f"无法连接 {self.server_url}")
        except Exception as e:
            yield ("error", str(e))

    def get_tasks(self):
        return self._request("GET", "/api/cli-tasks")

    def exec_tasks(self):
        from staff.role_agent import auto_process_tasks_for_role
        if not self.user:
            return []
        return auto_process_tasks_for_role(self.user.get("role", ""), self.user.get("username", ""), self.user.get("display_name", ""))

    def mark_task_done(self, task_id):
        return self._request("PUT", f"/api/cli-tasks/{task_id}", {"status": "completed"})

    def close_ticket(self, ticket_no):
        """接收人完成工单"""
        return self._request("POST", f"/api/tickets/{ticket_no}/done")

    def cancel_ticket(self, ticket_no):
        """提交人撤销工单"""
        return self._request("POST", f"/api/tickets/{ticket_no}/cancel")

    def get_task_detail(self, task_id):
        """获取CLI任务详情"""
        return self._request("GET", f"/api/cli-tasks/{task_id}")

    def get_ticket_detail(self, ticket_no):
        """获取单个工单详情"""
        return self._request("GET", f"/api/tickets/{ticket_no}")

    def create_ticket(self, title, category="一般", description="", priority="normal"):
        return self._request("POST", "/api/tickets",
                             {"title": title, "category": category, "description": description, "priority": priority})

    def change_password(self, old_password, new_password):
        return self._request("POST", "/api/profile/change-password",
                             {"old_password": old_password, "new_password": new_password})

    def start_realtime_chat(self, target_user):
        return self._request("POST", "/api/realtime-chat/start",
                             {"target_user": target_user})

    def send_chat_msg(self, session_id, content):
        return self._request("POST", "/api/realtime-chat/send",
                             {"session_id": session_id, "content": content})

    def poll_chat(self, session_id, last_id=0):
        return self._request("POST", "/api/realtime-chat/poll",
                             {"session_id": session_id, "last_id": last_id})

    def close_realtime_chat(self, session_id):
        return self._request("POST", "/api/realtime-chat/close",
                             {"session_id": session_id})

    def get_pending_chat(self, session_id):
        result = self._request("POST", "/api/realtime-chat/pending",
                               {"session_id": session_id})
        # 降级：如果服务端未部署新端点，fallback 到 poll_chat
        if "error" in result:
            return self.poll_chat(session_id, last_id=0)
        return result

    def mark_chat_delivered(self, session_id):
        result = self._request("POST", "/api/realtime-chat/mark-delivered",
                               {"session_id": session_id})
        # 降级：如果服务端未部署新端点，静默忽略
        if "error" in result:
            return {"success": False, "error": result.get("error")}
        return result

    def get_received_tickets(self, status=None):
        params = {"view": "receiver"}
        if status:
            params["status"] = status
        return self._request("GET", "/api/tickets", params)

    def log_activity(self, content, act_type="command"):
        """记录用户活动到服务器数据库（不经过大脑处理）"""
        return self._request("POST", "/api/log-activity",
                             {"content": content, "type": act_type, "session_id": self.session_id})


# ==================== YAML Frontmatter 解析（字符串操作，不用正则） ====================
def _parse_yaml_frontmatter(content: str) -> dict | None:
    """解析 YAML frontmatter（--- ... ---），返回 {"meta": {...}, "body": "..."}。
    YAML frontmatter 是死格式（固定的 --- 包裹结构），用正则处理。
    """
    import re as _re
    fm_match = _re.match(r'^---\s*\n(.*?)\n---\s*\n', content, _re.DOTALL)
    if not fm_match:
        return None
    fm_text = fm_match.group(1)
    body = content[fm_match.end():]

    meta = {}
    current_key = None
    current_list = None
    for line in fm_text.split('\n'):
        stripped = line.strip()
        # 列表项（死格式：以 "- " 开头）
        if stripped.startswith('- ') and current_key and current_list is not None:
            current_list.append(stripped[2:].strip().strip('"').strip("'"))
            continue
        # key: value 对（死格式：`word: value`）
        kv = _re.match(r'^(\w[\w_]*)\s*:\s*(.*)', stripped)
        if kv:
            if current_list is not None and current_key:
                meta[current_key] = current_list
                current_list = None
            key = kv.group(1)
            value = kv.group(2).strip().strip('"').strip("'")
            if not value:
                current_key = key
                current_list = []
            else:
                meta[key] = value
                current_key = key
    if current_list is not None and current_key:
        meta[current_key] = current_list

    return {"meta": meta, "body": body}


# ==================== /skill 命令 ====================
def _get_local_skills():
    skills_dir = Path(__file__).resolve().parent / "skills"
    if not skills_dir.exists():
        return []
    skills = []
    for item in skills_dir.iterdir():
        if not item.is_dir() or item.name.startswith("_") or item.name.startswith("."):
            continue
        skill_md = item / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            content = skill_md.read_text(encoding="utf-8")
            # 用字符串操作解析 YAML frontmatter（--- ... ---）
            frontmatter = _parse_yaml_frontmatter(content)
            if not frontmatter:
                continue
            meta = frontmatter["meta"]
            if not meta.get("name"):
                continue
            target_roles = meta.get("target_roles", [])
            if isinstance(target_roles, str):
                target_roles = [r.strip() for r in target_roles.split(",")]
            body = frontmatter["body"]
            skills.append({
                "name": meta.get("name", item.name),
                "display_name": meta.get("display_name", meta.get("name", "")),
                "description": meta.get("description", ""),
                "target_roles": target_roles,
                "dir": str(item),
                "body": body,
            })
        except Exception:
            pass
    return skills


def _handle_skill_command(client, args):
    if not args:
        print(colorize("  用法: /skill <需求> | /skill list", C.YELLOW))
        return
    cmd = args.strip()
    cmd_lower = cmd.lower()
    if cmd_lower == "list":
        _show_skill_list(client)
    else:
        _execute_skill(client, cmd)


def _show_skill_list(client):
    skills = _get_local_skills()
    role = client.user.get("role", "") if client.user else ""
    if not skills:
        print(colorize("  暂无可用Skill。", C.YELLOW))
        return
    print(f"\n  {colorize('当前可用 Skill：', C.BOLD)}")
    count = 0
    for s in skills:
        tr = s.get("target_roles", [])
        if tr and role and role not in tr:
            continue
        print(f"    {colorize(s['name'], C.GREEN)} — {s.get('description', '')[:60]}")
        count += 1
    if count == 0:
        print(colorize("    （当前角色无可用Skill）", C.DIM))
    print()


def _execute_skill(client, query):
    """
    将用户需求直接交给 deepagents agent，传入所有可用 Skills。
    官方 progressive disclosure 机制会自动：
      - L1 启动时加载所有 Skill 的 name + description 到 system prompt
      - L2 当用户需求匹配某个 Skill 时，自动读取完整 SKILL.md
      - L3 按需读取 scripts/references/assets
    不需要我们自己做匹配！
    """
    skills = _get_local_skills()
    role = client.user.get("role", "") if client.user else ""
    candidates = []
    for s in skills:
        tr = s.get("target_roles", [])
        if not tr or not role or role in tr:
            candidates.append(s)

    if not candidates:
        print(colorize("  ❌ 当前角色无可用Skill。", C.YELLOW))
        return

    # 展示将要加载的 Skills
    skill_names = [s["name"] for s in candidates]
    print(colorize(f"  📦 加载 {len(candidates)} 个Skill: {', '.join(skill_names)}", C.DIM))

    print(colorize(f"  ⚡ 执行中...", C.DIM))

    # 构建用户上下文
    user_ctx = ""
    if client.user:
        user_ctx = (
            f"\n\n[用户上下文]\n"
            f"- user_id: {client.user.get('username', '')}\n"
            f"- 姓名: {client.user.get('display_name', '')}\n"
            f"- 角色: {client.user.get('role', '')}\n"
            f"- 服务端: {client.server_url}\n"
            f"- Token: {client.token}\n"
            f"- 对话API: GET {client.server_url}/api/conversations?start_date=&end_date=\n"
            f"  (Header: Authorization: Bearer {client.token})\n"
            f"- 输出: staff/work_summaries/\n"
        )
    try:
        result_text = _run_local_agent(candidates, query, user_ctx)
        # 保存最终结果到数据库（只存输出，不存中间过程）
        if result_text:
            try:
                client.log_activity(f"[skill结果] {result_text[:2000]}", "skill_result")
            except Exception:
                pass
    except KeyboardInterrupt:
        print(colorize("\n  ⚠️ 用户中断执行。", C.YELLOW))
    except Exception as e:
        error_msg = str(e)
        # 针对常见错误给出友好提示
        if "Connection" in error_msg or "timeout" in error_msg.lower():
            print(colorize(f"  ❌ LLM模型连接失败，请检查网络或模型服务是否正常。", C.RED))
            print(colorize(f"     详情: {error_msg[:200]}", C.DIM))
        elif "rate" in error_msg.lower() or "429" in error_msg:
            print(colorize(f"  ❌ 模型请求频率超限，请稍后重试。", C.RED))
        elif "auth" in error_msg.lower() or "401" in error_msg:
            print(colorize(f"  ❌ 模型认证失败，请检查API Key配置。", C.RED))
        else:
            print(colorize(f"  ❌ 执行异常: {error_msg[:300]}", C.RED))
        print(colorize(f"  💡 您可以继续使用其他功能，无需重新登录。", C.DIM))


def _run_local_agent(skill_list, query, user_ctx):
    """
    使用 deepagents 官方标准方式执行 Skill。

    官方流程（不自己匹配，全部交给 agent）：
    1. create_deep_agent(model, backend, skills=[所有skill目录]) — 加载全部 Skill
    2. agent.invoke(messages) — 发送用户需求
    3. deepagents SkillsMiddleware 自动按 progressive disclosure：
       - L1: 将所有 Skill 的 name+description 注入 system prompt
       - L2: agent 根据用户需求语义匹配，自动选择并读取对应 SKILL.md
       - L3: 按需读取 scripts/references/assets
    """
    # 导入期间抑制所有第三方库警告
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from deepagents import create_deep_agent
        from deepagents.backends import LocalShellBackend
    from staff.llm import get_llm

    # 注入环境变量（HTTP API 凭据 + UTF-8 编码）
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if user_ctx:
        # 从 user_ctx 中提取服务端URL和Token（死格式：自生成的固定格式行）
        import re as _re
        server_m = _re.search(r'- 服务端:\s*(\S+)', user_ctx)
        if server_m:
            env["SSC_SERVER_URL"] = server_m.group(1)
        token_m = _re.search(r'- Token:\s*(\S+)', user_ctx)
        if token_m:
            env["SSC_TOKEN"] = token_m.group(1)

    # 官方标准：LocalShellBackend + virtual_mode + env
    backend = LocalShellBackend(
        root_dir=".",
        virtual_mode=True,
        env=env,
    )
    checkpointer = _get_skill_checkpointer()

    # 官方标准：传入所有 Skill 的相对路径，让 agent 自动选择
    # virtual_mode=True 下 skills 路径必须相对于 root_dir
    skills_dir = str(Path(__file__).resolve().parent / "skills")
    skills_rel = os.path.relpath(skills_dir, os.getcwd()).replace("\\", "/") + "/"

    # 加载自定义工具（GUI自动化、文件操作等）
    # 注意：工具是全局注册的，agent 会根据 Skill 内容自动决定是否使用
    from staff.tools import get_tools
    custom_tools = get_tools()

    # 获取项目根目录的绝对路径，注入到system prompt
    _project_root = str(Path(__file__).resolve().parent.parent).replace("\\", "/")

    # Staff Agent system prompt：融合官方harness行为准则 + HR SSC执行策略
    _staff_system_prompt = f"""你是一个HR SSC执行代理，帮助HR员工完成实际操作任务（工作总结、预约会议室、邮件管理等）。

## ⚠️ 路径规则（必须严格遵守）

你的工作目录是：{_project_root}

所有文件路径必须使用相对路径（不带前导斜杠），或使用上面的绝对路径作为前缀：
- ✅ 正确：staff/skills/skill-outlook-controller/scripts/outlook_cli.py
- ✅ 正确：{_project_root}/staff/skills/skill-outlook-controller/scripts/outlook_cli.py
- ❌ 错误：/staff/skills/skill-outlook-controller/scripts/outlook_cli.py（Windows下会解析为D盘根目录！）

执行Python脚本时，使用 `{_project_root}` 作为前缀构建完整路径。

## 核心行为

**简洁直接**。不要无意义的开场白（"好的！"、"我来帮你..."、"让我看看..."）。不要说"我将要做X"——直接做X。

**客观准确**。优先保证准确性，而非迎合用户的假设。当用户信息有误时，礼貌指出。

**理解再行动**。收到任务后：先快速理解（读相关文件、查看现有模式）→ 然后执行 → 最后验证结果是否符合要求。第一次尝试很少是完美的——迭代改进。

**持续工作直到完成**。不要做到一半停下来解释你会怎么做——直接做完。只在任务完成或真正卡住时才交还给用户。

## 执行策略

### 复杂任务
1. 先分析任务，拆解为步骤（使用 write_todos 工具）
2. 按步骤逐一执行，每步执行后验证结果
3. 中途发现计划需调整时，更新 todo 后继续
4. **简单任务（1-3步能完成）不要用 write_todos**，直接执行

### 工具错误处理
1. **诊断**：分析错误本质（参数/环境/权限/逻辑错误）
2. **修正**：针对原因调整后重试一次
3. **换路**：仍失败则思考替代方案（如 GUI 失败→命令行）
4. **升级**：全部失败则给出结构化报告（尝试了什么/具体错误/根本原因/建议行动）

### 特殊情况
- **权限错误**：不重试，直接升级报告
- **工具不可用**：检查是否需要启动外部软件或等待网络
- **数据不存在**：尝试不同搜索关键词或路径

### 并行化
- 当有多个独立步骤时，尽量并行执行（如同时读取多个文件、同时调用多个工具）
- 不要串行做可以并行的事

## 提问原则

- 不要追问用户已经提供的信息
- 当请求隐含了合理默认值时，直接使用默认值执行
- 如果确实需要澄清，只问最少的必要问题
- 优先问领域定义问题（做什么），而非实现细节问题（怎么做）"""

    agent = create_deep_agent(
        model=get_llm(),
        backend=backend,
        skills=[skills_rel],
        tools=custom_tools,  # 注册自定义工具，agent 按需调用
        checkpointer=checkpointer,
        system_prompt=_staff_system_prompt,
    )

    # 构建用户消息
    user_msg = query
    if user_ctx:
        user_msg = f"{query}\n{user_ctx}"

    # 官方标准：agent.invoke — agent 会自动匹配并执行合适的 Skill
    # 临时重定向 stderr 以抑制第三方库的无害警告（如 LangChainPendingDeprecationWarning）
    import io
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    result = None
    try:
        # 使用稳定的 thread_id 让同一终端会话的多次 /skill 调用共享上下文
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_msg}]},
            config={"configurable": {"thread_id": _skill_thread_id}},
        )
    except Exception as e:
        sys.stderr = old_stderr
        raise  # 由外层 _execute_skill 的 try/except 捕获并显示友好提示
    finally:
        sys.stderr = old_stderr

    # 输出结果（显示所有中间消息，包括思考过程）
    final_answer = None  # 提取最终 assistant 回复，用于保存到数据库
    try:
        if result and "messages" in result:
            messages = result["messages"]
            # 跳过第1条（用户消息），展示 agent 的完整思考和执行过程
            for i, msg in enumerate(messages[1:], 1):
                role = getattr(msg, "type", "unknown")
                content = ""
                if hasattr(msg, "content"):
                    content = msg.content or ""
                elif isinstance(msg, dict):
                    content = msg.get("content", "")

                # 检查是否有 tool_calls（表示 agent 正在调用工具）
                tool_calls = getattr(msg, "tool_calls", [])
                if tool_calls:
                    for tc in tool_calls:
                        tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                        if tool_name:
                            print(colorize(f"\n  🔧 调用工具: {tool_name}", C.CYAN))

                # 输出消息内容
                if content.strip():
                    # assistant 消息显示为思考过程
                    if role == "assistant":
                        print(f"\n{colorize('🧠 思考过程：', C.YELLOW + C.BOLD)}")
                        print(content.strip())
                        # 最后一条有内容的 assistant 消息视为最终回复
                        final_answer = content.strip()
                    # tool 消息显示为工具执行结果
                    elif role == "tool":
                        # 只显示前500字符，避免过长
                        display_content = content.strip()
                        if len(display_content) > 500:
                            display_content = display_content[:500] + "\n  ... (输出已截断)"
                        print(colorize(f"\n  📋 工具输出:", C.DIM))
                        print(f"  {display_content}")
                    # 最后的 assistant 消息显示为最终结果
                    elif i == len(messages) - 1:
                        print(f"\n{colorize('🧬 执行结果：', C.GREEN + C.BOLD)}")
                        print(content.strip())
                        final_answer = content.strip()
                    else:
                        if content.strip():
                            print(f"\n{colorize('💬 ' + role + '：', C.DIM)}")
                            print(content.strip())

            # 如果没有任何消息内容
            has_content = any(
                (hasattr(m, "content") and (m.content or "").strip())
                for m in messages[1:]
            )
            if not has_content:
                print(f"\n{colorize('✅ Skill执行完成。', C.GREEN)}")
        else:
            print(f"\n{colorize('✅ Skill执行完成。', C.GREEN)}")
    except Exception as e:
        print(colorize(f"\n  ⚠️ 结果输出异常: {str(e)[:200]}", C.YELLOW))
        print(colorize(f"  ✅ 但Skill可能已执行完成，请检查结果。", C.GREEN))

    return final_answer


# ==================== Skill Agent 共享状态 ====================
# 复用同一个 MemorySaver 实例，让同一终端会话的多次 /skill 调用共享上下文
_skill_checkpointer = None  # 延迟初始化，在首次使用时创建
_skill_thread_id = f"skill-session-{int(time.time())}"


def _get_skill_checkpointer():
    """获取或创建共享的 checkpointer（延迟导入）"""
    global _skill_checkpointer
    if _skill_checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver
        _skill_checkpointer = MemorySaver()
    return _skill_checkpointer


# ==================== 即时聊天状态（用字典避免global声明问题） ====================
_chat_state = {
    "session_id": None,   # 当前聊天会话ID（活跃聊天模式时有值）
    "target": None,       # 当前聊天对象姓名
    "last_id": 0,         # 已收到的最后一条消息ID
    "poll_stop": None,    # 停止轮询的Event
    "poll_thread": None,  # 轮询线程
    "is_initiator": False,  # 是否是聊天发起人（user1）
    "preserved_session_id": None,  # 发起方退出后保留的session ID（被动监控模式）
    "preserved_target": None,      # 发起方退出后保留的聊天对象
    "pending_after_exit": False,   # 被动监控期间是否检测到新消息
}


def _start_chat_poll(client, session_id, reset_last_id=True):
    """启动后台消息轮询线程
    
    Args:
        client: SSCClient实例
        session_id: 聊天会话ID
        reset_last_id: 是否重置last_id为0。为False时保留当前值（用于_check_pending_chat已加载历史消息后）
    """
    _chat_state["poll_stop"] = threading.Event()
    if reset_last_id:
        _chat_state["last_id"] = 0

    def _poll_loop():
        poll_count = 0
        while not _chat_state["poll_stop"].is_set():
            try:
                # 每3轮（约6秒）检查一次会话是否仍然活跃
                if poll_count % 3 == 0:
                    active = client._request("GET", "/api/realtime-chat/active")
                    if not (active.get("success") and active.get("session")):
                        # 会话已被对方关闭，自动退出
                        print(f"\r{' ' * 40}\r", end="")
                        print(colorize(f"\n  💬 对方已退出聊天，自动退出聊天模式。", C.YELLOW))
                        _chat_state["session_id"] = None
                        _chat_state["target"] = None
                        _chat_state["last_id"] = 0
                        # 重新显示输入提示
                        ud = client.user["display_name"] if client.user else "未登录"
                        rd = client.user["role"] if client.user else ""
                        print(f"{colorize('┌─', C.DIM)} {colorize(ud, C.CYAN)} {colorize(f'({rd})', C.DIM)}")
                        print(f"{colorize('└─▸', C.DIM)} ", end="", flush=True)
                        return
                result = client.poll_chat(session_id, last_id=_chat_state["last_id"])
                messages = result.get("messages", [])
                for msg in messages:
                    sender = msg.get("sender", "")
                    content = msg.get("content", "")
                    msg_id = msg.get("id", 0)
                    if sender != client.user.get("username", ""):
                        # 对方发的消息，显示到终端
                        print(f"\r{' ' * 40}\r", end="")
                        print(colorize(f"  📩 [{sender}]: ", C.GREEN) + content)
                        print(f"{colorize('  [聊天]', C.YELLOW)} ", end="", flush=True)
                    _chat_state["last_id"] = max(_chat_state["last_id"], msg_id)
            except Exception:
                pass
            poll_count += 1
            _chat_state["poll_stop"].wait(timeout=2)

    _chat_state["poll_thread"] = threading.Thread(target=_poll_loop, daemon=True)
    _chat_state["poll_thread"].start()


# ==================== 后台自动加入聊天邀请 ====================
_invite_watch_stop = None   # 停止事件
_invite_watch_thread = None  # 监听线程


def _start_invite_watch(client):
    """启动后台线程，每5秒检查一次是否有新的聊天邀请（对方发起的活跃会话）"""
    global _invite_watch_stop, _invite_watch_thread
    _invite_watch_stop = threading.Event()

    def _watch_loop():
        while not _invite_watch_stop.is_set():
            try:
                # 只在未处于聊天模式时检查
                if not _chat_state["session_id"]:
                    result = client._request("GET", "/api/realtime-chat/active")
                    if result.get("success") and result.get("session"):
                        session = result["session"]
                        user1 = session.get("user1", "")
                        my_username = client.user.get("username", "")
                        # 跳过自己发起的会话（/exit chat 后 session 仍 active，不应重新加入）
                        if user1 == my_username:
                            _invite_watch_stop.wait(timeout=5)
                            continue
                        partner_username = user1
                        if partner_username == my_username:
                            partner_username = session.get("user2", "")
                        sid = session.get("session_id", "")
                        if sid:
                            _chat_state["session_id"] = sid
                            _chat_state["target"] = partner_username
                            _start_chat_poll(client, sid)
                            # 清除当前输入行，显示提示
                            print(f"\r{' ' * 60}\r", end="")
                            print(colorize(f"\n  📨 检测到聊天邀请（来自 {partner_username}），已自动加入！", C.GREEN))
                            print(colorize(f"  💬 直接输入消息即可发送，输入 /exit chat 结束", C.DIM))
                            print(f"{colorize('  [聊天模式已激活]', C.YELLOW)} ", end="", flush=True)
            except Exception:
                pass
            _invite_watch_stop.wait(timeout=5)

    _invite_watch_thread = threading.Thread(target=_watch_loop, daemon=True)
    _invite_watch_thread.start()


def _stop_invite_watch():
    """停止聊天邀请监听线程"""
    global _invite_watch_stop
    if _invite_watch_stop:
        _invite_watch_stop.set()


# ==================== 交互循环 ====================
def _check_pending_chat(client):
    """登录后检查是否有活跃的聊天会话需要加入。
    
    只加载待推送的（pending）消息，保证每条消息只推送一次。
    显示由 _display_pending_chat 控制顺序。
    返回加载的消息列表，供调用方在合适时机显示。
    """
    result = client._request("GET", "/api/realtime-chat/active")
    if result.get("success") and result.get("session"):
        session = result["session"]
        partner_username = session.get("user1", "")
        if partner_username == client.user.get("username", ""):
            partner_username = session.get("user2", "")
        sid = session.get("session_id", "")
        if sid:
            _chat_state["session_id"] = sid
            _chat_state["target"] = partner_username
            # 只拉取待推送的消息（pending），不拉取已推送过的
            pending_result = client.get_pending_chat(sid)
            messages = pending_result.get("messages", [])
            # 启动后台轮询，只关注新消息（last_id=0 确保不遗漏）
            _start_chat_poll(client, sid, reset_last_id=True)
            return {
                "has_session": True,
                "partner": partner_username,
                "messages": messages,
                "my_username": client.user.get("username", ""),
                "session_id": sid,
            }
    return {"has_session": False}


def _start_passive_poll(client, session_id, partner_username):
    """发起方退出聊天后，启动被动轮询监控对方回复。
    
    当检测到对方新消息时，通知用户并提示按 r 重新进入聊天。
    """
    if _chat_state.get("poll_stop"):
        _chat_state["poll_stop"].set()
    _chat_state["poll_stop"] = threading.Event()

    def _passive_loop():
        poll_count = 0
        while not _chat_state["poll_stop"].is_set():
            try:
                # 每3轮（约6秒）检查一次会话是否仍然活跃
                if poll_count % 3 == 0:
                    active = client._request("GET", "/api/realtime-chat/active")
                    if not (active.get("success") and active.get("session")):
                        # 会话已被对方关闭，停止被动监控
                        print(f"\r{' ' * 60}\r", end="")
                        print(colorize(f"\n  💬 {partner_username} 已退出聊天，会话结束。", C.DIM))
                        _chat_state["preserved_session_id"] = None
                        _chat_state["preserved_target"] = None
                        _chat_state["pending_after_exit"] = False
                        ud = client.user["display_name"] if client.user else "未登录"
                        rd = client.user["role"] if client.user else ""
                        print(f"{colorize('┌─', C.DIM)} {colorize(ud, C.CYAN)} {colorize(f'({rd})', C.DIM)}")
                        print(f"{colorize('└─▸', C.DIM)} ", end="", flush=True)
                        return
                # 检查对方是否有新消息
                result = client.poll_chat(session_id, last_id=_chat_state["last_id"])
                messages = result.get("messages", [])
                has_new_from_partner = False
                for msg in messages:
                    sender = msg.get("sender", "")
                    content = msg.get("content", "")
                    msg_id = msg.get("id", 0)
                    if sender != client.user.get("username", ""):
                        has_new_from_partner = True
                        print(f"\r{' ' * 60}\r", end="")
                        print(colorize(f"\n  📩 [{sender}]: {content}", C.GREEN))
                    _chat_state["last_id"] = max(_chat_state["last_id"], msg_id)
                if has_new_from_partner:
                    _chat_state["pending_after_exit"] = True
                    print(colorize(f"  💬 输入 r 重新进入与 {partner_username} 的聊天", C.YELLOW))
                    _ud = client.user["display_name"] if client.user else ""
                    _rd = client.user["role"] if client.user else ""
                    print(f"{colorize('┌─', C.DIM)} {colorize(_ud, C.CYAN)} {colorize(f'({_rd})', C.DIM)}")
                    print(f"{colorize('└─▸', C.DIM)} ", end="", flush=True)
            except Exception:
                pass
            poll_count += 1
            _chat_state["poll_stop"].wait(timeout=3)

    _chat_state["poll_thread"] = threading.Thread(target=_passive_loop, daemon=True)
    _chat_state["poll_thread"].start()


def _reset_chat_state():
    """重置聊天状态（统一清理逻辑）"""
    if _chat_state.get("poll_stop"):
        _chat_state["poll_stop"].set()
    _chat_state["session_id"] = None
    _chat_state["target"] = None
    _chat_state["last_id"] = 0
    _chat_state["is_initiator"] = False
    _chat_state["preserved_session_id"] = None
    _chat_state["preserved_target"] = None
    _chat_state["pending_after_exit"] = False


def _display_pending_chat(chat_info):
    """在合适的位置显示历史聊天消息（在命令帮助之后调用）。
    显示后自动将消息标记为已推送，确保下次登录不重复显示。
    """
    if not chat_info.get("has_session"):
        return
    partner = chat_info["partner"]
    messages = chat_info.get("messages", [])
    my_username = chat_info.get("my_username", "")
    session_id = chat_info.get("session_id", "")
    if messages:
        print(colorize(f"  📨 检测到与 {partner} 的聊天会话，加载了 {len(messages)} 条未读消息：", C.GREEN))
        print(colorize(f"  {'─' * 50}", C.DIM))
        for msg in messages:
            sender = msg.get("sender", "")
            content = msg.get("content", "")
            ts = msg.get("created_at", "")
            if sender == my_username:
                print(colorize(f"  [{ts}] 我: ", C.CYAN) + content)
            else:
                print(colorize(f"  [{ts}] {sender}: ", C.GREEN) + content)
        print(colorize(f"  {'─' * 50}", C.DIM))
        # 注意：标记已推送由 interactive_loop 在显示后调用 client.mark_chat_delivered
        print(colorize(f"  📌 上述消息已标记为已推送，下次登录不再重复显示。", C.DIM))
    else:
        print(colorize(f"  📨 检测到与 {partner} 的聊天会话，暂无未读消息。", C.GREEN))
    print(colorize(f"  💬 直接输入消息即可发送，输入 /exit chat 结束", C.DIM))


# ==================== /marathon 命令 ====================
def _handle_marathon_command(client, args, proj_root):
    """处理 /marathon 命令"""
    from staff.marathon.graph import run_marathon, resume_marathon
    from staff.marathon.state import list_marathons
    from staff.marathon.config import MARATHON_PAUSED, MARATHON_FAILED, MARATHON_CANCELLED

    args = args.strip() if args else ""

    if not args:
        print(colorize("  用法:", C.YELLOW))
        print(colorize("    /marathon <任务描述>       启动新的马拉松", C.DIM))
        print(colorize("    /marathon status           查看所有marathon进度", C.DIM))
        print(colorize("    /marathon resume [id]      恢复暂停的marathon", C.DIM))
        return

    cmd = args.lower()

    # ── /marathon status ──
    if cmd == "status":
        marathons = list_marathons(proj_root)
        if not marathons:
            print(colorize("  暂无marathon记录。", C.DIM))
            return
        print(f"\n  {colorize('📋 Marathon 记录：', C.BOLD)}")
        for m in marathons:
            icon = {"planning":"📝","executing":"⏳","paused":"⏸","done":"✅","failed":"❌","cancelled":"🚫"}.get(m["status"], "❓")
            print(f"    {icon} [{m['marathon_id']}] {m['task_description'][:50]}")
            print(f"       状态: {m['status']} | 进度: {m['progress']} | 更新: {m['updated_at'][:19]}")
        print()
        return

    # ── /marathon resume ──
    if cmd.startswith("resume"):
        marathons = list_marathons(proj_root)
        paused = [m for m in marathons if m["status"] in ("paused", "executing")]
        if not paused:
            print(colorize("  没有可恢复的marathon。", C.YELLOW))
            return
        resume_id = cmd.replace("resume", "").strip()
        target = None
        if resume_id:
            target = next((m for m in paused if resume_id in m["marathon_id"]), None)
        else:
            target = paused[0]
        if not target:
            print(colorize(f"  未找到marathon: {resume_id}", C.RED))
            return
        print(colorize(f"  恢复 marathon: {target['task_description'][:50]}...", C.CYAN))
        print(colorize("  选择操作: [r]重试 / [s]跳过当前步 / [e]终止", C.YELLOW))
        decision = input(f"  {colorize('操作(回车默认r):', C.CYAN)} ").strip() or "r"
        try:
            final = resume_marathon(target["state_dir"], decision, lambda n,u,s: _marathon_display(n,u,s))
            _marathon_final(final, client=client)
        except Exception as e:
            print(colorize(f"  ❌ 恢复失败: {str(e)[:200]}", C.RED))
        return

    # ── /marathon <任务描述> ──
    print(f"\n{'═'*50}")
    print(colorize("🎯 Marathon Agent 启动", C.BOLD + C.MAGENTA))
    print(f"📋 任务: {colorize(args, C.CYAN)}")
    print(f"{'═'*50}")

    # 注入服务端凭据到环境变量（供 Marathon executor 的 dispatch_actions 使用）
    if client.server_url:
        os.environ["SSC_SERVER_URL"] = client.server_url
    if client.token:
        os.environ["SSC_TOKEN"] = client.token

    # 注册 Event Streaming 回调：实时显示大脑的 tool call 事件
    from staff.marathon.nodes.executor import set_brain_event_callback
    def _brain_stream_display(event_type, event_data):
        now = datetime.now().strftime("%H:%M:%S")
        if event_type == "tool_start":
            tool = event_data.get("tool", "")
            inp = event_data.get("input", "")[:60]
            print(colorize(f"    🔧 [{now}] 调用 {tool}({inp})", C.CYAN), flush=True)
        elif event_type == "tool_end":
            tool = event_data.get("tool", "")
            out = event_data.get("output", "")[:60]
            print(colorize(f"    📋 [{now}] {tool} → {out}", C.DIM), flush=True)
        elif event_type == "rubric_evaluation":
            result = event_data.get("result", "unknown")
            explanation = event_data.get("explanation", "")
            iteration = event_data.get("iteration", 0)
            criteria = event_data.get("criteria", [])
            icon = "✅" if result == "satisfied" else "🔄" if result == "needs_revision" else "⚠️"
            print(colorize(f"    {icon} [{now}] Rubric验证(iter {iteration}): {result} — {explanation[:60]}", C.YELLOW), flush=True)
            for c in criteria:
                c_icon = "✅" if c.get("passed") else "❌"
                gap = c.get("gap", "")
                name = c.get("name", "")
                gap_text = f" ({gap[:40]})" if gap else ""
                print(colorize(f"      {c_icon} {name}{gap_text}", C.DIM), flush=True)
    set_brain_event_callback(_brain_stream_display)

    try:
        final = run_marathon(
            task_description=args,
            username=client.user.get("username", ""),
            display_name=client.user.get("display_name", ""),
            project_root=proj_root,
            stream_callback=lambda n,u,s: _marathon_display(n,u,s),
        )
        _marathon_final(final, original_question=args, session_id=client.session_id, client=client)
    except KeyboardInterrupt:
        print(colorize("\n  ⚠️ 用户中断。进度已保存，可用 /marathon resume 恢复。", C.YELLOW))
    except Exception as e:
        print(colorize(f"\n  ❌ Marathon异常: {str(e)[:300]}", C.RED))
        print(colorize("  💡 进度已保存，可用 /marathon resume 恢复。", C.DIM))
    finally:
        set_brain_event_callback(None)  # 清除回调


def _marathon_display(node_name, updates, state_dict):
    """Marathon 进度实时展示"""
    now = datetime.now().strftime("%H:%M:%S")
    if node_name == "planner":
        plan = updates.get("plan", [])
        if plan:
            print(f"\n  {colorize('📝 规划完成:', C.BOLD)}")
            for step in plan:
                d = step.description if hasattr(step, "description") else step.get("description", "")
                a = step.action_type if hasattr(step, "action_type") else step.get("action_type", "")
                cap = step.capability if hasattr(step, "capability") else step.get("capability", "")
                sid = step.id if hasattr(step, "id") else step.get("id", "?")
                cap_text = f" [{cap}]" if cap else ""
                print(f"    [{sid}]{cap_text} {d} ({a})")
    elif node_name == "executor":
        plan = state_dict.get("plan", [])
        idx = state_dict.get("current_step_index", 0)
        if plan and idx < len(plan):
            step = plan[idx]
            d = step.description if hasattr(step, "description") else step.get("description", "")
            print(f"\n  ▶ {colorize(f'Step {idx+1}/{len(plan)}:', C.CYAN)} {d}")
            print(colorize(f"    [{now}] 大脑执行中...", C.DIM), flush=True)
    elif node_name == "validator":
        v = updates.get("current_validation")
        if v:
            p = v.passed if hasattr(v, "passed") else v.get("passed")
            l = v.level if hasattr(v, "level") else v.get("level", "")
            e = v.error if hasattr(v, "error") else v.get("error", "")
            if p: print(colorize(f"    ✅ 验证通过 ({l})", C.GREEN))
            else: print(colorize(f"    ❌ 验证失败 ({l}): {e[:80]}", C.RED))
    elif node_name == "committer":
        print(colorize("    📦 检查点已保存", C.DIM))
    elif node_name == "error_handler":
        if updates.get("requires_human"):
            print(colorize(f"\n  ⚠️ 需要人类介入:", C.YELLOW + C.BOLD))
            print(f"    {updates.get('human_message', '')}")
        elif updates.get("status") == "failed":
            print(colorize("    💀 任务失败", C.RED))
        else:
            print(colorize("    🔄 准备重试...", C.DIM))


def _marathon_final(final_state, original_question=None, session_id=None, client=None):
    """Marathon 最终结果展示 + 合成最终回复"""
    from staff.marathon.config import MARATHON_DONE, MARATHON_FAILED, MARATHON_CANCELLED, MARATHON_PAUSED
    plan = final_state.plan
    done_c = sum(1 for s in plan if s.status == "done")
    skip_c = sum(1 for s in plan if s.status == "skipped")
    fail_c = sum(1 for s in plan if s.status == "failed")
    print(f"\n{'═'*50}")
    if final_state.status == MARATHON_DONE:
        print(colorize("🎉 Marathon 完成！", C.BOLD + C.GREEN))
    elif final_state.status == MARATHON_PAUSED:
        print(colorize("⏸ Marathon 暂停（等待人类决策）", C.BOLD + C.YELLOW))
    elif final_state.status == MARATHON_FAILED:
        print(colorize("💀 Marathon 失败", C.BOLD + C.RED))
    elif final_state.status == MARATHON_CANCELLED:
        print(colorize("🚫 Marathon 已取消", C.BOLD + C.DIM))
    print(f"   步骤: {done_c}完成 / {skip_c}跳过 / {fail_c}失败 / {len(plan)}总计")
    if final_state.state_dir:
        print(colorize(f"   详情: {final_state.state_dir}/PROGRESS.md", C.DIM))
    print(f"{'═'*50}")

    # 合成最终回复：将所有步骤结果汇总，调用大脑生成用户友好的回答
    if final_state.status == MARATHON_DONE and original_question:
        _marathon_synthesize_answer(original_question, final_state, session_id=session_id, client=client)
    elif final_state.status in (MARATHON_FAILED, MARATHON_PAUSED):
        # 失败/暂停时也给出提示
        print(colorize("\n  💡 如需继续，可使用 /marathon resume 恢复。", C.DIM))


def _marathon_synthesize_answer(original_question, final_state, session_id=None, client=None):
    """Marathon完成后，汇总所有步骤结果，调用大脑生成用户友好的最终回复。
    session_id 用于共享 checkpointer，让 Marathon 回复进入普通对话的上下文记忆。
    client 用于将最终结果保存到服务器数据库。"""
    from src.brain import create_brain_agent_with_tools

    # 收集所有步骤的完整结果（result_summary 现在保存了完整回复，最长2000字符）
    step_results = []
    for s in final_state.plan:
        desc = s.description if hasattr(s, "description") else s.get("description", "")
        result = s.result_summary if hasattr(s, "result_summary") else s.get("result_summary", "")
        status = s.status if hasattr(s, "status") else s.get("status", "")
        if status == "done" and result:
            step_results.append(f"### {desc}\n{result}")

    if not step_results:
        print(colorize("  （无步骤结果可汇总）", C.DIM))
        return

    # 注入身份信息（干净的结构化数据，交给大脑语义理解）
    synthesis_prompt = f"""[用户身份]
工号: {final_state.username}
姓名: {final_state.display_name}

用户问题：{original_question}

Marathon 执行了以下步骤，每步都有详细结果：
{chr(10).join(step_results)}

请根据以上步骤的执行结果，用自然语言回答用户的原始问题。
直接给出答案，不要列出执行步骤。像普通对话一样回复，简洁但信息完整。
如果涉及该用户的考勤/薪资/个人信息，直接基于步骤中的数据回答。"""

    print(f"\n{colorize('🧬 综合回复：', C.BOLD + C.MAGENTA)}", flush=True)

    try:
        brain_agent = create_brain_agent_with_tools()
        result = brain_agent.invoke(
            {"messages": [{"role": "user", "content": synthesis_prompt}]},
            config={"configurable": {"thread_id": session_id or f"marathon-synthesis-{final_state.marathon_id}"}},
        )

        # 提取回复内容（兼容 object 和 dict 两种返回格式）
        answer = None
        if hasattr(result, "messages") and result.messages:
            # result 是对象，有 messages 属性
            answer = result.messages[-1].content
        elif isinstance(result, dict) and "messages" in result and result["messages"]:
            # result 是 dict
            last_msg = result["messages"][-1]
            if isinstance(last_msg, dict):
                answer = last_msg.get("content", "")
            elif hasattr(last_msg, "content"):
                answer = last_msg.content

        if answer:
            # 清理可能的 dispatch_actions JSON 和秘书任务标记（字符串操作，不用正则）
            answer = _clean_response_markers(answer)
            if answer:
                print(answer)
                # 保存最终结果到数据库（只存输出，不存中间过程）
                if client:
                    try:
                        client.log_activity(f"[marathon结果] {answer[:2000]}", "marathon_result")
                    except Exception:
                        pass
            else:
                # 清理后为空，降级展示步骤结果
                print(colorize("  （大脑回复为空，以下为各步骤执行结果）", C.DIM))
                _show_step_results_fallback(step_results)
        else:
            # 无法提取回复，降级展示
            print(colorize("  （合成回复失败，以下为各步骤执行结果）", C.YELLOW))
            _show_step_results_fallback(step_results)
    except Exception as e:
        print(colorize(f"  ⚠️ 合成回复异常: {str(e)[:200]}", C.YELLOW))
        # 降级：直接展示步骤结果
        print(colorize("\n  📋 各步骤执行结果：", C.DIM))
        _show_step_results_fallback(step_results)


def _show_step_results_fallback(step_results):
    """降级展示：直接输出各步骤结果"""
    print(colorize("\n  📋 各步骤执行结果：", C.DIM))
    for sr in step_results:
        print(f"  {sr}")


def _clean_response_markers(text: str) -> str:
    """移除响应中的结构化标记（死格式，用正则处理）。
    - dispatch_actions JSON 块：```json ... "dispatch_actions" ... ```
    - 秘书任务标记：【秘书任务】...【/秘书任务】
    """
    import re as _re
    # 移除含 dispatch_actions 的 JSON 代码块（死格式：```json 包裹）
    text = _re.sub(r'```json\s*\n?\s*\{[\s\S]*?"dispatch_actions"[\s\S]*?\}\s*\n?```', '', text)
    # 移除秘书任务标记（死格式：中文书名号包裹）
    text = _re.sub(r'【秘书任务】[\s\S]*?【/秘书任务】', '', text)
    return text.strip()


def interactive_loop(client):
    chat_info = _check_pending_chat(client)
    _start_invite_watch(client)
    print_help()
    # 聊天历史显示在命令帮助之后，更醒目
    _display_pending_chat(chat_info)
    # 将待推送消息标记为已推送，确保下次登录不重复显示
    if chat_info.get("has_session") and chat_info.get("messages") and chat_info.get("session_id"):
        client.mark_chat_delivered(chat_info["session_id"])
    while True:
        try:
            # 邀请监听线程已自动处理新会话检测，无需每轮重复检查
            ud = client.user["display_name"] if client.user else "未登录"
            rd = client.user["role"] if client.user else ""
            prompt = f"{colorize('┌─', C.DIM)} {colorize(ud, C.CYAN)} {colorize(f'({rd})', C.DIM)}\n{colorize('└─▸', C.DIM)} "
            user_input = input(prompt).strip()
            if not user_input:
                continue
            if user_input.startswith("/"):
                parts = user_input.split(maxsplit=1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                # 记录命令到 conversations 表（不经过大脑处理）
                if client.user and cmd not in ("/quit", "/exit", "/q", "/help"):
                    try:
                        client.log_activity(user_input, "command")
                    except Exception:
                        pass  # 日志记录失败不影响命令执行
                if cmd in ("/quit", "/q"):
                    _stop_invite_watch()
                    print(colorize("\n  再见！🧬\n", C.DIM))
                    break
                elif cmd == "/exit" and not args.strip():
                    _stop_invite_watch()
                    print(colorize("\n  再见！🧬\n", C.DIM))
                    break
                elif cmd == "/help":
                    print_help()
                elif cmd == "/skill":
                    if not client.user:
                        print(colorize("  请先登录。", C.YELLOW))
                        continue
                    _handle_skill_command(client, args)
                elif cmd == "/marathon":
                    if not client.user:
                        print(colorize("  请先登录。", C.YELLOW))
                        continue
                    _handle_marathon_command(client, args, project_root)
                elif cmd == "/whoami":
                    if client.user:
                        u = client.user
                        print(f"\n  {colorize('用户信息：', C.BOLD)}")
                        print(f"    姓名: {u.get('display_name', '--')}")
                        print(f"    用户名: {u.get('username', '--')}")
                        print(f"    角色: {colorize(u.get('role', '--'), C.MAGENTA)}")
                        print()
                    else:
                        print(colorize("  请先登录。", C.YELLOW))
                elif cmd == "/tasks":
                    if not client.user:
                        print(colorize("  请先登录。", C.YELLOW))
                        continue
                    result = client.get_tasks()
                    t_data = client.get_received_tickets(status="open")
                    received = t_data.get("tickets", []) if "error" not in t_data else []
                    if "error" in result:
                        print(colorize(f"  ✗ {result['error']}", C.RED))
                    else:
                        tasks = result.get("tasks", [])
                        if not tasks and not received:
                            print(colorize("  ✅ 暂无待处理任务和工单。", C.GREEN))
                        else:
                            if tasks:
                                print(f"\n  {colorize('📋 待处理CLI任务：', C.BOLD)}")
                                for t in tasks:
                                    print(f"    {colorize(t.get('task_id', ''), C.CYAN)} [{t.get('priority', '')}] {t.get('title', '')}")
                            if received:
                                print(f"\n  {colorize('📋 交给我的工单：', C.BOLD)}")
                                for t in received:
                                    prio = " 🔴紧急" if t.get("priority") == "urgent" else " 🟡高" if t.get("priority") == "high" else ""
                                    print(f"    🟡 {colorize(t.get('ticket_no', ''), C.CYAN)} {t.get('title', '')}{prio}")
                                    print(f"       分类:{t.get('category','')} | 提交人:{t.get('submitter','')} | 时间:{t.get('created_at','')}")
                            print()
                elif cmd == "/task":
                    if not client.user:
                        print(colorize("  请先登录。", C.YELLOW))
                        continue
                    sp = args.split(maxsplit=1)
                    sub = sp[0] if sp else ""
                    subargs = sp[1] if len(sp) > 1 else ""
                    if sub == "exec":
                        print(colorize("  🤖 处理中...", C.DIM))
                        results = client.exec_tasks()
                        if not results:
                            print(colorize("  ✅ 暂无任务。", C.GREEN))
                        else:
                            for r in results:
                                if r.get("action") == "human_required":
                                    print(f"  ⚠️ 需人工处理: {r.get('task', {}).get('title', '')}")
                                else:
                                    s = "✅" if r.get("success") else "❌"
                                    print(f"  {s} {r.get('message', '')}")
                        print()
                    elif sub == "done":
                        if not subargs:
                            print(colorize("  用法: /task done <id>", C.YELLOW))
                            print(colorize("  id 可以是任务ID(CT-)或工单号(TK)", C.DIM))
                            continue
                        done_id = subargs.strip()
                        if done_id.upper().startswith("TK"):
                            result = client.close_ticket(done_id)
                            if "error" in result:
                                print(colorize(f"  ✗ {result.get('error', '失败')}", C.RED))
                            else:
                                print(colorize(f"  ✅ 工单 {done_id} 已关闭。", C.GREEN))
                        else:
                            result = client.mark_task_done(done_id)
                            if result.get("success"):
                                print(colorize(f"  ✅ 已完成。", C.GREEN))
                            else:
                                print(colorize(f"  ✗ {result.get('error', '失败')}", C.RED))
                    elif sub == "info":
                        if not subargs:
                            print(colorize("  用法: /task info <任务ID或工单号>", C.YELLOW))
                            print(colorize("  示例: /task info CT-20260608175709-0cedb1 | /task info TK20260616175", C.DIM))
                            continue
                        info_id = subargs.strip()
                        if info_id.upper().startswith("TK"):
                            # 工单详情
                            result = client.get_ticket_detail(info_id)
                            if "error" in result:
                                print(colorize(f"  ✗ {result.get('error', '无法查看工单')}", C.RED))
                            else:
                                t = result.get("ticket", {})
                                status_icons = {"open": "🟡待处理", "processing": "🔵处理中", "done": "✅已完成", "cancelled": "🚫已撤销"}
                                prio_colors = {"urgent": C.RED, "high": C.YELLOW, "normal": C.DIM}
                                prio_color = prio_colors.get(t.get("priority", "normal"), C.DIM)
                                status_icon = status_icons.get(t.get("status", ""), "⚪")
                                print(f"\n  {colorize('━━━ 工单详情 ━━━', C.BOLD)}")
                                print(f"  {colorize('工单号:', C.CYAN)}     {t.get('ticket_no', '--')}")
                                print(f"  {colorize('标题:', C.CYAN)}       {t.get('title', '--')}")
                                print(f"  {colorize('分类:', C.CYAN)}       {t.get('category', '--')}")
                                print(f"  {colorize('优先级:', C.CYAN)}     {colorize(t.get('priority', '--'), prio_color)}")
                                print(f"  {colorize('状态:', C.CYAN)}       {status_icon}")
                                print(f"  {colorize('提交人:', C.CYAN)}     {t.get('submitter', '--')}")
                                assignee = t.get('assignee', '')
                                if assignee:
                                    print(f"  {colorize('处理人:', C.CYAN)}     {assignee}")
                                else:
                                    print(f"  {colorize('处理人:', C.CYAN)}     待分派")
                                print(f"  {colorize('创建时间:', C.CYAN)}   {t.get('created_at', '--')}")
                                if t.get('updated_at'):
                                    print(f"  {colorize('更新时间:', C.CYAN)}   {t.get('updated_at')}")
                                if t.get('resolved_at'):
                                    print(f"  {colorize('完成时间:', C.CYAN)}   {t.get('resolved_at')}")
                                desc = t.get('description', '')
                                if desc:
                                    print(f"  {colorize('描述:', C.CYAN)}       {desc}")
                                print(f"  {colorize('━━━━━━━━━━━━━━━━', C.BOLD)}")
                            continue
                        result = client.get_task_detail(info_id)
                        if "error" in result:
                            print(colorize(f"  ✗ {result.get('error', '任务不存在')}", C.RED))
                        else:
                            t = result.get("task", {})
                            prio_colors = {"urgent": C.RED, "high": C.YELLOW, "normal": C.DIM}
                            prio_color = prio_colors.get(t.get("priority", "normal"), C.DIM)
                            print(f"\n  {colorize('━━━ 任务详情 ━━━', C.BOLD)}")
                            print(f"  {colorize('任务ID:', C.CYAN)}   {t.get('task_id', '--')}")
                            print(f"  {colorize('标题:', C.CYAN)}     {t.get('title', '--')}")
                            print(f"  {colorize('优先级:', C.CYAN)}   {colorize(t.get('priority', '--'), prio_color)}")
                            print(f"  {colorize('状态:', C.CYAN)}     {t.get('status', '--')}")
                            print(f"  {colorize('目标角色:', C.CYAN)} {t.get('target_role', '--')}")
                            if t.get('target_username'):
                                print(f"  {colorize('目标用户:', C.CYAN)} {t.get('target_username')}")
                            print(f"  {colorize('创建时间:', C.CYAN)} {t.get('created_at', '--')}")
                            if t.get('claimed_at'):
                                print(f"  {colorize('认领时间:', C.CYAN)} {t.get('claimed_at')}")
                            if t.get('completed_at'):
                                print(f"  {colorize('完成时间:', C.CYAN)} {t.get('completed_at')}")
                            desc = t.get('description', '')
                            if desc:
                                print(f"  {colorize('描述:', C.CYAN)}     {desc}")
                            skill = t.get('skill_name', '')
                            if skill:
                                print(f"  {colorize('关联技能:', C.CYAN)} {skill}")
                            context = t.get('context', {})
                            if context:
                                print(f"  {colorize('上下文:', C.CYAN)}   ", end="")
                                for k, v in context.items():
                                    print(f"{k}={v} ", end="")
                                print()
                            result_text = t.get('result', '')
                            if result_text:
                                print(f"  {colorize('执行结果:', C.CYAN)} {result_text[:200]}")
                            print(f"  {colorize('━━━━━━━━━━━━━━━━', C.BOLD)}")
                    else:
                        print(colorize("  用法: /task exec | /task done <id> | /task info <CT-xxx>", C.YELLOW))
                elif cmd == "/change" and args.strip() == "password":
                    if not client.user:
                        print(colorize("  请先登录。", C.YELLOW))
                        continue
                    try:
                        old_pwd = _input_password(f"  {colorize('当前密码:', C.CYAN)} ")
                        if not old_pwd:
                            print(colorize("  已取消。", C.DIM))
                            continue
                        new_pwd = _input_password(f"  {colorize('新密码:', C.CYAN)} ")
                        if not new_pwd:
                            print(colorize("  已取消。", C.DIM))
                            continue
                        if len(new_pwd) < 4:
                            print(colorize("  ✗ 密码长度至少4位。", C.RED))
                            continue
                        confirm_pwd = _input_password(f"  {colorize('确认新密码:', C.CYAN)} ")
                        if new_pwd != confirm_pwd:
                            print(colorize("  ✗ 两次输入的新密码不一致。", C.RED))
                            continue
                        print(colorize("  提交中...", C.DIM), end="", flush=True)
                        result = client.change_password(old_pwd, new_pwd)
                        print("\r" + " " * 20 + "\r", end="")
                        if "error" in result:
                            print(colorize(f"  ✗ {result['error']}", C.RED))
                        else:
                            print(colorize("  ✅ 密码修改成功！", C.GREEN))
                    except (EOFError, KeyboardInterrupt):
                        print()
                        print(colorize("  已取消。", C.DIM))
                elif cmd == "/my" and args.strip().lower() == "ticket":
                    # /my ticket - 查看我提的工单
                    if not client.user:
                        print(colorize("  请先登录。", C.YELLOW))
                        continue
                    result = client._request("GET", "/api/tickets", {"view": "submitted"})
                    if "error" in result:
                        print(colorize(f"  ✗ {result['error']}", C.RED))
                    else:
                        tickets = result.get("tickets", [])
                        if not tickets:
                            print(colorize("  📋 暂无工单。", C.GREEN))
                        else:
                            status_icons = {"open": "🟡待处理", "processing": "🔵处理中", "done": "✅已完成", "cancelled": "🚫已撤销"}
                            print(f"\n  {colorize('📋 我提的工单：', C.BOLD)}")
                            for t in tickets:
                                icon = status_icons.get(t.get("status", ""), "⚪")
                                prio = " 🔴紧急" if t.get("priority") == "urgent" else " 🟡高" if t.get("priority") == "high" else ""
                                print(f"    {icon} {colorize(t.get('ticket_no', ''), C.CYAN)} {t.get('title', '')}{prio}")
                                assignee = t.get('assignee', '')
                                if assignee:
                                    print(f"       处理人:{assignee} | 时间:{t.get('created_at','')}")
                                else:
                                    print(f"       待分派 | 时间:{t.get('created_at','')}")
                            print()
                elif cmd == "/ticket" and args.strip().startswith("cancel"):
                    # /ticket cancel <TK> - 撤销我提的工单
                    cancel_args = args.strip()[6:].strip()
                    if not cancel_args:
                        print(colorize("  用法: /ticket cancel <工单号>", C.YELLOW))
                        print(colorize("  示例: /ticket cancel TK20260608119", C.DIM))
                        continue
                    if not cancel_args.upper().startswith("TK"):
                        print(colorize("  ✗ 请输入正确的工单号（TK开头）。", C.RED))
                        continue
                    if not client.user:
                        print(colorize("  请先登录。", C.YELLOW))
                        continue
                    result = client.cancel_ticket(cancel_args)
                    if "error" in result:
                        print(colorize(f"  ✗ {result.get('error', '失败')}", C.RED))
                    else:
                        print(colorize(f"  ✅ 工单 {cancel_args} 已撤销。", C.GREEN))
                elif cmd == "/ticket":
                    if not client.user:
                        print(colorize("  请先登录。", C.YELLOW))
                        continue
                    try:
                        print(colorize("  ── 提交工单 ──", C.BOLD))
                        title = input(f"  {colorize('标题:', C.CYAN)} ").strip()
                        if not title:
                            print(colorize("  已取消。", C.DIM))
                            continue
                        print(f"  {colorize('分类:', C.CYAN)} ", end="")
                        print(colorize("1.一般 2.薪酬 3.社保 4.合同 5.招聘 6.其他", C.DIM))
                        cat_input = input(f"  {colorize('选择(回车默认1):', C.CYAN)} ").strip()
                        cat_map = {"1": "一般", "2": "薪酬", "3": "社保", "4": "合同", "5": "招聘", "6": "其他",
                                   "一般": "一般", "薪酬": "薪酬", "社保": "社保", "合同": "合同", "招聘": "招聘", "其他": "其他"}
                        category = cat_map.get(cat_input, "一般")
                        description = input(f"  {colorize('内容描述:', C.CYAN)} ").strip()
                        print(f"  {colorize('优先级:', C.CYAN)} ", end="")
                        print(colorize("1.普通 2.紧急 3.非常紧急", C.DIM))
                        pri_input = input(f"  {colorize('选择(回车默认1):', C.CYAN)} ").strip()
                        pri_map = {"1": "normal", "2": "high", "3": "urgent",
                                   "普通": "normal", "紧急": "high", "非常紧急": "urgent"}
                        priority = pri_map.get(pri_input, "normal")
                        print(colorize("  提交中...", C.DIM), end="", flush=True)
                        result = client.create_ticket(title, category, description, priority)
                        print("\r" + " " * 20 + "\r", end="")
                        if "error" in result:
                            print(colorize(f"  ✗ 提交失败: {result['error']}", C.RED))
                        else:
                            ticket_no = result.get("ticket_no", "")
                            print(colorize(f"  ✅ 工单创建成功！工单号: {ticket_no}", C.GREEN))
                            print(colorize(f"  ⏳ 正在等待大脑分析并分派...", C.DIM))
                            # 轮询等待大脑完成分派（最多20秒）
                            assigned = False
                            for _ in range(10):
                                time.sleep(2)
                                try:
                                    t_data = client._request("GET", "/api/tickets", {"view": "submitted", "status": "open"})
                                    tickets = t_data.get("tickets", [])
                                    found = [t for t in tickets if t.get("ticket_no") == ticket_no]
                                    if found and found[0].get("assignee"):
                                        assignee = found[0]["assignee"]
                                        print(colorize(f"  📋 工单已分派给: {assignee}", C.GREEN))
                                        print(colorize(f"  💡 对方可在 /tasks 中查看此工单", C.DIM))
                                        assigned = True
                                        break
                                except Exception:
                                    pass
                            if not assigned:
                                print(colorize(f"  ⏳ 分派中...（大脑正在分析，可稍后查看）", C.DIM))
                    except (EOFError, KeyboardInterrupt):
                        print()
                        print(colorize("  已取消。", C.DIM))
                elif cmd == "/chat":
                    if not client.user:
                        print(colorize("  请先登录。", C.YELLOW))
                        continue
                    if not args:
                        print(colorize("  用法: /chat <姓名或用户名>", C.YELLOW))
                        continue
                    if _chat_state["session_id"]:
                        print(colorize(f"  ⚠️ 你正在与{_chat_state['target']}聊天中，请先 /exit chat", C.YELLOW))
                        continue
                    target = args.strip()
                    # 通过服务端查找用户名（target可能是显示名）
                    result = client.start_realtime_chat(target)
                    if "error" in result:
                        print(colorize(f"  ✗ {result.get('error', '无法发起对话')}", C.RED))
                        continue
                    sid = result.get("session_id", "")
                    if not sid:
                        print(colorize("  ✗ 无法创建聊天会话。", C.RED))
                        continue
                    _chat_state["session_id"] = sid
                    _chat_state["target"] = target
                    _chat_state["is_initiator"] = True  # 主动发起聊天
                    _start_chat_poll(client, sid)
                    print(colorize(f"  📨 已进入与 {target} 的实时聊天模式", C.GREEN))
                    print(colorize(f"  💬 直接输入消息即可发送，输入 /exit chat 结束", C.DIM))
                elif cmd == "/exit" and args.strip() == "chat":
                    if not _chat_state["session_id"]:
                        print(colorize("  当前没有活跃的聊天。", C.DIM))
                        continue
                    target_name = _chat_state["target"]
                    # 不关闭服务端会话——让接收方有机会登录后查看离线消息
                    # 仅在接收方也退出时才关闭（通过会话中消息都已读取判断）
                    # 先检查：如果我是接收方（非发起人），且所有消息都已读，可以关闭
                    is_initiator = _chat_state.get("is_initiator", False)
                    if not is_initiator:
                        # 接收方退出时关闭会话（表示双方都已看过消息）
                        client.close_realtime_chat(_chat_state["session_id"])
                        print(colorize(f"  💬 与 {target_name} 的对话已结束。聊天记录已保存到服务器。", C.GREEN))
                    else:
                        # 发起方退出时：保留会话，启动被动监控，对方回复时通知
                        _chat_state["preserved_session_id"] = _chat_state["session_id"]
                        _chat_state["preserved_target"] = target_name
                        _start_passive_poll(client, _chat_state["session_id"], target_name)
                        _chat_state["session_id"] = None  # 退出活跃聊天模式
                        _chat_state["target"] = None
                        _chat_state["is_initiator"] = False
                        print(colorize(f"  💬 已退出与 {target_name} 的聊天。后台监控中，对方回复会通知你。", C.GREEN))
                elif cmd == "/logout":
                    if _chat_state["session_id"]:
                        # 与 /exit chat 逻辑一致：发起方不关闭服务端会话
                        if not _chat_state.get("is_initiator", False):
                            client.close_realtime_chat(_chat_state["session_id"])
                    _reset_chat_state()
                    _stop_invite_watch()
                    client.logout()
                    print(colorize("  已登出。", C.GREEN))
                    if not do_login(client):
                        break
                else:
                    print(colorize(f"  未知命令: {cmd}，输入 /help", C.YELLOW))
                continue
            # 普通消息 → 判断是聊天模式还是大脑对话
            if not client.user:
                print(colorize("  请先登录。", C.YELLOW))
                continue
            # 被动监控模式：输入 'r' 重新进入聊天
            if user_input.lower() == "r" and _chat_state.get("preserved_session_id") and _chat_state.get("pending_after_exit"):
                # 停止被动轮询，切换回活跃聊天模式
                if _chat_state.get("poll_stop"):
                    _chat_state["poll_stop"].set()
                _chat_state["session_id"] = _chat_state["preserved_session_id"]
                _chat_state["target"] = _chat_state["preserved_target"]
                _chat_state["is_initiator"] = True
                _chat_state["preserved_session_id"] = None
                _chat_state["preserved_target"] = None
                _chat_state["pending_after_exit"] = False
                # 启动活跃轮询
                _start_chat_poll(client, _chat_state["session_id"], reset_last_id=False)
                print(colorize(f"  📨 重新进入与 {_chat_state['target']} 的聊天模式", C.GREEN))
                print(colorize(f"  💬 直接输入消息即可发送，输入 /exit chat 结束", C.DIM))
                continue
            # 聊天模式：消息发送给对方
            if _chat_state["session_id"]:
                result = client.send_chat_msg(_chat_state["session_id"], user_input)
                if "error" in result:
                    print(colorize(f"  ✗ 发送失败: {result['error']}", C.RED))
                else:
                    print(colorize("  ✓ 已发送", C.DIM))
                    print(colorize(f"  💡 提示：当前处于与 {_chat_state['target']} 的聊天模式，输入 /exit chat 退出后可与大脑对话", C.DIM))
                continue
            # 普通模式：消息发给大脑（流式输出）
            try:
                print(f"\n{colorize('🧬 SSC回复：', C.MAGENTA + C.BOLD)}")
                raw_chunks = ""
                done_response = None
                has_secretary_task = False
                for event_type, data in client.chat_stream(user_input):
                    if event_type == "chunk":
                        raw_chunks += data
                        # 检测是否包含秘书任务标记（死格式：中文书名号包裹）
                        if "【秘书任务】" in raw_chunks and not has_secretary_task:
                            has_secretary_task = True
                            # 显示初始思考摘要（用正则剥离秘书任务标记及后续内容）
                            import re as _re
                            initial_thinking = _re.sub(r'【秘书任务】[\s\S]*', '', raw_chunks).strip()
                            if initial_thinking:
                                print(initial_thinking, flush=True)
                            print(f"\n{colorize('  📋 正在采集补充信息...', C.DIM)}", flush=True)
                        elif not has_secretary_task:
                            # 无秘书任务，正常逐token输出
                            print(data, end="", flush=True)
                    elif event_type == "status":
                        print(f"\r{colorize(f'  {data}', C.DIM)}", flush=True)
                    elif event_type == "done":
                        done_response = data
                    elif event_type == "error":
                        print(f"\n{colorize(f'  ❌ {data}', C.RED)}")
                        break
                # 最终回复显示
                if done_response and done_response.strip():
                    if has_secretary_task:
                        # 秘书补充后的大脑重新生成回复，直接显示最终版本
                        print(done_response)
                    else:
                        # 无秘书任务，流式输出已是最终版本
                        # done_response 可能是清理后的版本，检查是否与流式输出不同
                        clean_raw = _clean_response_markers(raw_chunks)
                        if done_response.strip() != clean_raw:
                            print(f"\n\n{colorize('━━━ 最终回复（已补充完整信息）━━━', C.GREEN + C.BOLD)}")
                            print(done_response)
                print()  # 结束后换行
            except KeyboardInterrupt:
                print(colorize("\n  ⚠️ 用户中断。", C.YELLOW))
            except Exception as e:
                print(colorize(f"\n  ❌ 对话异常: {str(e)[:200]}", C.RED))
                print(colorize(f"  💡 您可以继续输入其他消息。", C.DIM))
        except KeyboardInterrupt:
            print(colorize("\n\n  再见！🧬\n", C.DIM))
            break
        except EOFError:
            break


def do_login(client):
    print(colorize("请登录", C.BOLD))
    print(colorize("─" * 40, C.DIM))
    for attempt in range(3):
        try:
            username = input(f"  {colorize('用户名:', C.CYAN)} ").strip()
            if not username:
                continue
            try:
                password = _input_password(f"  {colorize('密  码:', C.CYAN)} ")
            except (EOFError, Exception):
                password = input(f"  {colorize('密  码:', C.CYAN)} ")
            print(colorize("  验证中...", C.DIM), end="", flush=True)
            if client.login(username, password):
                print("\r" + " " * 20 + "\r", end="")
                print(colorize(f"  ✓ 欢迎 {client.user['display_name']}（{client.user['role']}）", C.GREEN))
                print()
                client.sync_skills()
                return True
            else:
                print("\r" + " " * 20 + "\r", end="")
                remaining = 2 - attempt
                if remaining > 0:
                    print(colorize(f"  还剩 {remaining} 次", C.YELLOW))
        except KeyboardInterrupt:
            print()
            return False
        except EOFError:
            return False
    return False


def main():
    parser = argparse.ArgumentParser(description="SSC员工终端")
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    args = parser.parse_args()

    if sys.platform == "win32":
        try:
            os.system("")
        except Exception:
            C.disable()

    print_banner()
    client = SSCClient(args.server)
    print(f"  服务器: {colorize(args.server, C.CYAN)}\n")

    if args.user and args.password:
        if client.login(args.user, args.password):
            print(colorize(f"  ✓ {client.user['display_name']}（{client.user['role']}）", C.GREEN))
            client.sync_skills()
        else:
            if not do_login(client):
                return
    else:
        if not do_login(client):
            return
    interactive_loop(client)


if __name__ == "__main__":
    main()