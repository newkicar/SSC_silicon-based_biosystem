# Acceptance Criteria（验收标准）

> 每条标准应可测试、可判定通过/失败。
> 使用 Given-When-Then 格式描述行为，粒度控制在单个功能点。

---

## 功能：智能问答系统

- [ ] **AC-1**：给定员工通过 Web 门户提问政策相关问题，当系统收到请求时，那么通过 RAG 搜索政策文档并返回引用来源
  - **关联**：PRD「智能问答系统」Web 端
  - **测试**：`tests/test_web_portal_rag.py`

- [ ] **AC-2**：给定员工通过 CLI 终端查询个人数据（如考勤、花名册），当系统识别到 `[渠道:cli]` 时，那么执行联合搜索（RAG + 数据库向量检索）
  - **关联**：PRD「智能问答系统」CLI 端
  - **测试**：`tests/test_cli_joint_search.py`

- [ ] **AC-3**：给定用户未登录，当发起任何 API 请求时，那么返回 401 错误并要求认证
  - **关联**：PRD「RBAC 权限体系」
  - **测试**：`tests/test_auth_required.py`

- [ ] **AC-4**：给定普通员工查询敏感话题（劳动仲裁、举报），当请求包含此类关键词时，那么立即转交 HR 创建 urgent 工单
  - **关联**：PRD「安全」敏感话题处理
  - **测试**：`tests/test_sensitive_topic_handling.py`

## 功能：Marathon 多步骤执行引擎

- [ ] **AC-5**：给定用户提出复杂多步骤任务（如"生成月度考勤报告并通知部门负责人"），当 Planner 节点执行时，那么拆解为至少 2 个子步骤并标注 capability
  - **关联**：PRD「Marathon 多步骤执行引擎」
  - **测试**：`staff/test/test_planner.py`

- [ ] **AC-6**：给定 executor 节点接收到 `skill-` 开头的 capability，当执行时，那么注入 search + execute_skill 工具集
  - **关联**：PRD「动态工具隔离」
  - **测试**：`staff/test/test_executor_tool_injection.py`

- [ ] **AC-7**：给定 executor 节点接收到搜索类 capability（如 `query_attendance`），当执行时，那么仅注入搜索工具，不包含 execute_skill
  - **关联**：PRD「防止越界执行」
  - **测试**：`staff/test/test_executor_isolation.py`

- [ ] **AC-8**：给定 RubricMiddleware 评分未通过，当重试 execute_skill 时，那么相同 task_description + execution_context_id 直接返回缓存结果（60s 内）
  - **关联**：PRD「幂等性缓存」
  - **测试**：`staff/test/test_executor_idempotency.py`

## 功能：数据洞察系统

- [ ] **AC-9**：给定每日 05:00 定时任务触发，当花名册和加班数据都更新成功时，那么自动生成洞察通知并推送给对应角色
  - **关联**：PRD「数据洞察系统」
  - **测试**：`tests/test_daily_insight_generation.py`

- [ ] **AC-10**：给定任一数据源更新失败（[ERP系统接口] 不可用/Excel 解析失败），当 `_daily_data_refresh()` 完成时，那么创建 HRIS 紧急工单并跳过洞察生成
  - **关联**：PRD「故障必须暴露」
  - **测试**：`tests/test_data_refresh_failure.py`

- [ ] **AC-11**：给定公司级洞察通知，当目标用户为总经理（[高管占位符]）时，那么只推送[公司名称]公司公司级洞察，不推送[关联公司]的
  - **关联**：PRD「公司级洞察隔离」
  - **测试**：`tests/test_insight_routing_isolation.py`

## 功能：RBAC 权限体系

- [ ] **AC-12**：给定用户拥有多个角色（兼岗），当查询权限时，那么取所有角色的权限并集
  - **关联**：PRD「兼岗并集支持」
  - **测试**：`tests/test_dual_role_permission.py`

- [ ] **AC-13**：给定 scope_level 为 `department` 的用户，当查询数据时，那么只返回其管辖部门的数据，不返回其他部门
  - **关联**：PRD「范围限制」
  - **测试**：`tests/test_scope_restriction.py`

- [ ] **AC-14**：给定 deny_fields 配置了敏感字段（如薪资、身份证号），当普通员工角色查询时，那么返回数据中这些字段被过滤
  - **关联**：PRD「排除法权限」
  - **测试**：`tests/test_deny_fields_filter.py`

## 功能：定时任务调度

- [ ] **AC-15**：给定 Scheduler 启动，当 02:00 到达时，那么执行记忆整理任务（调用大脑提炼对话决策）
  - **关联**：PRD「定时任务调度」
  - **测试**：`tests/test_scheduler_memorize.py`

- [ ] **AC-16**：给定心跳巡检任务执行，当快照对比发现差异时，那么生成差异报告并发送给大脑分析
  - **关联**：PRD「每30分钟心跳巡检」
  - **测试**：`tests/test_heartbeat_scan.py`

---

## 边界与错误

- [ ] **AC-E1**：给定大脑返回的 dispatch_actions JSON 格式不完整（如缺失 `type` 字段），当分派器解析时，那么跳过该 action 并记录错误日志
  - **关联**：PRD「安全」JSON 容错
  - **测试**：`tests/test_dispatch_json_invalid.py`

- [ ] **AC-E2**：给定通知路由匹配到 0 个目标用户，当洞察生成完成时，那么创建 HRIS 工单升级处理
  - **关联**：PRD「通知路由兜底」
  - **测试**：`tests/test_notification_no_target.py`

- [ ] **AC-E3**：给定 execute_skill 调用 deepagents agent 超时（>120s），当执行失败时，那么返回错误信息并标记步骤为 failed
  - **关联**：PRD「性能」超时处理
  - **测试**：`staff/test/test_executor_timeout.py`

---

## 非功能验收

| 指标 | 验收条件 | 测量方式 |
|------|---------|---------|
| 响应时间 | 单次问答 ≤ 5s（不含工具调用） | APM 监控 + 日志计时 |
| Marathon 执行 | 复杂任务 ≤ 60s | Marathon 执行日志 |
| 可靠性 | 定时任务失败率 < 1% | 生产日志统计 |
| 安全 | 无 CVE-high 依赖漏洞 | `pip audit` |
| 权限隔离 | 跨部门数据访问 100% 拦截 | 渗透测试 + 自动化测试 |

---

## 补充说明

- 每条 AC 对应一个或多个测试用例
- 标记 `[ ]` 表示待完成，测试通过后改为 `[x]`
- 无法自动测试的手动验证项，在备注中说明验证步骤