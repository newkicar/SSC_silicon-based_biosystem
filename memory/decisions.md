# Decisions

> 架构与实现决策记录。避免重复讨论已定论的问题。

---

## 2026-06-29

- **决策：通知全员广播 bug 修复**
- **背景：** `_dispatch_notification` 中 `target_user` 硬编码为 `"all"`，导致所有通知全员可见
- **原因：** 第 472 行 `"target_user": "all"` 写死，`final_targets` 精确计算的用户列表被丢弃
- **实现：**
  - `dispatcher.py`：`_dispatch_notification` 中改为 `"target_user": ",".join(final_targets)`
  - 去掉 `targets[0] == "all"` 广播逻辑
  - 无匹配用户时创建 HRIS 工单升级处理
  - 清理所有 try-except（异常直接抛）

- **决策：通知路由精准匹配**
- **背景：** `resolve_notification_targets` 只看 `role` 不看 `org`，导致：
  - admin（HR_SSC经理）匹配所有洞察
  - 110136（制造一中心总监）被路由到大连研发中心通知
- **原因：** 管理中心级/部门级洞察时必须 `insight_org == org`
- **实现：**
  - `services.py`：`resolve_notification_targets` 中 HR_SSC经理/学科经理只接收公司级 + 自己管辖 org 的洞察
  - admin 单独排除（系统管理员不接收洞察）
  - 中心总监只接收自己 org 的中心级洞察
  - 部门经理只接收自己 org 的部门级洞察

- **决策：通知查询支持逗号分隔列表**
- **背景：** `target_user` 存的是 `"110031,110136"` 逗号分隔列表，但查询用 `n.target_user = ?` 精确匹配，导致无人能收到通知
- **原因：** 字符串精确匹配无法匹配逗号分隔列表
- **实现：**
  - `services.py`：`get_notifications` 中加 `',' || n.target_user || ',' LIKE '%,' || ? || ',%'` 支持列表匹配

- **决策：洞察生成添加详细计时日志**
- **背景：** 洞察生成卡住（LLM 调用超时），需要精确定位卡住位置
- **实现：**
  - `agent.py`：`run_insight_agent()` 记录 `agent.invoke()` 耗时
  - `agent.py`：`generate_insight_with_retry()` 记录每次重试耗时
  - `scheduler.py`：`_run_daily_insight()` 记录每个公司耗时
---

## 2026-06-23

- **决策：** `build_overtime.py` 聚合 DataFrame 中"后续填充"列初始化为 `None` 而非 `""`
- **背景：** pandas 将整列空字符串推断为 `str` dtype，后续写入 float 时触发 `TypeError`
- **原因：** `None` 让 pandas 推断为 `NaN` (float)，配合 `pd.to_numeric(errors="coerce")` 保证 dtype 兼容

- **决策：** 实现主动洞察通知路由（scheduler → brain → dispatcher → services）
- **背景：** 原通知链路仅在员工请求时被动触发，管理层/SSC员工无法在数据更新后自动收到洞察
- **原因：**
  1. `target_user="all_ssc"` 与 `get_notifications()` 查询 `target_user='all'` 不匹配，导致通知对用户不可见
  2. 大脑缺乏主动洞察机制，数据更新后无自动推送
- **实现：**
  - `services.py`：`_normalize_target_user()` 统一将 `all_ssc/all_users/*` 规范化为 `all`；新增 `resolve_notification_targets()` 按洞察类型和用户上下文路由
  - `brain.py`：SYSTEM_PROMPT 增加「四-2、洞察通知路由规则」，管理层按管辖域 `scope:{org}` 推送，SSC经理全员广播，员工按 specialization 匹配
  - `main.py`：在 brain invoke 前提取提问人身份并注入 `intelligence_prompt`，确保大脑路由有据可依
  - `dispatcher.py`：`scope:{org}` 展开为具体接收人（查 `user_roles` + `users`）；同一轮次用 `_notif_seen` set 去重
  - `scheduler.py`：`_daily_data_refresh()` 末尾调用 `_run_daily_insight()`，每天 05:00 数据更新后自动生成洞察并分发通知

