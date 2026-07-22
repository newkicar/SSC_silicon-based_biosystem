"""
SSC硅基生物系统 - FastAPI数据接口

提供三类API：
1. 认证接口（登录/登出/token验证）
2. Dashboard数据接口（花名册统计/招聘数据/考勤数据）
3. 智能问答接口（接入process_message）

启动方式：python -m src.api.server
访问地址：http://localhost:8000
API文档：http://localhost:8000/docs
"""

import sys
import os
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional


# ==================== 日志过滤：减少轮询噪音 ====================
class _AccessLogFilter(logging.Filter):
    """过滤高频轮询接口的access log，只保留有意义的请求"""

    _NOISY_PATHS = ("/api/realtime-chat/poll", "/api/realtime-chat/send")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for path in self._NOISY_PATHS:
            if path in msg:
                return False  # 不打印
        return True


# Windows GBK编码兼容：强制stdout使用UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        os.environ["PYTHONIOENCODING"] = "utf-8"

# 确保项目根目录在路径中
project_root = str(Path(__file__).resolve().parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    Header,
    Request,
    UploadFile,
    File,
    Form,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from src.security.auth import (
    init_auth_db,
    login,
    verify_token,
    logout,
    register_user,
    list_users,
    update_user_role,
    delete_user,
    get_user_by_username,
    create_default_admin,
    add_user_role,
    remove_user_role,
    get_user_roles_by_username,
)
from src.security.permissions import check_data_access, ROLE_PERMISSIONS
from src.security.seed_users import seed_default_users
from src.tools.data_sources import get_secretary
from src.tools.dashboard_data import get_dashboard_provider
from src.api.services import (
    init_ticket_tables,
    get_tickets,
    get_ticket_detail,
    create_ticket,
    update_ticket,
    cancel_ticket,
    done_ticket,
    transfer_ticket,
    get_ticket_transfers,
    get_notifications,
    create_notification,
    mark_notification_read,
    mark_notification_unread,
    mark_all_notifications_read,
    get_user_profile,
    update_user_profile,
    change_password,
    init_chat_tables,
    start_chat_session,
    send_chat_message,
    poll_chat_messages,
    close_chat_session,
    get_active_chat,
    get_pending_messages,
    mark_messages_delivered,
)
from src.data.skill_registry import (
    init_skill_registry,
    register_skill,
    get_all_skills,
    get_skill_by_name,
    update_skill_status,
    update_skill_roles,
    delete_skill,
    check_updates,
)

# ==================== 初始化 ====================
app = FastAPI(
    title="SSC硅基生物系统 API",
    description="HR SSC硅基生命体 — 数据接口",
    version="2.0.0",
)

# CORS（允许前端跨域调用）
# 注意：allow_origins=["*"] 与 allow_credentials=True 不兼容（CORS 规范）
# 前端通过 Bearer Token 在 Header 中传递认证信息，不需要 cookie/credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件服务（CSS/JS）
from fastapi.staticfiles import StaticFiles

app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "static")),
    name="static",
)


# 全局参数：是否强制更新向量索引（由命令行 --update 控制）
_force_update_index = False
_update_db_file = ""
_server_port = 8000
_server_host = "0.0.0.0"


@app.on_event("startup")
async def startup_event():
    """启动时初始化"""
    global _force_update_index
    # 应用日志过滤（减少实时聊天轮询的噪音）
    logging.getLogger("uvicorn.access").addFilter(_AccessLogFilter())
    init_auth_db()
    create_default_admin()
    print("[API] 认证数据库已初始化")
    # 预热缓存：加载所有Excel数据到内存
    provider = get_dashboard_provider()
    print("[API] 正在预热缓存...")
    provider.get_kpi_data()
    provider.get_chart_data()
    provider.get_efficiency_data()
    provider.get_overtime_data()
    provider.get_dept_detail_data()
    print("[API] 缓存预热完成！")
    # 初始化工单/通知表+示例数据
    init_ticket_tables()
    print("[API] 工单/通知系统已初始化")
    # 初始化CLI任务表
    from src.data.cli_tasks import init_cli_task_table

    init_cli_task_table()
    print("[API] CLI任务表已初始化")
    # 初始化即时通讯表
    init_chat_tables()
    print("[API] 即时通讯系统已初始化")
    # 初始化Skill注册中心
    init_skill_registry()
    print("[API] Skill注册中心已初始化")
    # 初始化统一数据层（task_bs / task_st / event_bus 表）
    from src.data.task_queue import init_task_tables
    init_task_tables()
    print("[API] 统一数据层表已初始化")
    # 初始化上下文池
    from src.data.context_pool import init_context_pool
    init_context_pool()
    print("[API] 上下文池已初始化")
    # 启动定时调度器（数据更新、洞察、记忆整理等）
    from src.scheduler.scheduler import Scheduler

    global _scheduler_instance
    _scheduler_instance = Scheduler()
    _scheduler_instance.start()
    print("[API] 定时调度器已启动")

    # 向量索引加载（--update 时强制重建，否则加载缓存）
    from src.tools.vector_rag import (
        build_index,
        rebuild_index,
        _load_db_index,
        rebuild_db_index,
        rebuild_db_index_file,
    )

    if _update_db_file:
        print(f"[API] --update-db 模式：只重建 {_update_db_file} 的索引...")
        rag_count = build_index()
        db_count = rebuild_db_index_file(_update_db_file)
        print(
            f"[API] 索引更新完成：RAG文档 {rag_count} 个切片，数据库增量更新 {db_count} 行"
        )
    elif _force_update_index:
        print("[API] --update 模式：正在强制重建全部向量索引...")
        rag_count = rebuild_index()
        db_count = rebuild_db_index()
        print(
            f"[API] 全量索引重建完成：RAG文档 {rag_count} 个切片，数据库 {db_count} 行数据"
        )
    else:
        print("[API] 正在加载向量索引...")
        rag_count = build_index()
        db_index = _load_db_index()
        db_count = len(db_index.get("documents", []))
        print(
            f"[API] 向量索引就绪：RAG文档 {rag_count} 个切片，数据库 {db_count} 行数据"
        )
    print(f"[API] FastAPI服务已启动: http://{_server_host}:{_server_port}")
    print(f"[API] API文档: http://{_server_host}:{_server_port}/docs")


