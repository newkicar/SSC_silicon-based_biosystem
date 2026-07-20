"""
角色Agent —— 员工终端的AI执行层

每个SSC操作角色登录终端后，自动成为一个AI Agent：
1. 接收大脑分派的任务（从cli_tasks队列）
2. 检查自己是否有匹配的本地skill可以自动执行
3. 有skill → 自动执行，返回结果
4. 无skill → 提示人类手动处理

注意：Skill从 staff/skills/ 目录加载（由 skill_sync 从服务端同步）
"""
import sys
import os
import json
import re
import importlib.util
from datetime import datetime
from pathlib import Path

# 确保项目根目录在Python路径中
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.data.cli_tasks import (
    get_pending_tasks_for_role,
    claim_cli_task,
    update_cli_task_status,
    get_task_by_id,
)

# 本地 Skill 目录
STAFF_SKILLS_DIR = str(Path(__file__).resolve().parent / "skills")


def _load_local_skills(role_name: str) -> list:
    """从 staff/skills/ 加载当前角色可用的 Skill"""
    skills = []
    skills_dir = Path(STAFF_SKILLS_DIR)
    if not skills_dir.exists():
        return skills

    for item in skills_dir.iterdir():
        if not item.is_dir() or item.name.startswith("_") or item.name.startswith("."):
            continue
        skill_md_path = item / "SKILL.md"
        if not skill_md_path.exists():
            continue
        try:
            content = skill_md_path.read_text(encoding="utf-8")
            # 简单解析 frontmatter
            fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if not fm_match:
                continue
            fm_text = fm_match.group(1)
            meta = {}
            for line in fm_text.split('\n'):
                kv = re.match(r'^(\w[\w_]*)\s*:\s*(.*)', line.strip())
                if kv:
                    meta[kv.group(1)] = kv.group(2).strip().strip('"').strip("'")
            
            # 检查 target_roles
            target_roles = []
            in_roles = False
            for line in fm_text.split('\n'):
                stripped = line.strip()
                if stripped.startswith('target_roles:'):
                    in_roles = True
                    continue
                if in_roles:
                    if stripped.startswith('- '):
                        target_roles.append(stripped[2:].strip().strip('"').strip("'"))
                    elif ':' in stripped and not stripped.startswith(' '):
                        in_roles = False
            
            if role_name not in target_roles and target_roles:
                continue

            skill_name = meta.get("name", item.name)
            display_name = meta.get("display_name", skill_name)
            
            # 检查是否有 scripts/ 目录
            scripts_dir = item / "scripts"
            scripts = []
            if scripts_dir.exists():
                scripts = [f for f in scripts_dir.iterdir() if f.suffix == '.py']

            skills.append({
                "name": skill_name,
                "display_name": display_name,
                "description": meta.get("description", ""),
                "dir": str(item),
                "scripts": [str(s) for s in scripts],
            })
        except Exception as e:
            print(f"[角色Agent] 加载 Skill {item.name} 失败: {e}")

    return skills


def _find_skill_by_name(skills: list, name: str) -> dict:
    """在本地 skill 列表中按名称查找"""
    for s in skills:
        if s["name"] == name:
            return s
    return None


def _find_skill_by_keyword(skills: list, task: dict) -> dict:
    """通过任务关键词推断匹配的 skill"""
    title = task.get("title", "")
    description = task.get("description", "")
    context_text = f"{title} {description}".lower()

    for s in skills:
        skill_name = s["name"].lower()
        skill_desc = s.get("description", "").lower()
        # 简单关键词匹配
        if skill_name.replace("-", "").replace("_", "") in context_text.replace(" ", ""):
            return s
        # 检查 skill 描述中的关键词是否在任务中出现
        for keyword in re.findall(r'[\u4e00-\u9fff]+', skill_desc):
            if len(keyword) >= 2 and keyword in context_text:
                return s
    return None


