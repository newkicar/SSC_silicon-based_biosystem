# 项目进度

> 项目：HR SSC 硅基生物系统（组织数字孪生）
> 上次更新：2026-07-01

## 当前里程碑

| 里程碑 | 状态 | 备注 |
|--------|------|------|
| M1 - 基础架构（骨架） | ✅ 完成 | backbone、brain、RAG、api |
| M2 - 数据能力（血液） | ✅ 完成 | 考勤、花名册、排班 |
| M3 - 工单/通知（器官） | ✅ 完成 | tickets API |
| M4 - Marathon 执行引擎 | ✅ 完成 | plan → execute → validate |
| M5 - 技能注入（肌肉） | ✅ 完成 | Skills 匹配加载 |
| M6 - 团队协作（细胞） | ✅ 完成 | 分派、通知、协作 |
| M7 - 角色权限增强 | ✅ 完成 | role_departments 表、dispatcher 集成 |
| M8 - 幂等性修复 | ✅ 完成 | Rubric 感知去重 v2 |

## 待办 / 已知问题

### P0 — 需立即处理
- （无）

### P1 — 高优先级
- （无）

### P2 — 改进项
- 并发问题，当前架构最多能支持多少并发？

## 2026-07-03 工作记录

### 洞察通知路由修复（兼岗匹配问题）
- **问题**：1[工号]（[姓名]，4个兼岗）收不到代工业务中心加班洞察通知
- **根因**：`resolve_notification_targets()` 只检查 `list_users()` 返回的第一条兼岗记录，而数据库查询无 ORDER BY，有时取到 `org=""` 的记录，导致所有洞察通知匹配失败
- **修复**：
  - `services.py`：`resolve_notification_targets()` 新增 `_all_orgs` 参数，遍历用户所有兼岗记录进行匹配
  - `dispatcher.py`：查询用户所有兼岗记录并通过 `_all_orgs` 传入路由函数

### 洞察查重逻辑修复
- **问题**：两条不同主题的洞察通知（成本 vs 离职）发给同一用户时，因 `target_user` 匹配全部被拦截
- **根因**：`get_recent_notifications()` 查询该用户所有历史记录，`check_is_duplicate()` 用 LLM 对所有记录做语义相似度比较，即使主题完全不同也可能被判为重复
- **修复**：在 `_dispatch_insight_actions()` 中添加 `insight_type` 预过滤 — 只有相同 `insight_type` 的记录才送入 LLM 查重，不同类型的洞察直接放行

### 工单转办功能（全栈完成）
- **需求**：人员转岗时，接收人可将未处理工单转办给接手人
- **后端实现**：
  - `services.py`：新增 `ticket_transfers` 表 + `transfer_ticket()` + `get_ticket_transfers()` 函数
  - `server.py`：新增 `POST /api/tickets/{ticket_no}/transfer` + `GET /api/tickets/{ticket_no}/transfers` 接口
- **前端实现**：
  - `portal_ext.js`：工单列表增加「🔄 转办」按钮（仅"交给我的"视图可见）
  - `portal_ext.js`：转办弹窗（prompt 输入目标用户 + 原因）
  - `portal_ext.js`：转办历史弹窗（自定义模态框展示转办记录）
- **权限**：当前 assignee 可转办给自己指定的人；Admin/HR_SSC 经理可强制转办任意工单
- **通知**：转办成功后自动通知新接收人

### Dashboard 缓存延迟修复
- **问题**：用户停止操作 10 分钟以上后，再次点击报表切片出现 20-30 秒延迟
- **根因**：`DashboardDataProvider` 缓存 TTL 过短（数据层 300s、结果层 120s），空闲后缓存全部过期，首次请求需重新读取 7 个 Excel 文件并聚合计算
- **修复**：
  - `dashboard_data.py`：`_get_cache()` 默认 TTL 300s → 3600s（1 小时）
  - `dashboard_data.py`：`_get_result_cache()` 默认 TTL 120s → 1800s（30 分钟）
  - `server.py`：新增 `POST /api/dashboard/clear-cache` 手动清除缓存接口，数据更新后可触发重新计算

### 通知路由问题修复
- **问题**：洞察通知全部被查重拦截，用户收不到通知
- **根因**：`cleanup_test_data.py` 遗漏了 `insight_notifications` 表（查重记录表）
- **修复**：添加 `clear_table(conn, "insight_notifications")` 到清理脚本

### 死函数清理（6 个）
使用 codebase-memory-mcp 索引项目（5,581 节点，10,299 边），通过 `search_graph` + `trace_path` 发现 6 个无人调用的死函数，依赖关系全部干净：

| 函数 | 文件 | 状态 |
|------|------|------|
| `_cosine_similarity` | `src/tools/vector_rag.py` | ✅ 已删除 |
| `_get_named_row_cursor` | `src/data/insight_notifications.py` | ✅ 已删除 |
| `_parse_input_schema` | `src/skills/__init__.py` | ✅ 已删除 |
| `get_escalation_strategy` | `src/scheduler/work_time.py` | ✅ 已删除 |
| `get_local_skill_dirs` | `staff/skill_sync.py` | ✅ 已删除 |
| `get_skill_skill_md` | `staff/skill_sync.py` | ✅ 已删除 |

### 项目文档补充
- `specs/PRD.md` — 产品需求文档
- `specs/acceptance-criteria.md` — 验收标准（16 条 AC）
- `design/HLD.md` — 高层设计文档（含 ASCII 架构图）
- `design/contracts/api-contract.md` — REST API 契约
- `design/contracts/dispatch-schema.md` — dispatch_actions JSON Schema
- `design/contracts/insight-schema.md` — 洞察通知 JSON Schema

## 团队成员角色-部门映射（已入库）

通过 role_departments 表配置，dispatcher.py 直接读库。见 auth.py 的 `create_role_department()`、`get_department_for_role()`。

## 异常处理策略（v2 幂等性）

- **RubricMiddleware 重试场景**：Rubric 未通过时，exec_id 不在 `_rubric_passed_exec_ids`，execute_skill 允许重新执行
- **Rubric 通过后**：exec_id 被记录，同一 exec_id 内后续 execute_skill 调用直接跳过
- **缓存隔离**：不同 step/attempt 互不干扰，60s 窗口 + LRU 淘汰
