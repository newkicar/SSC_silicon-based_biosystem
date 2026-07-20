"""
Marathon Agent 状态定义 + 持久化读写

核心理念：状态外置——不依赖LLM上下文，而是写入文件系统和数据库。
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime

from .config import (
    STEP_PENDING, STEP_EXECUTING, STEP_DONE, STEP_FAILED, STEP_SKIPPED, STEP_WAITING,
    MARATHON_PLANNING, MARATHON_EXECUTING, MARATHON_PAUSED, MARATHON_DONE, MARATHON_FAILED,
    MARATHON_STATE_DIR, PROGRESS_FILENAME, STATE_FILENAME
)


@dataclass
class SubTask:
    """单个子步骤"""
    id: int
    description: str
    acceptance_criteria: str
    status: str = STEP_PENDING
    action_type: str = ""
    capability: str = ""
    error_log: str = ""
    error_history: List[str] = field(default_factory=list)
    git_commit: str = ""
    attempts: int = 0
    result_summary: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SubTask":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ValidationResult:
    """验证结果"""
    passed: Optional[bool]  # True=通过, False=失败, None=需要人类判断
    level: str              # existence / business_action / consistency / unknown
    error: str = ""
    details: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ValidationResult":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class MarathonState:
    """Marathon Agent 的完整状态"""
    marathon_id: str = ""
    task_description: str = ""
    username: str = ""
    display_name: str = ""

    plan: List[SubTask] = field(default_factory=list)
    current_step_index: int = 0
    current_validation: Optional[ValidationResult] = None

    step_error_count: int = 0
    global_error_count: int = 0

    context_summary: str = ""
    execution_log: List[str] = field(default_factory=list)

    status: str = MARATHON_PLANNING
    is_complete: bool = False
    requires_human: bool = False
    human_message: str = ""

    created_at: str = ""
    updated_at: str = ""
    completed_at: str = ""
    started_at: str = ""
    state_dir: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
        if not self.marathon_id:
            self.marathon_id = f"marathon-{int(time.time())}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["plan"] = [s.to_dict() for s in self.plan]
        if self.current_validation:
            d["current_validation"] = self.current_validation.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "MarathonState":
        state = cls()
        for k, v in d.items():
            if k == "plan":
                state.plan = [SubTask.from_dict(s) for s in v] if v else []
            elif k == "current_validation" and v:
                state.current_validation = ValidationResult.from_dict(v)
            elif hasattr(state, k):
                setattr(state, k, v)
        return state

    def get_current_step(self) -> Optional[SubTask]:
        if 0 <= self.current_step_index < len(self.plan):
            return self.plan[self.current_step_index]
        return None

    def get_progress_text(self) -> str:
        lines = [
            "# Marathon 进度报告", "",
            f"## 任务：{self.task_description}",
            f"## 发起人：{self.display_name} ({self.username})",
            f"## 状态：{self.status}",
            f"## 创建时间：{self.created_at}",
            f"## 最后更新：{self.updated_at}", "", "## 步骤进度",
        ]
        for step in self.plan:
            icons = {
                STEP_PENDING: "○", STEP_EXECUTING: "⏳", STEP_DONE: "✅",
                STEP_FAILED: "❌", STEP_SKIPPED: "⏭", STEP_WAITING: "⏸"
            }
            icon = icons.get(step.status, "❓")
            cap_text = f" [{step.capability}]" if step.capability else ""
            line = f"- {icon} Step {step.id + 1}: {step.description}{cap_text}"
            if step.status == STEP_DONE and step.result_summary:
                line += f" — {step.result_summary}"
            elif step.status == STEP_FAILED and step.error_log:
                line += f" — 失败: {step.error_log[:80]}"
            elif step.status == STEP_WAITING:
                line += " — 等待中..."
            lines.append(line)

        done_count = sum(1 for s in self.plan if s.status == STEP_DONE)
        lines.append("")
        lines.append(f"**总进度**: {done_count}/{len(self.plan)} 步完成")

        if self.execution_log:
            lines.append("")
            lines.append("## 执行日志（最近10条）")
            for log in self.execution_log[-10:]:
                lines.append(f"- {log}")

        return "\n".join(lines)


# ==================== 持久化读写 ====================

def ensure_state_dir(marathon_id: str, project_root: str) -> str:
    state_dir = os.path.join(project_root, MARATHON_STATE_DIR, marathon_id)
    os.makedirs(state_dir, exist_ok=True)
    return state_dir


def save_state(state: MarathonState, state_dir: str = ""):
    if not state_dir:
        state_dir = state.state_dir
    if not state_dir:
        return
    state.updated_at = datetime.now().isoformat()
    state.state_dir = state_dir
    path = os.path.join(state_dir, STATE_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)


def load_state(state_dir: str) -> Optional[MarathonState]:
    path = os.path.join(state_dir, STATE_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        state = MarathonState.from_dict(data)
        state.state_dir = state_dir
        return state
    except Exception:
        return None


def save_progress(state: MarathonState):
    if not state.state_dir:
        return
    path = os.path.join(state.state_dir, PROGRESS_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write(state.get_progress_text())


def list_marathons(project_root: str) -> list:
    marathon_dir = os.path.join(project_root, MARATHON_STATE_DIR)
    if not os.path.exists(marathon_dir):
        return []
    results = []
    for name in sorted(os.listdir(marathon_dir), reverse=True):
        state_dir = os.path.join(marathon_dir, name)
        state_file = os.path.join(state_dir, STATE_FILENAME)
        if os.path.isfile(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                plan = data.get("plan", [])
                results.append({
                    "marathon_id": data.get("marathon_id", name),
                    "task_description": data.get("task_description", ""),
                    "status": data.get("status", "unknown"),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "progress": f"{sum(1 for s in plan if s.get('status') == 'done')}/{len(plan)}",
                    "state_dir": state_dir,
                })
            except Exception:
                continue
    return results