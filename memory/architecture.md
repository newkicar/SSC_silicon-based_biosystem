# SSC硅基生物系统 — 架构与开发指南

> 本文档是项目的技术参考手册，供开发者和AI工具理解项目全貌。
> 历史进展详见 git log，本文档只保留当前架构和关键决策。

**最后更新：** 2026-06-29
**版本：** v3.1
**仓库：** https://gitee.com/thomas_lee_0627/thomas-project.git

---

## 一、项目定位

将HR SSC（人力资源共享服务中心）重构为一个**以AI为神经中枢的硅基生命体**——能感知、能思考、能进化、能与人类协同。

- **技术栈：** Python 3.10+ / LangChain / deepagents / FastAPI / SQLite / ECharts
- **大模型：** 本地部署 [大模型名称]
- **用户规模：** 44个示例用户（34管理层 + 9 SSC操作层 + 1管理员），19个RBAC角色

---

## 二、系统架构

### 2.1 信息流

```
员工输入（Web门户 / Staff终端CLI）
  ↓
 ① 上行脊髓（身份识别 + 意图增强 + 渠道分流）
  ├─ Web端 → RAG政策搜索路径（只返回政策知识，不暴露个人信息）
  └─ CLI端 → 联合搜索路径（RAG政策 + databases/Excel向量化检索）
  ↓
  ② 中枢神经节（反射弧模式匹配 → 结果作为上下文传递给大脑）
  ↓
  ③ 大脑 Agent Loop（deepagents agent loop，带4个搜索工具）
     LLM自主决策：审视情报包 → 判断信息充足性 → 调用工具补充 → 推理 → 回答
  ↓
  ④ 输出格式化 + 任务分派（dispatch_actions JSON → 工单/CLI任务/通知）
  ↓
 ⑤ 下行脊髓（任务翻译 + 编排 + 终端路由 + 执行）
  ↓
 回复送达用户（Web / CLI）
```

### 2.2 生物隐喻映射

| 人体器官 | 文件 | 职责 |
|---------|------|------|
| 大脑 | `src/brain.py` | deepagents agent loop + 4个搜索工具，禁用文件系统 |
| 上行脊髓 | `src/spine/ascending.py` | 身份识别 + 渠道标注 + RAG搜索 + 情报包组装 |
| 中枢神经节 | `src/ganglion/reflex.py` | 16个反射弧模式 + RAG质量检查 |
| 下行脊髓 | `src/spine/descending.py` | 任务翻译 + 编排 + 终端路由 |
| 分派器 | `src/spine/dispatcher.py` | 解析 dispatch_actions JSON，创建工单/CLI任务/通知 |
| 秘书 | `src/tools/data_sources.py` | DataSecretary — 数据采集、花名册查询、[ERP系统接口]调用 |
| 神经突触 | `src/data/task_queue.py` | 统一消息总线（task_bs + task_st + event_bus） |
| 上下文池 | `src/data/context_pool.py` | 事务CRUD + 时间线 + 决策记录 |
| 三层记忆 | `src/memory/` | State(SQLite) + MD文件 + 向量索引 |
| 免疫系统 | `src/security/immune.py` | SQL注入/XSS检测 + 自愈 + Token管控 |
| 定时调度 | `src/scheduler/scheduler.py` | 7个定时任务（超时扫描/心跳/记忆整理/数据更新/晨报/日报/Token监控） |

### 2.3 目录结构