# ==================== 请求/响应模型 ====================
class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str
    role: str
    department: Optional[str] = None
    employee_id: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    source: Optional[str] = "web"  # "web" 或 "cli"，决定数据粒度
    mode: Optional[str] = None  # 保留字段兼容旧客户端，但不再使用


class RoleUpdateRequest(BaseModel):
    username: str
    new_role: str


class UserRoleRequest(BaseModel):
    username: str
    role: str


class TicketCreateRequest(BaseModel):
    title: str
    category: Optional[str] = "一般"
    description: Optional[str] = ""
    priority: Optional[str] = "normal"
    assignee: Optional[str] = ""
    department: Optional[str] = ""


class TicketUpdateRequest(BaseModel):
    status: Optional[str] = None
    assignee: Optional[str] = None
    priority: Optional[str] = None
    description: Optional[str] = None


class NotificationCreateRequest(BaseModel):
    title: str
    content: str
    type: Optional[str] = "info"
    icon: Optional[str] = "🔔"
    target_user: Optional[str] = "all"


class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    department: Optional[str] = None


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str


# OAuth2 for Swagger UI "Authorize" button
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login-form", auto_error=False)


# ==================== 认证依赖 ====================
async def get_current_user(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Depends(oauth2_scheme),
):
    """
    从Header或OAuth2 token中提取认证信息并验证用户身份。
    支持两种方式：
    1. Authorization: Bearer <token> (API调用)
    2. Swagger UI的Authorize按钮 (OAuth2 password flow)
    """
    # 优先使用OAuth2 token（来自Swagger UI Authorize按钮）
    raw_token = token
    # 如果没有OAuth2 token，尝试从Header获取
    if not raw_token and authorization:
        raw_token = (
            authorization.replace("Bearer ", "")
            if authorization.startswith("Bearer ")
            else authorization
        )

    if not raw_token:
        raise HTTPException(
            status_code=401,
            detail="未提供认证信息。请先调用 POST /api/auth/login 获取token，或点击页面顶部 Authorize 按钮登录。",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = verify_token(raw_token)

    if not result.get("valid"):
        raise HTTPException(status_code=401, detail="认证已过期或无效，请重新登录。")

    return result["user"]


# ==================== 认证接口 ====================
@app.post("/api/auth/login")
async def api_login(req: LoginRequest):
    """用户登录（JSON格式，适合前端/Postman调用）"""
    result = login(req.username, req.password)
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["message"])
    return result


