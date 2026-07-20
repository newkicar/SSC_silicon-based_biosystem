# API 契约（REST API）

> FastAPI 服务端接口定义，基于 `src/api/server.py`。

---

## 基础信息

- **Base URL**: `http://localhost:8000`
- **认证方式**: Bearer Token (`Authorization: Bearer <token>`)
- **Content-Type**: `application/json`

---

## 认证接口

### POST /api/auth/login

用户登录，获取 Token。

**请求**:
```json
{"username": "110031", "password": "xxx"}
```

**响应 200**:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {"username": "110031", "display_name": "张三", "role": "HR_SSC经理"}
}
```

### GET /api/auth/me

获取当前用户信息。

**响应 200**:
```json
{
  "username": "110031",
  "display_name": "张三",
  "role": "HR_SSC经理",
  "scope_level": "company",
  "deny_fields": ["salary", "id_card"]
}
```

---

## 智能问答接口

### POST /api/chat

同步智能问答。

**请求**:
```json
{"message": "我上个月加班时长是多少？", "channel": "cli"}
```

**响应 200**:
```json
{
  "reply": "您上个月（2026-06）累计加班 12 小时...",
  "sources": ["RAG_files/policy/overtime.md"],
  "dispatch_actions": null
}
```

### POST /api/chat/stream

SSE 流式智能问答。

**响应**: SSE 事件流，包含 `token`、`complete` 事件。

---

## Dashboard 接口

### GET /api/dashboard/kpi

KPI 卡片数据。

**响应 200**:
```json
{
  "total_tickets": 156,
  "pending_tasks": 23,
  "active_users": 44,
  "today_queries": 89
}
```

### GET /api/dashboard/charts

图表数据（工单趋势/部门分布/角色分布）。

### GET /api/dashboard/overtime

加班分析数据（汇总/趋势/Top部门）。

### GET /api/dashboard/dept-detail

部门明细表（人数/加班/休假余额）。

### GET /api/dashboard/efficiency

人效指标（每人工单数/平均响应时间）。

### GET /api/dashboard/cost-analysis

成本分析（总成本/人均成本/部门分布）。

---

## 工单接口

### GET /api/tickets

获取工单列表。

**查询参数**: `status`, `priority`, `page`, `page_size`

**响应 200**:
```json
{
  "tickets": [
    {
      "id": 1,
      "ticket_no": "TK-20260629-001",
      "title": "考勤异常申诉",
      "status": "pending",
      "priority": "normal",
      "created_at": "2026-06-29T10:00:00Z"
    }
  ],
  "total": 156,
  "page": 1
}
```

### POST /api/tickets

创建工单。

**请求**:
```json
{
  "title": "考勤异常申诉",
  "description": "6月15日迟到非本人原因",
  "priority": "normal",
  "category": "员工关系"
}
```

---

## 通知接口

### GET /api/notifications

获取通知列表。

**查询参数**: `filter` (=all|unread|read)

**响应 200**:
```json
{
  "notifications": [
    {
      "id": 1,
      "title": "月度考勤洞察",
      "content": "6月全公司人均加班12小时...",
      "is_read": false,
      "created_at": "2026-07-01T05:00:00Z"
    }
  ],
  "unread_count": 5
}
```

### PUT /api/notifications/{id}/read

标记通知为已读。

---

## 调度器接口

### POST /api/scheduler/trigger-insight

手动触发洞察生成（仅 HR_SSC经理）。

---

## Skill 注册接口

### GET /api/skills

获取已注册 Skill 列表。

### POST /api/skills/register

注册新 Skill。

---

## 数据管理接口

### POST /api/data/update-db

单文件索引更新。

**请求**:
```json
{"filename": "员工花名册.xlsx"}
```

### POST /api/data/update

全量索引重建。

---

## 错误响应格式

所有错误统一格式：

```json
{
  "detail": "错误描述信息"
}
```

| HTTP 状态码 | 说明 |
|------------|------|
| 400 | 请求参数错误 |
| 401 | 未认证/Token 无效 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 422 | 验证失败 |
| 500 | 服务器内部错误 |