```
.gitignore
README.md
requirements.txt          # 依赖清单
fix_port_8000.bat         # 端口清理批处理
密码清单.xlsx              # 密码记录

src/                      # 服务端核心代码
├── brain.py              # 大脑（deepagents agent loop + 4搜索工具）
├── main.py               # 主入口（完整信息流 + 免疫 + 上下文池 + 调度器）
├── api/
│   ├── server.py         # FastAPI 40+端点（认证/Dashboard/工单/通知/Skill注册/即时通讯）
│   ├── portal.html       # 门户前端（HTML + CSS + JS模块）
│   ├── static/           # CSS/JS静态资源
│   └── services.py       # 工单/通知/个人中心/即时通讯业务逻辑（含通知路由）
├── config/               # 配置文件（角色路由等）
├── data/
│   ├── task_queue.py     # 统一数据层（task_bs + task_st + event_bus）
│   ├── context_pool.py   # 上下文池（事务CRUD）
│   ├── cli_tasks.py      # CLI任务表
│   └── skill_registry.py # Skill注册中心
├── ganglion/
│   └── reflex.py         # 中枢神经节（16个反射弧）
├── insight_agent/        # 洞察子代理
│   ├── agent.py          # 洞察生成 + JSON解析 + 验证重试
│   ├── insight-skill/    # 洞察生成技能定义
│   └── json_parser_skill/ # JSON解析子代理技能
├── memory/
│   ├── database.py       # SQLite记忆层（conversations表）
│   └── md_memory.py      # MD文件记忆层
├── scheduler/
│   ├── scheduler.py      # 定时任务调度器（含洞察生成逻辑）
│   └── work_time.py      # 工作时间判断
├── security/
│   ├── auth.py           # 认证（注册/登录/token/会话/兼岗）
│   ├── permissions.py    # RBAC权限控制（19角色 + 范围限制 + 兼岗并集）
│   ├── seed_users.py     # 种子用户导入
│   └── admin.py          # 管理员账户管理
├── skills/               # 服务端Skill目录
│   └── role_routing/     # 角色职责路由指南
├── spine/
│   ├── ascending.py      # 上行脊髓（身份识别+意图增强+向量RAG+数据预取）
│   ├── descending.py     # 下行脊髓（任务翻译+编排+终端路由）
│   └── dispatcher.py     # 分派器（dispatch_actions → 工单/CLI任务/通知）
└── tools/
    ├── data_sources.py   # DataSecretary（花名册查询+[ERP系统接口]+考勤查询）
    ├── dashboard_data.py # Dashboard数据源（7个Excel+多级缓存）
    ├── insight_data.py   # 洞察数据提供者
    └── vector_rag.py     # 向量RAG（bge-m3 1024维，policy+db索引）

staff/                    # 员工终端（CLI）
├── terminal.py           # 交互式终端（/skill /chat /tasks /ticket /marathon）
├── llm.py                # ToolCallFixChatOpenAI（修复[大模型名称]工具调用格式）
├── role_agent.py         # 角色Agent
├── settings.py           # 员工端配置
├── skill_sync.py         # CLI端Skill同步
├── marathon/             # 多步骤业务流程自动执行引擎
│   ├── graph.py          # LangGraph 状态图定义
│   ├── state.py          # MarathonState 数据模型
│   ├── config.py         # 常量配置（步骤状态码等）
│   ├── capability_registry.py  # 能力注册表（动态发现搜索工具+Skill+系统能力）
│   └── nodes/
│       ├── planner.py    # 规划节点（LLM拆解任务为子步骤，标注每步 capability）
│       ├── executor.py   # 执行节点（按 capability 动态注入工具，幂等性缓存）
│       ├── validator.py  # 验证节点（硬证据检查 + RubricMiddleware 评分）
│       ├── committer.py  # 提交节点（步骤结果归档）
│       └── error_handler.py  # 错误处理节点
├── skills/               # CLI端Skill目录（含 skill-outlook-controller 等）
└── tools/                # CLI端工具

scripts/                  # 运维脚本
├── manage_roles.py       # 兼岗双向管理（导出/导入Excel）
├── cleanup_test_data.py  # 清理测试数据
├── refresh_roster.py     # 花名册自动刷新
├── build_overtime.py     # 加班数据自动构建
├── sync_users_from_json.py # 用户信息同步
└── ...                   # 其他辅助脚本

databases/                # 数据文件（Excel）
├── 员工花名册.xlsx       # 花名册（花名册sheet + 人数预算sheet）
├── 加班基础数据.xlsx     # 考勤/加班/出勤率（按月追加）
├── 元数据-公司组织架构.xlsx
├── 各中心部门人工成本.xlsx
├── 人效数据-公司级.xlsx
├── 离职率数据.xlsx
├── 待招岗位需求.xlsx
└── assistance/           # 辅助数据（不统计的人等）

data/                     # 运行时数据（向量索引缓存等）
RAG_files/                # 政策文档（向量化检索用）
logs/                     # 运行时日志
memory/                   # 项目知识库 + Cline 跨 session 工作记忆
├── architecture.md       # 架构与开发指南（本文档）
├── data_management.md    # 数据管理操作手册
├── progress.md           # 跨 Session 工作进度
├── decisions.md          # 架构与实现决策记录
└── blockers.md           # 当前阻塞与已知风险

memories/                 # AGENTS.md 长期记忆文件存放目录
resources/                # 静态资源（Logo 等）
```

