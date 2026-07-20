# 🧬 SSC硅基生物系统

> 将HR SSC（人力资源共享服务中心）重构为一个以AI为神经中枢的硅基生命体——能感知、能思考、能进化、能与人类协同。

**技术栈：** Python 3.10+ / LangChain / LangGraph / deepagents / FastAPI / SQLite / ECharts
**大模型：** 本地部署 [大模型名称]
**用户规模：** 44个示例用户（34管理层 + 9 SSC操作层 + 1管理员），19个RBAC角色

---

## 快速开始

### 环境要求
- Python 3.10+（推荐 Anaconda 虚拟环境）
- Windows 10/11（员工端 GUI 自动化需要 Windows）
- 内网（需要访问 LLM 模型和 [ERP系统接口] 服务）

### 安装依赖
```bash
pip install -r requirements.txt
```

### 启动服务端（API服务）

```bash
# 正常启动（加载已有索引缓存）
set PYTHONIOENCODING=utf-8
python -m src.api.server

# 数据更新后（强制重建向量索引）
python -m src.api.server --update

# 单独更新花名册索引
python -m src.api.server --update-db 员工花名册.xlsx

# 指定端口
python -m src.api.server --port 8001
```

**启动后自动完成：** 认证数据库初始化 → Dashboard缓存预热 → 向量索引加载（RAG 180切片 + 数据库31747行） → 定时调度器启动

| 地址 | 说明 |
|------|------|
| `http://localhost:8000/portal` | 门户前端（数据看板/智能问答/工单系统/通知中心/个人中心） |
| `http://localhost:8000/docs` | Swagger API文档 |
| `http://localhost:8000` | 导航首页 |

### 启动员工终端（CLI）

```bash
# 交互式登录（密码输入显示星号）
python -X utf8 -m staff.terminal --server http://localhost:8000

# 自动登录
python -X utf8 -m staff.terminal --server http://localhost:8000 --user Vxxxxx --password 123456
```

**终端命令体系：**

| 命令 | 说明 |
|------|------|
| 普通消息 | 直接输入，与SSC大脑对话 |
| `/tasks` | 查看待处理任务 + 接收的工单 |
| `/task exec` | 自动处理任务 |
| `/task done <CT/TK>` | 标记任务/工单完成 |
| `/task info <CT/TK>` | 查看任务/工单详情 |
| `/ticket` | 提交新工单 |
| `/ticket cancel <TK>` | 撤销我提的工单 |
| `/my ticket` | 查看我提的工单 |
| `/skill <需求>` | 执行Skill（AI自动匹配） |
| `/skill list` | 查看可用Skill列表 |
| `/marathon <任务>` | 业务流程马拉松（多步骤自动执行） |
| `/chat <姓名>` | 与同事实时聊天 |
| `/exit chat` | 结束当前聊天 |
| `/whoami` | 用户信息 |
| `/change password` | 修改密码 |

---

## 系统架构

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
     4个搜索工具：search_policy / search_employee_database / query_employee_roster / query_attendance
  ↓
  ④ 输出格式化 + 任务分派
     - 直接回复（信息充足时）
     - dispatch_actions JSON（需要分派任务时 → 创建工单/CLI任务/通知）
  ↓
 ⑤ 下行脊髓（任务翻译 + 编排 + 终端路由 + 执行）
  ↓
 回复送达用户（Web / CLI）