class RoleAgent:
    """
    角色Agent —— SSC操作人员的本地AI助手
    
    职责：
    1. 轮询自己角色的任务队列
    2. 认领并尝试自动执行任务
    3. 无法自动执行的任务，提示人类处理
    """
    
    def __init__(self, role_name: str, username: str, display_name: str):
        self.role_name = role_name
        self.username = username
        self.display_name = display_name
        self.skills = _load_local_skills(role_name)
        
    def get_status(self) -> dict:
        """获取当前Agent状态"""
        pending = get_pending_tasks_for_role(self.role_name, self.username)
        return {
            "role": self.role_name,
            "username": self.username,
            "display_name": self.display_name,
            "available_skills": [s["name"] for s in self.skills],
            "pending_tasks_count": len(pending),
        }
    
    def poll_tasks(self) -> list:
        """轮询待处理任务"""
        tasks = get_pending_tasks_for_role(self.role_name, self.username)
        return tasks
    
    def process_task(self, task_id: str) -> dict:
        """
        处理一个任务。
        
        流程：
        1. 认领任务
        2. 检查是否有匹配skill
        3. 有skill → 执行skill（本地运行 scripts）
        4. 无skill → 提示人类
        """
        task = get_task_by_id(task_id)
        if not task:
            return {"success": False, "message": f"任务 {task_id} 不存在"}
        
        # 认领任务
        claim_result = claim_cli_task(task_id, self.username)
        if not claim_result["success"]:
            return {"success": False, "message": f"任务 {task_id} 认领失败（可能已被他人认领）"}
        
        print(f"\n[角色Agent-{self.display_name}] 已认领任务: {task['title']}")
        
        # 检查是否有匹配skill
        skill_name = task.get("skill_name", "")
        skill_params = task.get("skill_params", {})
        
        if skill_name:
            skill = _find_skill_by_name(self.skills, skill_name)
            if skill:
                print(f"[角色Agent-{self.display_name}] 发现匹配技能: {skill['display_name']}，自动执行...")
                return self._execute_skill(task_id, skill, skill_params)
        
        # 没有明确skill_name，尝试从任务信息推断
        inferred_skill = _find_skill_by_keyword(self.skills, task)
        if inferred_skill:
            print(f"[角色Agent-{self.display_name}] 推断匹配技能: {inferred_skill['display_name']}，自动执行...")
            context = task.get("context", {})
            return self._execute_skill(task_id, inferred_skill, context)
        
        # 无skill可用，提示人类
        print(f"[角色Agent-{self.display_name}] 无可用技能，需人工处理。")
        update_cli_task_status(task_id, "claimed", "等待人工处理")
        
        return {
            "success": True,
            "action": "human_required",
            "message": self._format_human_prompt(task),
            "task": task,
        }
    
    def _execute_skill(self, task_id: str, skill: dict, params: dict) -> dict:
        """在本地执行一个 skill 的脚本"""
        import subprocess
        
        try:
            skill_name = skill["name"]
            scripts = skill.get("scripts", [])
            
            if not scripts:
                # 没有脚本，只读取 SKILL.md 提示人工
                return {
                    "success": True,
                    "action": "human_required",
                    "message": f"技能 '{skill_name}' 暂无可执行脚本，请手动参照 {skill['dir']}/SKILL.md 处理。",
                }
            
            # 执行第一个脚本（主脚本）
            main_script = scripts[0]
            params_json = json.dumps(params, ensure_ascii=False)
            
            print(f"[角色Agent-{self.display_name}] 执行脚本: {main_script}")
            print(f"[角色Agent-{self.display_name}] 参数: {params_json}")
            
            # 通过 subprocess 执行脚本，传入参数
            result = subprocess.run(
                [sys.executable, main_script, "--params", params_json],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=skill["dir"],
            )
            
            if result.returncode == 0:
                # 尝试解析 JSON 输出
                output = result.stdout.strip()
                try:
                    skill_result = json.loads(output)
                except json.JSONDecodeError:
                    skill_result = {"success": True, "message": output or "执行完成"}
                
                print(f"[角色Agent-{self.display_name}] ✅ 技能执行成功: {skill_result.get('message', '')}")
                update_cli_task_status(task_id, "completed", json.dumps(skill_result, ensure_ascii=False))
                return skill_result
            else:
                error_msg = result.stderr.strip() or result.stdout.strip() or "执行失败"
                print(f"[角色Agent-{self.display_name}] ❌ 技能执行失败: {error_msg}")
                update_cli_task_status(task_id, "failed", error_msg)
                return {"success": False, "message": error_msg}
            
        except subprocess.TimeoutExpired:
            error_msg = "脚本执行超时（60秒）"
            print(f"[角色Agent-{self.display_name}] ❌ {error_msg}")
            update_cli_task_status(task_id, "failed", error_msg)
            return {"success": False, "message": error_msg}
        except Exception as e:
            error_msg = f"技能执行异常: {e}"
            print(f"[角色Agent-{self.display_name}] ❌ {error_msg}")
            update_cli_task_status(task_id, "failed", error_msg)
            return {"success": False, "message": error_msg}
    
    def _format_human_prompt(self, task: dict) -> str:
        """格式化人类提示信息"""
        lines = [
            f"{'='*50}",
            f"📋 新任务待处理",
            f"{'='*50}",
            f"任务ID: {task.get('task_id', '')}",
            f"标题: {task.get('title', '')}",
            f"优先级: {task.get('priority', 'normal')}",
            f"描述: {task.get('description', '')}",
        ]
        
        context = task.get("context", {})
        if context:
            lines.append(f"上下文: {json.dumps(context, ensure_ascii=False, indent=2)}")
        
        lines.append(f"{'='*50}")
        lines.append(f"⚠️  该任务无可用自动技能，请手动处理。")
        lines.append(f"处理完成后，请执行: /task done {task.get('task_id', '')}")
        
        return "\n".join(lines)


def create_role_agent(role_name: str, username: str, display_name: str) -> RoleAgent:
    """创建角色Agent"""
    return RoleAgent(role_name, username, display_name)


def auto_process_tasks_for_role(role_name: str, username: str, display_name: str) -> list:
    """
    自动处理某个角色的所有待处理任务。
    返回处理结果列表。
    """
    agent = create_role_agent(role_name, username, display_name)
    tasks = agent.poll_tasks()
    
    results = []
    for task in tasks:
        task_id = task["task_id"]
        result = agent.process_task(task_id)
        results.append({"task_id": task_id, **result})
    
    return results