---

## 三、核心设计原则

### 3.1 大脑设计

- **单一agent loop**：`create_deep_agent()` 返回的 CompiledStateGraph 本质上是一个"agent"节点，LLM自主决定何时调用工具
- **禁用文件系统**：通过 HarnessProfile 排除 ls/read_file/write_file/glob/grep，防止大脑编造数据
- **4个搜索工具**：search_policy / search_employee_database / query_employee_roster / query_attendance
- **信息充足性原则**：不硬编码"什么问题搜什么"，给LLM通用原则让它自行推理

### 3.2 渠道分流

| 渠道 | 数据来源 | 适用场景 |
|------|---------|---------|
| Web端 `[渠道:web]` | RAG_files/ 政策文档 | 政策咨询、制度问答、不暴露个人信息 |
| CLI端 | RAG_files/ + databases/ | 个人数据查询、HR内部操作 |

### 3.3 数据查询通用化

用向量化检索替代硬编码字段查询。将数据源的所有字段转为文本块后向量化，让AI通过语义匹配找到相关数据。新增数据源只需放入 `databases/` 目录，重启即自动索引。

### 3.4 任务分派（dispatch_actions）

大脑不直接执行任何操作。需要转交任务时，在回复末尾输出 `dispatch_actions` JSON，由分派器自动创建工单/CLI任务/通知。

### 3.5 敏感话题处理

涉及劳动仲裁、举报、索赔等敏感话题时，大脑立即转交HR（创建urgent工单），不告知员工操作流程。

---

## 四、洞察通知系统

### 4.1 架构

```
Daily Data Refresh
  ├─ RosterStats / OvertimeStats（dashboard_data.py）→ 企业数据聚合
  ├─ _gather_auth_db_stats() / _gather_memory_db_stats()（scheduler.py）→ 系统指标
  ↓
  InsightDataProvider.get_enterprise_insight() → 结构化 dict
  ├─ roster_summary / overtime_summary（花名册/加班摘要）
  ├─ roster_detail / overtime_detail（明细）
  └─ system_metrics（工单/任务/用户/事件统计）
  ↓
  InsightDataProvider.format_enterprise_insight_for_llm() → Markdown 表格（~2KB）
  ↓
  _run_daily_insight() 拼入 prompt，大脑「读表 → 洞察 → dispatch_actions」
  ↓
  dispatcher → create_notification() → 按路由规则推送
```

### 4.2 洞察子代理

使用 `create_deep_agent()` 创建独立的洞察子代理，加载 `insight-skill/SKILL.md` 作为 system prompt。

- **输出验证**：`validate_insight_output()` 确保包含 `insight_level`、`insight_org`、`insight_type` 字段
- **自动重试**：验证失败时返回错误信息，让子代理重新生成，最多 3 次
- **JSON解析**：`parse_json_from_response()` 使用正则+json库提取JSON，支持markdown代码块

### 4.3 通知路由

`resolve_notification_targets()` 根据洞察类型、级别、管辖范围精准路由：

| 洞察级别 | 接收者 | 匹配规则 |
|---------|--------|---------|
| company | 总经理、副总经理 | 必须匹配公司归属（company字段） |
| center | 中心总监、HRBP | 洞察org必须匹配用户org |
| department | 部门经理、HRBP | 洞察org必须匹配用户org |
| SSC操作层 | 按specialization匹配 | insight_type匹配岗位职责 |