- **决策：** 洞察通知标题/内容质量硬约束
- **背景：** `_run_daily_insight()` 的 prompt 示例中使用 `"洞察标题"`/`"具体内容含数据"` 作为模板，大脑将其直接复制为实际输出，导致用户看到"洞察A""内容A"
- **原因：** LLM 会将 prompt 示例的占位符文本当作输出格式盲目复制
- **实现：**
  - `scheduler.py`：删除模板占位符，替换为有数据的具体示例（`[考勤]全公司本月人均加班XX小时`）
  - 增加"title 必须见文知义"硬约束 + "禁止输出内容A/洞察A"的禁止清单
  - prompt 示例改为有实际数据字段 + 变化趋势 + 建议的完整 JSON

- **决策：** 通知中心支持按「全部/未读/已读」筛选
- **背景：** 通知点击后变暗（opacity:0.6），但历史信息一直显示，用户需要筛选能力
- **原因：** 列表视图中已读/未读混合显示造成信息噪音
- **实现：**
  - `services.py`：`get_notifications()` 新增 `filter_by` 参数（SQL WHERE 子句方式）
  - `server.py`：`/api/notifications` 路由接受 `?filter=all|unread|read` 查询参数
  - `portal.html`：通知中心列表上方新增 3 个筛选按钮
  - `portal_ext.js`：新增 `_notifFilter` 变量 + `switchNotifFilter()` 切换函数 + 空状态区分文案

- **决策：** 工单追踪页补全衬底色块 + 缺失样式
- **背景：** Auto-formatting 后 `.tk-status.cancelled` 和 `.ticket-view-tab` 样式缺失，工单追踪页无 `--bg-card` 背景
- **原因：** CSS 从未定义 `tk-status.cancelled`（已于 2026-06-22 在 portal_ext.js 中使用）；工单追踪内容直接在 `.page-body` 上裸露
- **实现：**
  - `portal.css`：新增 `.tk-status.cancelled`（红色底块）、`.ticket-view-tab` 基础样式、增强 `.ticket-item` padding/hover
  - `portal.html`：用 `div.chart-card` 包裹工单筛选按钮 + 列表，获得一致 `--bg-card` 背景

- **决策：** `server.py` 启动时未启动 Scheduler，导致所有定时任务静默失效
- **背景：** `startup_event()` 中初始化了认证、缓存、工单表、向量索引、Skill 注册中心，但从未调用 `Scheduler().start()`
- **原因：** 05:00 数据更新/洞察/记忆整理全部不会触发，日志中无任何 `[数据更新]`/`[数据洞察]` 输出
- **实现：**
  - `server.py`：在 `startup_event()` 末尾添加 `from src.scheduler.scheduler import Scheduler; scheduler = Scheduler(); scheduler.start()`

- **决策：** 洞察触发链重构为「数据就绪驱动」（MVP）
- **背景：** 原设计 `_run_daily_insight()` 内有时间守卫 `if now.hour != 5 or now.minute > 5: return`，且 `_daily_data_refresh()` 依赖固定时间窗口，导致：
  1. 服务器部署新代码后若错过 05:00 窗口，当天不会触发洞察
  2. 数据更新失败时（[ERP系统接口] 不可用），洞察也静默跳过，无补偿机制
  3. 手动 `--update` 启动不会触发洞察，调试困难
- **原因：** 用户反馈"5点没更新数据也没出洞察"，排查发现 scheduler 线程从未启动（已单独修复），但触发链本身仍需解耦
- **实现：**
  - `scheduler.py`：`__init__` 新增 `_last_insight_date` + `_last_refresh_context` 实例变量
  - `_daily_data_refresh()`：去掉原时间守卫（改为 05:00~05:10 窗口），数据更新完成后立即调用 `_run_daily_insight(now, data_context)`，不再等待固定时间
  - **触发条件改为「和」而非「或」**：只有 `roster_ok AND overtime_ok` 都成功才触发洞察；任一失败则跳过洞察并创建 HRIS 紧急工单
  - `_run_daily_insight()`：签名改为 `(now, data_context="")`，prompt 中注入 `本轮数据更新` 字段；同一天内 `_last_insight_date` 去重，避免重复触发
  - 新增 `_create_hris_emergency_ticket()`：任一数据源失败时，调用 `insert_task_bs()` 创建紧急工单给 HRIS 工程师（target_role="HRIS工程师", priority="urgent"）
  - 新增 `trigger_insight()` 公共方法：管理员可随时手动触发洞察（不受时间限制，强制重置 `_last_insight_date`）