```

**核心原则：**
- 大脑使用 deepagents agent loop（单一节点），LLM自主决定何时调用搜索工具
- 大脑被禁止使用文件系统工具，通过4个搜索工具获取数据
- 渠道分流：Web端走RAG政策，CLI端走联合搜索（RAG + 数据库）
- Skill匹配交给 deepagents 官方 progressive disclosure
- **所有执行动作通过 `dispatch_actions` JSON 下发**，大脑不直接执行任何操作
- 敏感话题（仲裁/举报/索赔等）立即转交HR，不告知操作流程

---

## 工单与任务分派

### 工作流程

1. **员工提问** → 大脑分析 → 输出 `dispatch_actions` JSON
2. **分派器** 根据 JSON 自动创建工单 + CLI任务
3. **工单** 分配给具体处理人（通过 `target_username` 指定，基于 specialization 匹配）
4. **目标角色** 通过 `/tasks` 查看待处理工单，通过 `/task info <TK>` 查看详情
5. **完成/撤销**：接收人 `/task done <TK>` 完成，提交人 `/ticket cancel <TK>` 撤销

### 大脑分派格式（格式C）

大脑在需要转交任务时，必须在回复末尾输出 `dispatch_actions` JSON：

```json
{
  "dispatch_actions": [
    {
      "type": "create_ticket",
      "target_role": "员工关系专员",
      "target_username": "110807",
      "title": "员工咨询劳动仲裁事宜",
      "description": "详细描述",
      "priority": "urgent",
      "category": "员工关系"
    }
  ]
}
```

**关键规则：**
- `target_username`：指定具体处理人用户名（从 SSC人员职责清单 的 specialization 匹配）
- 未指定 `target_username` 且角色有多人时，工单可见但未指定具体处理人
- 无 `dispatch_actions` 的"转交"不会被送达——系统不会自动创建工单

### 敏感话题处理

涉及劳动仲裁、举报、索赔、群体性事件等敏感话题时：
- 大脑立即转交HR，回复模板消息
- 创建 urgent 级别工单
- 不告知员工任何操作流程

---

## 角色与权限

### 角色职责配置

| 配置文件 | 作用 |
|---------|------|
| `src/config/users.json` | 用户账号、角色、访问渠道控制 |
| `src/skills/role_routing/SKILL.md` | 角色职责路由指南——每个岗位负责什么工作 |
| `src/spine/dispatcher.py` | 角色→部门映射表 |

**SSC角色列表：**

| 角色 | 职责范围 |
|------|---------|
| HR_SSC经理 | SSC全面管理、跨部门协调 |
| HR_SSC学科经理 | 学科领域决策、政策执行监督 |
| 高级HRIS工程师 | 系统架构、数据安全、接口对接 |
| HRIS工程师 | 系统日常维护、数据对接 |
| 员工关系主管 | 员工关系管理、劳动争议处理 |
| 员工关系专员 | 合同管理、证明开具、社保办理 |
| 招聘主管/专员 | 招聘策略、简历筛选、面试安排 |
| 薪酬主管/专员 | 薪酬体系、薪资核算、社保公积金 |
| 考勤专员 | 考勤管理、排班管理 |

### 用户信息同步

`users.json` 是种子文件，首次运行时导入数据库。之后修改不会自动同步：

```bash
# 同步 users.json 到数据库
python -X utf8 scripts/sync_users_from_json.py
```

### Skill 目标角色

在 SKILL.md 的 YAML frontmatter 中通过 `target_roles` 控制可见性：

```yaml
---
name: skill-outlook-controller
description: 自动化操作Outlook邮件客户端...
target_roles:
  - HR_SSC学科经理
  - 高级HRIS工程师
  - 员工关系专员
---
```

- `target_roles` 为空或不写 → 所有角色可见
- 指定角色后 → 只有这些角色可用

---

## 数据管理

### 数据源

| 数据源 | 文件 | 用途 | 更新方式 |
|--------|------|------|---------|
| 员工花名册 | `databases/员工花名册.xlsx` | 人事数据、部门架构 | `scripts/refresh_roster.py` |
| 加班基础数据 | `databases/加班基础数据.xlsx` | 考勤/加班/出勤率 | `scripts/build_overtime.py` |
| 政策文档 | `RAG_files/` | 员工手册、考勤制度等 | 手动放入 |
| 向量索引 | `data/db_index.pkl` | 加速语义检索 | 自动/手动 |

### 花名册自动刷新

从CC/DL人员清册解密 + [ERP系统接口]岗级匹配，自动生成完整花名册：

```bash
# 刷新花名册（需修改脚本中 CC/DL 文件路径）
python -X utf8 scripts/refresh_roster.py

# 刷新后更新向量索引
python -m src.api.server --update-db 员工花名册.xlsx
```

**处理流程：** 解密CC/DL → 合并4个sheet → [ERP系统接口]岗级匹配 → 部门规范化 → 中心补全 → 衍生字段 → 蓝领白领分类 → 特殊修正 → 删除高管 → 大级别识别 → 括号替换 → 写入Excel

### 加班数据自动构建

从SAP考勤API获取数据，计算每人每月加班时长/出勤率，追加写入Excel：

```bash
# 默认：当天=1日拉上月整月，≥2日拉本月1日~昨天
python -X utf8 scripts/build_overtime.py

# 指定日期范围
python -X utf8 scripts/build_overtime.py --begin 2026-01-01 --end 2026-06-17
```

**写入逻辑：** 读取已有文件 → 删除目标月份旧数据 → 追加新数据 → 保留其他月份（当月覆盖，跨月累加）

### 服务端启动与数据更新

```bash
# 正常启动
python -m src.api.server

# 指定端口 + 监听地址
python -m src.api.server --port 8001 --host 0.0.0.0

# 只更新指定文件的向量索引（数据更新后使用）
python -m src.api.server --update-db 员工花名册.xlsx
python -m src.api.server --update-db 加班基础数据.xlsx