### 4.4 公司级洞察隔离

总经理/副总经理按公司归属接收通知：
- [用户A](emp_001)、[用户B](emp_002) → 只接收[公司名称]公司公司级洞察
- 刘旭(110004)、刘帅(110270) → 只接收[关联公司]公司级洞察

---

## 五、Marathon 引擎（多步骤自动执行）

### 5.1 总体架构

Marathon 是一个多步骤业务流程自动执行引擎，基于 LangGraph 构建。

```
用户任务
  ↓
Planner（规划节点）
  → LLM 拆解为 N 个子步骤
  → 每个步骤标注 capability（能力标签）
  → 自动指定 acceptance_criteria（验收标准）
  ↓
Executor（执行节点）× N 步
  → 按 capability 动态注入工具集（见 5.2）
  → 上行脊髓数据预取（仅首次，重试跳过）
  → SSC 团队信息注入（让大脑知道该分派给谁）
  → RubricMiddleware 评分（不达标自动重试，最多3次）
  ↓
Validator（验证节点）
  → 硬证据检查（dispatch_actions、CLI任务输出等）
  → RubricMiddleware 评分结果校验
  ↓
Committer（提交节点）
  → 结果归档
```

### 5.2 动态工具隔离（核心设计）

executor 按步骤的 `capability` 标签动态创建 brain agent，**只注入当前步骤需要的工具**：

| capability 类型 | 工具集 | 目的 |
|----------------|--------|------|
| `query_data` / `search_policy` 等搜索类 | 仅搜索工具 | 防止查询步骤越界执行后续操作（如发邮件） |
| `skill-outlook-controller` 等 skill- 开头 | 搜索 + execute_skill | 允许执行实际操作 |
| `create_ticket` / `create_notification` 等系统能力 | 仅搜索工具 | 结果通过 dispatch_actions JSON 输出 |

### 5.3 execute_skill 幂等性缓存

executor 内置幂等性缓存，防止 RubricMiddleware 重试时重复执行有副作用的操作：

```
缓存 key = hash(execution_context_id + task_description)
execution_context_id = "marathon-{marathon_id}-s{step_id}-a{attempt}"
```

- 同一 agent loop 内（Rubric 重试）：相同任务直接返回缓存结果（60秒有效）
- 不同步骤/不同 attempt：不同 execution_context_id，缓存不命中，正常执行
- LRU 上限：最多 64 条缓存，超出时淘汰最旧条目，防止长期运行内存泄漏

---

## 六、定时任务

| 时间 | 任务 | 说明 |
|------|------|------|
| 02:00 | 凌晨记忆整理 | 调用大脑提炼对话中的关键决策 |
| 05:00 | 数据自动更新 | 刷新花名册 + 加班数据 + 增量更新向量索引 + **自动洞察通知** |
| 08:00 | 晨间扫描 | 生成晨报 |
| 18:00 | 日终总结 | 生成日报告 |
| 每30秒 | 超时扫描 | 扫描超时任务，重试/重新分配/升级 |
| 每30分钟 | 心跳巡检 | 快照对比，差异报告传给大脑 |
| 每5分钟 | Token监控 | 对话量监控 |

---

## 七、角色与权限

### 7.1 RBAC模型

- **排除法权限**：默认允许，deny_fields 指定不可见字段
- **范围限制**：scope_level 控制数据可见范围（company/department/self）
- **兼岗并集**：一人多角色时，权限取并集
- **19个角色**：HR_SSC经理、HR_SSC学科经理、高级HRIS工程师、HRIS工程师、员工关系主管/专员、招聘主管/专员、薪酬主管/专员、考勤专员等

### 7.2 角色配置文件

| 文件 | 作用 |
|------|------|
| `src/config/users.json` | 用户账号、角色、访问渠道控制 |
| `src/skills/role_routing/SKILL.md` | 角色职责路由指南 |
| `src/spine/dispatcher.py` | 角色→部门映射表 |

---

## 八、辅助工具

### 8.1 兼岗配置管理

使用 Excel 双向管理兼岗配置，无需手动写 SQL：