- **设计原则：**
  1. 数据质量优先：双数据源都成功才出洞察，避免基于旧数据做决策
  2. 故障必须暴露：任一数据更新失败立即创建 HRIS 紧急工单，不静默跳过
  3. 数据更新是信号，洞察是响应——不被时间守卫拦截
  4. `data_context` 告诉大脑本轮更新了什么，prompt 内动态调整关注重点
  5. 当日只触发一次，避免重复通知

- **决策：** 新增 `POST /api/scheduler/trigger-insight` 手动触发接口
- **背景：** `trigger_insight()` 方法已在 scheduler 中实现，但无外部调用入口。三种场景需手动补跑：定时任务失败修复后、HRIS 手动更新数据后、服务启动/错过窗口后
- **原因：** 用户明确要求"不需等到第二天"，HRIS 更新数据后应能立即产出洞察
- **实现：**
  - `server.py`：新增 `_scheduler_instance` 全局变量，`startup_event()` 中赋值
  - `server.py`：新增 `POST /api/scheduler/trigger-insight` 路由，仅 `HR_SSC经理` 可调用
  - 权限校验：`user["role"] != "HR_SSC经理"` → 403
  - 调度器未启动检查：`_scheduler_instance is None` → 503
  - 调用 `_scheduler_instance.trigger_insight()`，强制重置 `_last_insight_date`

## 2026-06-24

- **决策：** 创建 InsightDataProvider（数据生产-消费分层）
- **背景：** `_run_daily_insight()` 内手写 SQL 聚合字符串（部门分布、角色分布、工单统计），与 `dashboard_data.py` 的 `RosterStats`/`OvertimeStats` 逻辑重复，且字段口径可能不一致
- **原因：**
  1. 数据聚合应集中在 `dashboard_data.py`，LLM prompt 生成应集中在 `insight_data.py`，各司其职
  2. 避免在 scheduler 中拼接大量 Python 字符串，降低维护成本
- **实现：**
  - 新建 `src/tools/insight_data.py`：`InsightDataProvider` 类
  - `get_enterprise_insight(dp, auth_db_stats, memory_db_stats)` 产出结构化 dict（委托 `RosterStats`/`OvertimeStats` 生成花名册摘要，`auth_db_stats`/`memory_db_stats` 补充系统指标）
  - `format_enterprise_insight_for_llm(insight)` 将 dict 转为 Markdown 表格（仅 2KB），LLM prompt 直接嵌入
  - `scheduler.py`：`_run_daily_insight()` 改为调用 Provider，新增 `_gather_auth_db_stats()` / `_gather_memory_db_stats()` 作为参数输入

- **决策：** `_run_daily_insight()` 从手写 SQL 摘要迁移到 Markdown 表驱动
- **背景：** 原 `_run_daily_insight()` 在方法体内用 Python 字符串拼接 20+ 行部门/角色分布摘要，每次修改数据口径都要改这段字符串拼接逻辑
- **原因：** LLM 读 Markdown 表的效率远高于读自然语言段落；数据格式与内容生成解耦
- **实现：**
  - prompt 中数据部分替换为 Provider 生成的 Markdown 表格
  - prompt 头部增加 `【请基于下列数据表进行洞察分析，输出自然语言描述，禁止输出 JSON】` 强约束
  - `_run_daily_insight()` 逻辑从 ~80 行缩减到 ~50 行，纯编排，无业务逻辑

## 2026-06-22

- **决策：** 删除 `docs/` 目录，建立 `memory/` 作为项目知识库 + Cline 工作记忆的统一目录
- **背景：** 项目知识文档（架构、数据管理）与 Cline 跨 session 记录混在 `docs/` 中，Cline 自己生成的历史总结等也不规范地放在 `docs/`
- **原因：** 统一归口到 `memory/`，根目录文档只保留根级 `architecture.md`（英文/可视化总览）

## 2026-06-22

- **决策：** 清理根目录杂文件（test/、temp/、大胃王/、测试脚本等）
- **背景：** 根目录被临时文件和测试文件堆积，不符合项目规范
- **原因：** 保持根目录只放入口文件（README、requirements.txt等），临时文件放 logs/ 或 scripts/

## 2026-06-21（前期已有）

- **决策：** 采用"信息充足性原则"代替 hardcoded 问题-工具映射
- **背景：** SemanticExtraction skill 强化"不做语义正则匹配"
- **原因：** LLM 更能灵活判断信息充分性，减少维护成本