# 全量重建所有向量索引
python -m src.api.server --update
```

**自动更新：** 服务运行时，每天凌晨05:00自动刷新花名册 + 加班数据 + 向量索引（详见定时任务章节）

---

## 定时任务

| 任务 | 时间 | 说明 |
|------|------|------|
| 凌晨记忆整理 | 02:00 | 调用大脑提炼关键决策和待办 |
| 数据自动更新 | 05:00 | 刷新花名册 + 加班数据 + 增量更新向量索引 + **自动洞察通知** |
| 晨间扫描 | 08:00 | 生成晨报（待办事项+关注事项） |
| 日终总结 | 18:00 | 生成日报告（重要事项+明日建议） |

### 主动洞察通知（数据更新后自动触发）

数据自动更新完成后，系统自动调用大脑分析最新数据并生成洞察通知，采用「**数据就绪驱动**」：
- 数据更新成功立即触发洞察，不受时间窗口限制
- prompt 中注入本轮数据更新上下文（`data_context`），大脑据此动态调整关注重点
- 同一天只触发一次，避免重复通知
- 数据质量优先：双数据源（花名册 + 加班）都更新成功才触发洞察；任一失败则跳过洞察并创建 HRIS 紧急工单

**新架构（InsightDataProvider 统一数据源）：**

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

- **调用链**：`scheduler → _gather_auth_db_stats() / _gather_memory_db_stats() → InsightDataProvider → Markdown 表 → brain agent loop → dispatcher → create_notification()`
- **时间窗口**：每天 05:00~05:10 执行数据更新，更新完成后立即触发洞察（同一 tick 内）
- **触发条件**：`roster_ok AND overtime_ok` → 立即调用 `_run_daily_insight(now, data_context)`
- **失败处理**：任一数据源更新失败 → 跳过洞察，自动创建紧急工单给 HRIS 工程师（`target_role="HRIS工程师"`, `priority="urgent"`）
- **路由规则（洞察子代理 + 输出验证闸门）**：
  - 洞察生成改为子代理任务，使用 `src/insight_agent/` 目录下的专门实现
  - 输出验证：`validate_insight_output()` 确保包含 `insight_level`、`insight_org`、`insight_type` 字段
  - 自动重试：验证失败时返回错误信息，让子代理重新生成，最多 3 次
  - 管理者：按 `notification_scope='manager'` 和管辖域推送
  - SSC 团队：按 `notification_scope='ssc'` 和 specialization 匹配推送
  - 普通员工：`notification_scope='employee'`，不接收洞察通知
- **通知去重**：同一轮次相同 `(target_user, title, content)` 不会重复推送；同一天只生成一次洞察（`_last_insight_date` 日期去重）
- **标题/内容质量约束**：prompt 规定 title 必须「见文知义」（禁止"洞察A""通知B"等空泛标题），content 必须包含具体数据 + 变化趋势 + 建议动作
- **通知筛选**：Web 门户通知中心支持按「全部/未读/已读」筛选

#### 手动触发洞察（管理员 API）

当以下场景需要手动补跑洞察时，管理员可调用 API：

```bash
POST /api/scheduler/trigger-insight
Authorization: Bearer <管理员token>
```

**使用场景：**
1. 定时数据更新失败后，修复数据源需要补跑洞察
2. HRIS 手动更新了花名册或加班数据，需要立即产出洞察
3. 服务刚启动或错过 05:00 时间窗口，需要补跑当日洞察

该接口不受时间守卫限制，强制重置当日洞察状态后立即执行。

---

## 辅助工具

### 端口冲突解决

当 8000 端口被占用时，运行以下脚本释放端口：

```bash
fix_port_8000.bat
```

### 兼岗配置管理

使用 Excel 双向管理兼岗配置，无需手动写 SQL：

```bash
# 1. 导出当前兼岗配置
python scripts/manage_roles.py export

# 2. 编辑 scripts/roles_export.xlsx 文件

# 3. 导入修改后的配置
python scripts/manage_roles.py import scripts/roles_export.xlsx
```

### 清理测试数据

开发测试后清理垃圾数据，保留用户配置：

```bash
python scripts/cleanup_test_data.py
```

清理内容：
- 备份数据库到 `data/backups/`
- 清空对话、任务、通知、工单、聊天等测试数据
- 清空 `logs/` 和 `memories/` 目录

### 数据更新脚本

```bash
# 刷新花名册
python -X utf8 scripts/refresh_roster.py

# 构建加班数据
python -X utf8 scripts/build_overtime.py

# 同步用户配置
python -X utf8 scripts/sync_users_from_json.py
```

---

## 技术架构详情

- **大脑**：`src/brain.py` — deepagents agent loop + 4个搜索工具，禁用文件系统
- **上行脊髓**：`src/spine/ascending.py` — 身份识别 + 渠道标注 + RAG搜索
- **下行脊髓**：`src/spine/descending.py` — 任务翻译 + 编排 + 终端路由
- **分派器**：`src/spine/dispatcher.py` — 解析 dispatch_actions JSON，创建工单/CLI任务
- **员工终端**：`staff/terminal.py` — CLI交互 + Skill执行 + 实时聊天
- **Marathon**：`staff/marathon/` — 多步骤业务流程自动执行