@app.post(
    "/api/auth/login-form", summary="登录（Swagger UI专用）", include_in_schema=False
)
async def api_login_form(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    OAuth2密码模式登录 — 供Swagger UI的Authorize按钮使用。
    用户名输入username，密码输入password。
    """
    result = login(form_data.username, form_data.password)
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["message"])
    # OAuth2要求返回access_token字段
    return {
        "access_token": result["token"],
        "token_type": "bearer",
    }


@app.post("/api/auth/logout")
async def api_logout(authorization: Optional[str] = Header(None)):
    """用户登出"""
    if authorization:
        token = authorization.replace("Bearer ", "")
        logout(token)
    return {"success": True, "message": "已登出"}


@app.get("/api/auth/me")
async def api_me(user=Depends(get_current_user)):
    """获取当前用户信息"""
    return {"success": True, "user": user}


# ==================== Dashboard数据接口 ====================
@app.get("/api/dashboard/roster-stats")
async def api_roster_stats(
    department: Optional[str] = None, user=Depends(get_current_user)
):
    """花名册统计（按部门/性别/学历/年龄/工龄）"""
    secretary = get_secretary()
    stats = secretary.roster.get_department_stats(department if department else None)
    return {
        "success": True,
        "data": stats,
        "department": department or "全公司",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/dashboard/recruitment")
async def api_recruitment(user=Depends(get_current_user)):
    """招聘数据（按月度+渠道）"""
    secretary = get_secretary()
    data = secretary.get_recruitment_data()
    return {
        "success": True,
        "data": data,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/dashboard/headcount-trend")
async def api_headcount_trend(
    department: Optional[str] = None, user=Depends(get_current_user)
):
    """人力变动趋势"""
    secretary = get_secretary()
    trend = secretary.roster.get_headcount_trend(department if department else None)
    return {
        "success": True,
        "data": trend,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/dashboard/department-list")
async def api_department_list(user=Depends(get_current_user)):
    """部门列表"""
    secretary = get_secretary()
    stats = secretary.roster.get_department_stats()
    departments = sorted(
        stats["by_department"].items(), key=lambda x: x[1], reverse=True
    )
    return {
        "success": True,
        "data": [{"name": d[0], "count": d[1]} for d in departments],
    }


@app.get("/api/dashboard/kpi")
async def api_kpi(
    company: Optional[str] = None,
    center: Optional[str] = None,
    department: Optional[str] = None,
    emp_type: Optional[str] = None,
    month: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Dashboard KPI数据（切片筛选）"""
    provider = get_dashboard_provider()

    # 当月份为空时，自动使用最新月份（解决部门经理登录后月份为空导致显示全公司数据的问题）
    if not month:
        avail_months = provider.get_available_months()
        if avail_months:
            month = avail_months[0]  # get_available_months 返回降序列表，第一个是最新的

    filters = {
        "company": company or "",
        "center": center or "",
        "department": department or "",
        "emp_type": emp_type or "",
        "month": month or "",
    }
    # 去掉空值
    filters = {k: v for k, v in filters.items() if v}
    data = provider.get_kpi_data(filters if filters else None)
    return {"success": True, "data": data}


@app.get("/api/dashboard/charts")
async def api_charts(
    company: Optional[str] = None,
    center: Optional[str] = None,
    department: Optional[str] = None,
    emp_type: Optional[str] = None,
    month: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Dashboard图表数据（员工结构/编制类型/职级分布）"""
    provider = get_dashboard_provider()
    filters = {
        "company": company or "",
        "center": center or "",
        "department": department or "",
        "emp_type": emp_type or "",
        "month": month or "",
    }
    filters = {k: v for k, v in filters.items() if v}
    data = provider.get_chart_data(filters if filters else None)
    return {"success": True, "data": data}


@app.get("/api/dashboard/efficiency")
async def api_efficiency(
    company: Optional[str] = None,
    month: Optional[str] = None,
    user=Depends(get_current_user),
):
    """关键人效指标数据（每元人力投入产出/人事费用率/人均毛利）"""
    provider = get_dashboard_provider()
    filters = {
        "company": company or "",
        "month": month or "",
    }
    filters = {k: v for k, v in filters.items() if v}
    data = provider.get_efficiency_data(filters if filters else None)
    return {"success": True, "data": data}


@app.get("/api/dashboard/overtime")
async def api_overtime(
    company: Optional[str] = None,
    center: Optional[str] = None,
    department: Optional[str] = None,
    month: Optional[str] = None,
    emp_type: Optional[str] = None,
    user=Depends(get_current_user),
):
    """加班时长分析数据（中心级+部门级组合图）"""
    provider = get_dashboard_provider()
    filters = {
        "company": company or "",
        "center": center or "",
        "department": department or "",
        "month": month or "",
        "emp_type": emp_type or "",
    }
    filters = {k: v for k, v in filters.items() if v}
    data = provider.get_overtime_data(filters if filters else None)
    return {"success": True, "data": data}


@app.get("/api/dashboard/months")
async def api_available_months(user=Depends(get_current_user)):
    """获取可用的统计月份列表（从加班数据的考勤日期提取）"""
    provider = get_dashboard_provider()
    months = provider.get_available_months()
    return {"success": True, "months": months}


@app.get("/api/dashboard/dept-detail")
async def api_dept_detail(
    company: Optional[str] = None,
    center: Optional[str] = None,
    department: Optional[str] = None,
    month: Optional[str] = None,
    emp_type: Optional[str] = None,
    user=Depends(get_current_user),
):
    """部门信息明细表数据"""
    provider = get_dashboard_provider()
    filters = {
        "company": company or "",
        "center": center or "",
        "department": department or "",
        "month": month or "",
        "emp_type": emp_type or "",
    }
    filters = {k: v for k, v in filters.items() if v}
    data = provider.get_dept_detail_data(filters if filters else None)
    return {"success": True, "data": data}


@app.get("/api/dashboard/cost-analysis")
async def api_cost_analysis(
    company: Optional[str] = None,
    center: Optional[str] = None,
    department: Optional[str] = None,
    month: Optional[str] = None,
    user=Depends(get_current_user),
):
    """部门成本包使用情况数据"""
    provider = get_dashboard_provider()
    filters = {
        "company": company or "",
        "center": center or "",
        "department": department or "",
        "month": month or "",
    }
    filters = {k: v for k, v in filters.items() if v}
    data = provider.get_cost_analysis_data(filters if filters else None)
    return {"success": True, "data": data}


# ==================== Dashboard 缓存管理 ====================
@app.post("/api/dashboard/clear-cache")
async def api_clear_dashboard_cache(user=Depends(get_current_user)):
    """手动清除 Dashboard 缓存（数据更新后调用，触发下次请求重新计算）"""
    provider = get_dashboard_provider()
    provider._cache.clear()
    provider._result_cache.clear()
    provider._cache_time.clear()
    provider._result_cache_time.clear()
    print("[API] Dashboard 缓存已清除")
    return {"success": True, "message": "Dashboard 缓存已清除，下次请求将重新计算"}


@app.get("/api/dashboard/search")
async def api_search(keyword: str, source: str = "web", user=Depends(get_current_user)):
    """
    搜索员工。
    - source=web: 只返回聚合统计（人数+部门分布），不返回个人记录
    - source=cli: 按角色权限返回完整员工记录
    """
    secretary = get_secretary()

    if source == "web":
        # Web端：只返回聚合数据，不暴露任何员工个人信息
        raw_results = secretary.roster.query_by_keyword(keyword)
        count = len(raw_results)
        if count == 0:
            data = f"未找到与'{keyword}'相关的员工。"
        else:
            dept_dist = {}
            for r in raw_results:
                dept = str(r.get("部门", "未知")).strip() or "未知"
                dept_dist[dept] = dept_dist.get(dept, 0) + 1
            lines = [
                f"=== 搜索'{keyword}'统计 ===",
                f"匹配人数: {count}人",
                "",
                "【部门分布】",
            ]
            for dept, cnt in sorted(
                dept_dist.items(), key=lambda x: x[1], reverse=True
            )[:10]:
                lines.append(f"  {dept}: {cnt}人")
            data = "\n".join(lines)
    else:
        # CLI端：按角色权限返回完整记录
        raw_results = secretary.roster.query_by_keyword(keyword)
        if raw_results:
            filtered = check_data_access(user, raw_results)
        else:
            filtered = []
        if not filtered:
            data = f"未找到与'{keyword}'相关的员工信息。"
        else:
            lines = [f"=== 搜索'{keyword}'结果（共{len(filtered)}人） ==="]
            for r in filtered[:20]:
                name = r.get("姓名", "?")
                dept = r.get("部门", "?")
                pos = r.get("岗位", "?")
                emp_id = r.get("员工号", "?")
                gender = r.get("性别", "?")
                age = r.get("年龄", "?")
                lines.append(
                    f"  {name} | 工号:{emp_id} | {dept} | {pos} | {gender} | {age}岁"
                )
            if len(filtered) > 20:
                lines.append(f"  ...还有{len(filtered) - 20}人未显示")
            data = "\n".join(lines)

    return {
        "success": True,
        "data": data,
        "source": source,
    }


# ==================== 智能问答接口 ====================
@app.post("/api/chat")
async def api_chat(req: ChatRequest, user=Depends(get_current_user)):
    """智能问答（接入大脑）
    使用 run_in_executor 将同步阻塞的 LLM 调用放到线程池，
    避免阻塞事件循环，支持多人并发请求。
    """
    import asyncio
    from src.main import process_message

    process_fn = process_message

    # 使用稳定的per-user thread_id，让大脑记住每个员工的对话历史
    # 不使用客户端传来的随机session_id，而是基于用户名生成固定ID
    session_id = f"user-{user['username']}"

    # 前缀加上用户身份信息和渠道标记
    user_prefix = f"我是{user['role']}（{user['display_name']}），"
    message = (
        user_prefix + req.message if not req.message.startswith("我是") else req.message
    )

    # Web端附加数据安全限制指令
    if req.source == "web":
        message = "[渠道:web][安全规则] " + message

    try:
        # 将阻塞的 LLM 调用放到线程池，不阻塞事件循环
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, process_fn, message, session_id)
        return {
            "success": True,
            "response": response,
            "session_id": session_id,
            "user": user["display_name"],
            "role": user["role"],
            "source": req.source,
        }
    except Exception as e:
        return {
            "success": False,
            "response": f"处理请求时出错: {str(e)}",
            "session_id": session_id,
        }


@app.post("/api/chat/stream")
async def api_chat_stream(req: ChatRequest, user=Depends(get_current_user)):
    """智能问答流式接口（SSE）

    使用 process_message_stream 生成器，逐 token 返回大脑的思考过程。
    客户端通过 EventSource 或逐行读取获取实时输出。
    """
    import asyncio
    import json as _json
    from src.main import process_message_stream

    session_id = f"user-{user['username']}"

    user_prefix = f"我是{user['role']}（{user['display_name']}），"
    message = (
        user_prefix + req.message if not req.message.startswith("我是") else req.message
    )

    if req.source == "web":
        message = "[渠道:web][安全规则] " + message

    stream_fn = process_message_stream

    def _generate():
        """SSE 生成器：将 process_message_stream 的产出转为 SSE 格式"""
        try:
            gen = stream_fn(message, session_id)
            for event_type, data in gen:
                # SSE 格式: data: {"type": "xxx", "data": "xxx"}\n\n
                payload = _json.dumps(
                    {"type": event_type, "data": str(data)}, ensure_ascii=False
                )
                yield f"data: {payload}\n\n"
        except Exception as e:
            payload = _json.dumps({"type": "error", "data": str(e)}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ==================== 用户管理接口（管理员） ====================
@app.get("/api/admin/users")
async def api_list_users(user=Depends(get_current_user)):
    """列出所有用户（仅管理员）"""
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足")
    users = list_users()
    return {"success": True, "users": users}


@app.post("/api/admin/register")
async def api_register(req: RegisterRequest, user=Depends(get_current_user)):
    """注册新用户（仅管理员）"""
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足")
    result = register_user(
        username=req.username,
        password=req.password,
        display_name=req.display_name,
        role=req.role,
        department=req.department,
        employee_id=req.employee_id,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.put("/api/admin/role")
async def api_update_role(req: RoleUpdateRequest, user=Depends(get_current_user)):
    """更新用户角色（仅管理员）"""
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足")
    result = update_user_role(req.username, req.new_role)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.delete("/api/admin/users/{username}")
async def api_delete_user(username: str, user=Depends(get_current_user)):
    """禁用用户（仅管理员）"""
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足")
    result = delete_user(username)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


# ==================== 兼岗管理接口（管理员） ====================
@app.post("/api/admin/add-role")
async def api_add_role(req: UserRoleRequest, user=Depends(get_current_user)):
    """为用户添加兼岗角色（仅管理员）"""
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足")
    result = add_user_role(req.username, req.role)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.post("/api/admin/remove-role")
async def api_remove_role(req: UserRoleRequest, user=Depends(get_current_user)):
    """移除用户的兼岗角色（仅管理员）"""
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足")
    result = remove_user_role(req.username, req.role)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/api/admin/users/{username}/roles")
async def api_get_user_roles(username: str, user=Depends(get_current_user)):
    """获取用户的所有角色（仅管理员）"""
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足")
    roles = get_user_roles_by_username(username)
    return {"success": True, "username": username, "roles": roles}


@app.get("/api/admin/roles")
async def api_list_roles(user=Depends(get_current_user)):
    """获取所有可用角色列表（仅管理员）"""
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足")
    roles_info = {}
    for role_name, perms in ROLE_PERMISSIONS.items():
        roles_info[role_name] = {
            "deny_fields": perms.get("deny_fields", []),
            "scope_level": perms.get("scope_level", "company"),
            "approval_level": perms.get("approval_level", 0),
        }
    return {"success": True, "roles": roles_info}


# ==================== 工单系统接口 ====================
@app.get("/api/tickets")
async def api_get_tickets(
    status: Optional[str] = None,
    view: Optional[str] = None,
    user=Depends(get_current_user),
):
    """
    获取工单列表
    view=submitted: 我提出的（默认）
    view=received: 交给我的（按角色匹配）
    """
    tickets = get_tickets(
        username=user["username"], role=user["role"], status=status, view=view
    )
    return {"success": True, "tickets": tickets, "view": view or "submitted"}


@app.get("/api/tickets/{ticket_no}")
async def api_get_ticket_detail(ticket_no: str, user=Depends(get_current_user)):
    """获取单个工单详情"""
    ticket = get_ticket_detail(ticket_no, user["username"], user["role"])
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    if "error" in ticket:
        raise HTTPException(status_code=403, detail=ticket["error"])
    return {"success": True, "ticket": ticket}


@app.post("/api/tickets")
async def api_create_ticket(req: TicketCreateRequest, user=Depends(get_current_user)):
    """创建工单"""
    result = create_ticket(req.dict(), user["username"], user["display_name"])
    return {"success": True, **result}


@app.put("/api/tickets/{ticket_id}")
async def api_update_ticket(
    ticket_id: str, req: TicketUpdateRequest, user=Depends(get_current_user)
):
    """更新工单状态（支持数字ID或工单号如TK20260608119）"""
    data = {k: v for k, v in req.dict().items() if v is not None}
    result = update_ticket(ticket_id, data, user["username"])
    return result


@app.post("/api/tickets/{ticket_no}/cancel")
async def api_cancel_ticket(ticket_no: str, user=Depends(get_current_user)):
    """提交人撤销工单"""
    result = cancel_ticket(ticket_no, user["username"])
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "撤销失败"))
    return result


@app.post("/api/tickets/{ticket_no}/done")
async def api_done_ticket(ticket_no: str, user=Depends(get_current_user)):
    """接收人完成工单"""
    result = done_ticket(ticket_no, user["username"])
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "操作失败"))
    return result


# ==================== 工单转办接口 ====================
class TicketTransferRequest(BaseModel):
    target_username: str
    reason: Optional[str] = ""


@app.post("/api/tickets/{ticket_no}/transfer")
async def api_transfer_ticket(
    ticket_no: str, req: TicketTransferRequest, user=Depends(get_current_user)
):
    """工单转办（当前接收人/Admin可将工单转给其他人）"""
    result = transfer_ticket(
        ticket_no,
        from_username=user["username"],
        to_username=req.target_username,
        reason=req.reason,
        from_role=user["role"],
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "转办失败"))
    return result


@app.get("/api/tickets/{ticket_no}/transfers")
async def api_get_ticket_transfers(ticket_no: str, user=Depends(get_current_user)):
    """获取工单的转办历史记录"""
    transfers = get_ticket_transfers(ticket_no)
    return {"success": True, "transfers": transfers}


# ==================== 通知系统接口 ====================
@app.get("/api/notifications")
async def api_get_notifications(
    filter: Optional[str] = "all",
    cursor: Optional[int] = None,
    limit: Optional[int] = 50,
    user=Depends(get_current_user),
):
    """获取通知列表（游标分页）
    filter: all(全部), unread(未读), read(已读)
    cursor: 上一页最后一条通知的 id
    limit: 每页数量（默认50）
    """
    if filter not in ("all", "unread", "read"):
        filter = "all"
    notifs, has_more, next_cursor = get_notifications(
        username=user["username"], limit=limit, filter_by=filter, cursor=cursor
    )
    return {
        "success": True,
        "notifications": notifs,
        "filter": filter,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


@app.post("/api/notifications")
async def api_create_notification(
    req: NotificationCreateRequest, user=Depends(get_current_user)
):
    """创建通知（仅管理员）"""
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足")
    result = create_notification(req.dict())
    return {"success": True, **result}


@app.put("/api/notifications/{notif_id}/read")
async def api_mark_read(notif_id: int, user=Depends(get_current_user)):
    """标记通知已读"""
    result = mark_notification_read(notif_id, user["username"])
    return result


@app.delete("/api/notifications/{notif_id}/read")
async def api_mark_unread(notif_id: int, user=Depends(get_current_user)):
    """标记通知未读"""
    result = mark_notification_unread(notif_id, user["username"])
    return result


@app.put("/api/notifications/read-all")
async def api_mark_all_read(user=Depends(get_current_user)):
    """一键全部已读"""
    result = mark_all_notifications_read(user["username"])
    return result


# ==================== 个人中心接口 ====================
@app.get("/api/profile")
async def api_get_profile(user=Depends(get_current_user)):
    """获取个人信息"""
    profile = get_user_profile(user["username"])
    if not profile:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"success": True, "profile": profile}


@app.put("/api/profile")
async def api_update_profile(req: ProfileUpdateRequest, user=Depends(get_current_user)):
    """更新个人信息"""
    data = {k: v for k, v in req.dict().items() if v is not None}
    result = update_user_profile(user["username"], data)
    return result


@app.post("/api/profile/change-password")
async def api_change_password(
    req: PasswordChangeRequest, user=Depends(get_current_user)
):
    """修改密码"""
    result = change_password(user["username"], req.old_password, req.new_password)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


# ==================== CLI任务接口 ====================
@app.get("/api/cli-tasks")
async def api_get_cli_tasks(user=Depends(get_current_user)):
    """获取当前用户的待处理CLI任务"""
    from src.data.cli_tasks import get_pending_tasks_for_role

    role = user.get("role", "")
    username = user.get("username", "")
    tasks = get_pending_tasks_for_role(role, username)
    return {"success": True, "tasks": tasks}


@app.get("/api/cli-tasks/{task_id}")
async def api_get_cli_task_detail(task_id: str, user=Depends(get_current_user)):
    """获取单个CLI任务详情"""
    from src.data.cli_tasks import get_task_by_id

    task = get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "task": task}


@app.put("/api/cli-tasks/{task_id}")
async def api_update_cli_task(task_id: str, user=Depends(get_current_user)):
    """更新CLI任务状态"""
    from src.data.cli_tasks import update_cli_task_status, get_task_by_id
    from fastapi import Body

    task = get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    result = update_cli_task_status(task_id, "completed", "手动标记完成")
    return result


# ==================== 即时通讯接口 ====================
class ChatStartRequest(BaseModel):
    target_user: str  # 对方用户名


class ChatSendRequest(BaseModel):
    session_id: str
    content: str


class ChatCloseRequest(BaseModel):
    session_id: str


class ChatPollRequest(BaseModel):
    session_id: str
    last_id: Optional[int] = 0


@app.post("/api/realtime-chat/start")
async def api_chat_start(req: ChatStartRequest, user=Depends(get_current_user)):
    """发起即时对话"""
    from src.security.auth import get_user_by_username, list_users

    target = req.target_user

    # 先检查 target 是否是 username
    target_user = get_user_by_username(target)

    if not target_user:
        # target 可能是 display_name，通过用户列表查找对应的 username
        all_users = list_users()
        for u in all_users:
            if u.get("display_name") == target or u.get("display_name", "").startswith(
                target
            ):
                target = u["username"]
                target_user = u
                break

    if not target_user:
        raise HTTPException(status_code=404, detail=f"未找到用户 '{req.target_user}'")

    target_username = (
        target_user["username"] if isinstance(target_user, dict) else target
    )

    result = start_chat_session(user["username"], target_username)
    if not result["success"]:
        raise HTTPException(status_code=400, detail="无法创建对话")
    return result


@app.post("/api/realtime-chat/send")
async def api_chat_send(req: ChatSendRequest, user=Depends(get_current_user)):
    """发送消息（消息自动存储到服务器数据库）"""
    result = send_chat_message(req.session_id, user["username"], req.content)
    return result


@app.post("/api/realtime-chat/poll")
async def api_chat_poll(req: ChatPollRequest, user=Depends(get_current_user)):
    """拉取新消息（轮询）"""
    result = poll_chat_messages(req.session_id, last_id=req.last_id or 0)
    return result


@app.post("/api/realtime-chat/close")
async def api_chat_close(req: ChatCloseRequest, user=Depends(get_current_user)):
    """关闭对话"""
    result = close_chat_session(req.session_id)
    return result


@app.get("/api/realtime-chat/active")
async def api_chat_active(user=Depends(get_current_user)):
    """获取当前用户的活跃对话"""
    result = get_active_chat(user["username"])
    return result


@app.post("/api/realtime-chat/pending")
async def api_chat_pending(req: ChatPollRequest, user=Depends(get_current_user)):
    """获取待推送的消息（只返回 pending 状态的对方消息）"""
    result = get_pending_messages(req.session_id, user["username"])
    return result


class ChatMarkDeliveredRequest(BaseModel):
    session_id: str


@app.post("/api/realtime-chat/mark-delivered")
async def api_chat_mark_delivered(
    req: ChatMarkDeliveredRequest, user=Depends(get_current_user)
):
    """将指定会话中的对方消息标记为已推送"""
    result = mark_messages_delivered(req.session_id, user["username"])
    return result


# ==================== Skill注册中心接口 ====================
class SkillUploadRequest(BaseModel):
    skill_name: str
    display_name: Optional[str] = ""
    description: Optional[str] = ""
    version: Optional[str] = "1.0.0"
    target_roles: Optional[list] = []


class SkillRoleUpdateRequest(BaseModel):
    target_roles: list


class SkillCheckUpdateRequest(BaseModel):
    local_versions: Optional[dict] = {}


@app.post("/api/skills/registry")
async def api_upload_skill(
    skill_name: str = Form(...),
    display_name: str = Form(""),
    description: str = Form(""),
    version: str = Form("1.0.0"),
    target_roles: str = Form("[]"),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """上传新Skill（管理员）—— 通过 multipart/form-data"""
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足")

    import json as _json

    try:
        roles_list = (
            _json.loads(target_roles) if isinstance(target_roles, str) else target_roles
        )
    except Exception:
        roles_list = []

    from src.data.skill_registry import SKILL_PACKAGES_DIR
    import zipfile, io, shutil

    content = await file.read()

    # 验证 zip 格式
    try:
        zip_buffer = io.BytesIO(content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_list = zf.namelist()
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="上传的文件不是有效的zip格式")

    # 验证必须包含 SKILL.md
    has_skill_md = any(f.endswith("SKILL.md") for f in file_list)
    if not has_skill_md:
        raise HTTPException(status_code=400, detail="zip包中必须包含 SKILL.md 文件")

    # 保存 zip 文件
    zip_dir = Path(SKILL_PACKAGES_DIR)
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / f"{skill_name}.zip"
    with open(zip_path, "wb") as f:
        f.write(content)

    # 解压到 skill 目录（方便服务端读取元数据）
    skill_extract_dir = zip_dir / skill_name
    if skill_extract_dir.exists():
        shutil.rmtree(skill_extract_dir)
    with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
        zf.extractall(skill_extract_dir)

    # 注册到数据库
    result = register_skill(
        {
            "skill_name": skill_name,
            "display_name": display_name,
            "description": description,
            "version": version,
            "target_roles": roles_list,
            "file_list": file_list,
            "zip_path": str(zip_path),
            "created_by": user["username"],
        }
    )

    return {"success": True, **result, "files": file_list}


@app.get("/api/skills/registry")
async def api_list_skills(user=Depends(get_current_user)):
    """列出所有已注册的 Skill（管理员）"""
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足")
    skills = get_all_skills()
    return {"success": True, "skills": skills}


@app.get("/api/skills/registry/{skill_name}")
async def api_get_skill(skill_name: str, user=Depends(get_current_user)):
    """获取单个 Skill 详情"""
    skill = get_skill_by_name(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")
    return {"success": True, "skill": skill}


@app.put("/api/skills/registry/{skill_name}/status")
async def api_update_skill_status(
    skill_name: str, status: str, user=Depends(get_current_user)
):
    """更新 Skill 状态（active / disabled）"""
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足")
    if status not in ("active", "disabled"):
        raise HTTPException(status_code=400, detail="状态只能是 active 或 disabled")
    result = update_skill_status(skill_name, status)
    return result


@app.put("/api/skills/registry/{skill_name}/roles")
async def api_update_skill_roles(
    skill_name: str, req: SkillRoleUpdateRequest, user=Depends(get_current_user)
):
    """更新 Skill 的目标角色"""
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足")
    result = update_skill_roles(skill_name, req.target_roles)
    return result


@app.delete("/api/skills/registry/{skill_name}")
async def api_delete_skill(skill_name: str, user=Depends(get_current_user)):
    """删除 Skill"""
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足")
    result = delete_skill(skill_name)
    return result


@app.get("/api/skills/download/{skill_name}")
async def api_download_skill(skill_name: str, user=Depends(get_current_user)):
    """下载 Skill zip 包"""
    skill = get_skill_by_name(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")
    if skill["status"] != "active":
        raise HTTPException(status_code=403, detail=f"Skill '{skill_name}' 已禁用")

    zip_path = Path(skill.get("zip_path", ""))
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Skill包文件不存在")

    from fastapi.responses import FileResponse

    return FileResponse(
        str(zip_path),
        media_type="application/zip",
        filename=f"{skill_name}.zip",
    )


@app.post("/api/skills/check-update")
async def api_check_update(
    req: SkillCheckUpdateRequest, user=Depends(get_current_user)
):
    """CLI检查Skill更新"""
    result = check_updates(req.local_versions or {})
    return {"success": True, **result}


# ==================== 用户活动日志接口 ====================
class ActivityLogRequest(BaseModel):
    content: str
    type: Optional[str] = "command"  # command / chat / skill
    session_id: Optional[str] = None


@app.post("/api/log-activity")
async def api_log_activity(req: ActivityLogRequest, user=Depends(get_current_user)):
    """记录用户活动（命令执行、聊天消息等）到conversations表，不经过大脑处理"""
    from src.memory.database import save_conversation

    session_id = req.session_id or f"cli-{user['username']}"
    save_conversation(
        session_id=session_id,
        role="user",
        content=f"[{req.type}] {req.content}",
        source=f"cli_{req.type}",
        importance_score=0.3,
    )
    return {"success": True}


# ==================== 健康检查 ====================
@app.get("/api/health")
async def health_check():
    """服务健康检查"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
    }


# ==================== 调度器管理接口（管理员） ====================
@app.post("/api/scheduler/trigger-insight")
async def api_trigger_insight(user=Depends(get_current_user)):
    """手动触发洞察（仅管理员）

    使用场景：
    1. 定时数据更新失败后，修复数据源需要补跑洞察
    2. HRIS 手动更新了花名册或加班数据，需要立即产出洞察
    3. 服务刚启动或错过 05:00 时间窗口，需要补跑当日洞察

    该接口不受时间守卫限制，强制重置当日洞察状态后立即执行。
    """
    if user["role"] != "HR_SSC经理":
        raise HTTPException(status_code=403, detail="权限不足：仅管理员可触发洞察")
    if _scheduler_instance is None:
        raise HTTPException(status_code=503, detail="调度器未启动")
    try:
        success = _scheduler_instance.trigger_insight()
        if success:
            return {"success": True, "message": "洞察已触发，正在执行..."}
        else:
            return {"success": False, "message": "洞察触发失败，请检查日志"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"触发洞察异常: {str(e)}")


# ==================== 根路径 ====================
@app.get("/portal")
async def portal():
    """门户前端页面"""
    from fastapi.responses import FileResponse

    portal_path = Path(__file__).parent / "portal.html"
    return FileResponse(str(portal_path), media_type="text/html")


@app.get("/resources/{filename:path}")
async def serve_resources(filename: str):
    """静态资源文件（Logo等）"""
    from fastapi.responses import FileResponse

    resources_dir = Path(__file__).resolve().parent.parent.parent / "resources"
    file_path = resources_dir / filename
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    return JSONResponse(status_code=404, content={"detail": "File not found"})


@app.get("/")
async def root():
    """首页 — 导航页"""
    from fastapi.responses import HTMLResponse

    html_content = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>SSC硅基生物系统</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Microsoft YaHei', sans-serif;
                   background: #0a0e17; color: #e2e8f0; display: flex; justify-content: center;
                   align-items: center; min-height: 100vh; margin: 0; }
            .container { text-align: center; max-width: 600px; padding: 40px; }
            h1 { font-size: 36px; background: linear-gradient(135deg, #3b82f6, #8b5cf6);
                 -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 8px; }
            .subtitle { color: #94a3b8; font-size: 16px; margin-bottom: 40px; }
            .links { display: flex; flex-direction: column; gap: 16px; }
            .link { display: block; padding: 18px 24px; background: #1a2332; border: 1px solid #2d3a4f;
                    border-radius: 12px; color: #e2e8f0; text-decoration: none; transition: all 0.2s; }
            .link:hover { border-color: #3b82f6; background: #1e2a3d; transform: translateY(-2px); }
            .link h3 { margin: 0 0 4px; font-size: 18px; color: #3b82f6; }
            .link p { margin: 0; font-size: 14px; color: #94a3b8; }
            .badge { display: inline-block; padding: 2px 10px; border-radius: 4px; font-size: 12px;
                     margin-left: 8px; }
            .badge-green { background: rgba(16,185,129,0.15); color: #10b981; }
            .badge-blue { background: rgba(59,130,246,0.15); color: #3b82f6; }
            .badge-purple { background: rgba(139,92,246,0.15); color: #8b5cf6; }
            .footer { margin-top: 40px; color: #64748b; font-size: 13px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🧬 SSC硅基生物系统</h1>
            <p class="subtitle">HR SSC · AI神经中枢 · v2.0</p>
            <div class="links">
                <a class="link" href="/portal">
                    <h3>🏠 门户首页 <span class="badge badge-purple">Portal</span></h3>
                    <p>SSC门户前端（数据看板/智能问答/花名册/知识库）</p>
                </a>
                <a class="link" href="/docs">
                    <h3>📖 API文档 <span class="badge badge-green">Swagger UI</span></h3>
                    <p>查看和测试所有API接口</p>
                </a>
                <a class="link" href="/redoc">
                    <h3>📘 API文档 <span class="badge badge-blue">ReDoc</span></h3>
                    <p>更美观的API文档格式</p>
                </a>
                <a class="link" href="/api/health">
                    <h3>💓 健康检查</h3>
                    <p>检查服务运行状态</p>
                </a>
            </div>
            <p class="footer">SSC硅基生物系统 · FastAPI数据接口 · 2026-06-02</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# ==================== 启动入口 ====================
if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="SSC硅基生物系统 API服务")
    parser.add_argument(
        "--update", action="store_true", help="强制重建全部向量索引（数据更新后使用）"
    )
    parser.add_argument(
        "--update-db",
        type=str,
        default="",
        help="只重建指定数据库文件的索引（如: 员工花名册.xlsx）",
    )
    parser.add_argument("--port", type=int, default=8000, help="服务端口（默认8000）")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="监听地址（默认0.0.0.0，局域网可访问）",
    )
    args = parser.parse_args()

    # 设置全局标志
    _force_update_index = args.update
    _update_db_file = args.update_db
    _server_port = args.port
    _server_host = args.host

    # 先初始化种子数据
    init_auth_db()
    seed_default_users()
    # 应用日志过滤（减少实时聊天轮询的噪音）
    logging.getLogger("uvicorn.access").addFilter(_AccessLogFilter())
    # 检测端口是否被占用
    import socket

    _sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _sock.bind(("127.0.0.1", args.port))
        _sock.close()
    except OSError as e:
        _sock.close()
        print(f"\n❌ 端口 {args.port} 被占用！")
        print(f"   错误: {e}")
        # 尝试找出占用端口的进程
        try:
            import subprocess

            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in result.stdout.splitlines():
                if f":{args.port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    proc = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid}"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                    for pl in proc.stdout.splitlines():
                        if (
                            "python" in pl.lower()
                            or "java" in pl.lower()
                            or "node" in pl.lower()
                            or ".exe" in pl.lower()
                        ):
                            print(f"   占用进程: PID {pid} — {pl.strip().split()[0]}")
                            break
                    else:
                        print(f"   占用进程: PID {pid}")
                    break
        except Exception:
            pass
        print(f"\n   请先关闭占用端口的进程，或使用 --port 指定其他端口：")
        print(f"   python -m src.api.server --port 8001\n")
        sys.exit(1)

    # 单Worker + run_in_executor 已支持并发（每个LLM调用在线程池中独立执行，不阻塞事件循环）
    # 不使用多Worker：因为4个Worker会同时构建149184行Embedding索引，击垮Ollama服务
    uvicorn.run(app, host=args.host, port=args.port)