```bash
# 1. 导出当前兼岗配置
python scripts/manage_roles.py export

# 2. 编辑 scripts/roles_export.xlsx 文件

# 3. 导入修改后的配置
python scripts/manage_roles.py import scripts/roles_export.xlsx
```

### 8.2 清理测试数据

开发测试后清理垃圾数据，保留用户配置：

```bash
python scripts/cleanup_test_data.py
```

清理内容：
- 备份数据库到 `data/backups/`
- 清空对话、任务、通知、工单、聊天等测试数据
- 清空 `logs/` 和 `memories/` 目录

### 8.3 端口冲突解决

当 8000 端口被占用时，运行以下脚本释放端口：

```bash
fix_port_8000.bat
```

---

## 九、开发规范

### 9.1 编码规则

- **禁止正则做语义匹配**：交给LLM做语义理解
- **数据查询通用化**：向量化检索，不硬编码字段
- **工具描述要具体**：说明能获取什么、什么时候用
- **返回值要自解释**：带来源和字段解释，不要裸数据
- **System Prompt只写业务**：不要复制官方harness prompt
- **场景特化指令放在 Skill 里**：不要污染通用执行上下文

### 9.2 Windows + deepagents 注意事项

- 子进程编码：`python -X utf8` 或 `PYTHONIOENCODING=utf-8`
- Skill路径：相对路径 + `/` 分隔符
- ToolCall修复：使用 `staff/llm.py` 的 ToolCallFixChatOpenAI
- HarnessProfile：从 `deepagents.profiles` 导入

### 9.3 Marathon 节点规则

- 所有节点返回纯 dict（不返回 dataclass 对象）
- executor 按 capability 动态创建 brain agent，不是全局单例
- 重试时清空 context_summary，跳过 RAG 情报包（避免 token 累积）
- stream_callback 只在节点执行完成后触发
- RubricMiddleware 重试上限：3 次

---

## 十、关键API端点

### 认证
- `POST /api/auth/login` — 登录
- `GET /api/auth/me` — 当前用户信息

### Dashboard
- `GET /api/dashboard/kpi` — KPI卡片
- `GET /api/dashboard/charts` — 图表数据
- `GET /api/dashboard/overtime` — 加班分析
- `GET /api/dashboard/dept-detail` — 部门明细表
- `GET /api/dashboard/efficiency` — 人效指标
- `GET /api/dashboard/cost-analysis` — 成本分析

### 智能问答
- `POST /api/chat` — 智能问答（同步）
- `POST /api/chat/stream` — 智能问答（SSE流式）

### 工单/通知
- `GET/POST /api/tickets` — 工单CRUD
- `GET /api/notifications` — 通知列表

### 数据管理
- `python -m src.api.server --update-db <文件名.xlsx>` — 单文件索引更新
- `python -m src.api.server --update` — 全量索引重建

---

## 十一、历史里程碑

| 阶段 | 核心成果 |
|------|---------|
| Phase 1 MVP | 统一数据层 + 下行脊髓 + 端到端信息流 |
| Phase 2 核心能力 | 反射弧扩展(16个) + 上下文池 + 秘书机制 + 免疫系统 + RBAC |
| Phase 3 感知 | 上行脊髓(身份识别+意图增强) + 向量RAG |
| Phase 4 大脑 | deepagents agent loop + 4搜索工具 + 渠道分流 |
| Phase 5 Web | FastAPI + 门户前端 + Dashboard |
| Phase 6 Skill | Skill Registry + deepagents官方执行 |
| Phase 7 认证 | OAuth2 + RBAC + 19角色 |
| Phase 8 工单 | 工单系统 + 任务分派 + dispatch_actions |
| Phase 9 Marathon | 多步骤业务流程自动执行（基础版） |
| Phase 10 数据 | 花名册自动刷新 + 加班数据构建 + 每日自动更新 |
| Phase 11 Marathon强化 | 能力感知规划 + 动态工具隔离 + 幂等性缓存 + Skill指令预注入 |
| Phase 12 洞察 | 洞察子代理 + 通知精准路由 + 公司级洞察隔离 |