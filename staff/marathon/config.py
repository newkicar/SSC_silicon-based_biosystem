"""
Marathon Agent 配置常量
"""
from pathlib import Path

# ==================== 重试控制 ====================
MAX_RETRIES_PER_STEP = 3
MAX_GLOBAL_RETRIES = 10
RETRY_WAIT_SECONDS = [3, 10, 20]

# ==================== 超时控制 ====================
STEP_TIMEOUT_SECONDS = 600
TOTAL_TIMEOUT_SECONDS = 7200
VALIDATOR_TIMEOUT_SECONDS = 120

# ==================== 上下文管理 ====================
CONTEXT_TOKEN_THRESHOLD = 6000

# ==================== 持久化 ====================
MARATHON_STATE_DIR = ".marathon"
PROGRESS_FILENAME = "PROGRESS.md"
STATE_FILENAME = "state.json"

# ==================== Human-in-the-Loop ====================
HITL_PLAN_REVIEW = False  # Sprint 1: 先不暂停确认，直接执行
HITL_ON_MAX_RETRIES = True
HITL_ON_TIMEOUT = True

# ==================== 步骤状态常量 ====================
STEP_PENDING = "pending"
STEP_EXECUTING = "executing"
STEP_DONE = "done"
STEP_FAILED = "failed"
STEP_SKIPPED = "skipped"
STEP_WAITING = "waiting"

# ==================== Marathon 整体状态 ====================
MARATHON_PLANNING = "planning"
MARATHON_EXECUTING = "executing"
MARATHON_PAUSED = "paused"
MARATHON_DONE = "done"
MARATHON_FAILED = "failed"
MARATHON_CANCELLED = "cancelled"