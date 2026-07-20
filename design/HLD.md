# HLD - 高层设计文档

> 本文档描述 HR SSC 硅基生物系统的整体架构设计。

---

## 1. 概述

- **设计名称**: HR SSC 硅基生物系统（组织数字孪生）
- **作者**: Thomas Lee
- **创建日期**: 2026-06-29
- **最后更新**: 2026-07-02

## 2. 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户层                                       │
│  ┌──────────────┐              ┌──────────────┐                     │
│  │ Web 门户     │              │ Staff CLI    │                     │
│  │ (portal.html)│              │ (terminal.py)│                     │
│  └──────┬───────┘              └──────┬───────┘                     │
│         │                             │                              │
├─────────┼─────────────────────────────┼──────────────────────────────┤
│         ▼                             ▼                              │
│                    ┌──────────────────────────┐                     │
│                    │    认证层 (auth.py)       │                     │
│                    │  OAuth2 + RBAC + Token    │                     │
│                    └──────────┬───────────────┘                     │
│                               │                                      │
├───────────────────────────────┼──────────────────────────────────────┤
│                               ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │              上行脊髓 (ascending.py)                       │        │
│  │  身份识别 + 渠道标注 + 意图增强 + 向量RAG + 数据预取       │        │
│  └────────────────────────┬────────────────────────────────┘        │
│                           │                                          │
│                           ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │           中枢神经节 (reflex.py)                           │        │
│  │  16个反射弧模式 + RAG质量检查                              │        │
│  └────────────────────────┬────────────────────────────────┘        │
│                           │                                          │
│                           ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │                大脑 (brain.py)                             │        │
│  │  deepagents agent loop + 4搜索工具 + HarnessProfile沙箱  │        │
│  │  ┌───────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │        │
│  │  │search_    │ │search_   │ │query_    │ │query_    │  │        │
│  │  │policy     │ │employee_ │ │roster    │ │attendance│  │        │
│  │  └───────────┘ └──────────┘ └──────────┘ └──────────┘  │        │
│  └────────────────────────┬────────────────────────────────┘        │
│                           │                                          │
│                           ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │           下行脊髓 (descending.py)                         │        │
│  │  任务翻译 + 编排 + 终端路由                                │        │
│  └────────────────────────┬────────────────────────────────┘        │
│                           │                                          │
│              ┌────────────┴────────────┐                            │
│              ▼                         ▼                            │
│  ┌──────────────────┐      ┌──────────────────────┐                │
│  │ 分派器            │      │ Marathon 引擎         │                │
│  │ (dispatcher.py)  │      │ (marathon/)           │                │
│  │ • 创建工单        │      │ • Planner (规划)      │                │
│  │ • 创建通知        │      │ • Executor (执行)     │                │
│  │ • 创建CLI任务     │      │ • Validator (验证)    │                │
│  └────────┬─────────┘      │ • Committer (提交)    │                │
│           │                └──────────┬───────────┘                │
│           │                           │                              │
│  ┌────────┴─────────┐      ┌──────────┴───────────┐                │
│  │ 数据存储层        │      │ execute_skill 工具    │                │
│  │ • SQLite         │      │ • Outlook 邮件        │                │
│  │ • Excel 向量索引  │      │ • 会议室预约          │                │
│  │ • MD 记忆文件    │      │ • GUI 自动化          │                │
│  └──────────────────┘      └──────────────────────┘                │
└─────────────────────────────────────────────────────────────────────┘
```

## 3. 模块划分

| 模块 | 职责 | 依赖 |
|------|------|------|
| `src/brain.py` | 大脑 agent loop，deepagents 编译图 | LangChain, deepagents |
| `src/spine/ascending.py` | 上行脊髓，身份识别 + 数据预取 | auth.py, vector_rag.py |
| `src/spine/descending.py` | 下行脊髓，任务翻译 + 路由 | dispatcher.py |
| `src/spine/dispatcher.py` | 分派器，解析 dispatch_actions JSON | auth.py, task_bs, task_st |
| `src/ganglion/reflex.py` | 中枢神经节，16个反射弧模式 | - |
| `src/security/auth.py` | 认证 + RBAC + Token 管理 | SQLite |
| `src/api/server.py` | FastAPI 服务端，40+ 端点 | 所有业务模块 |
| `staff/terminal.py` | CLI 员工终端 | brain.py, marathon/ |
| `staff/marathon/` | Marathon 多步骤执行引擎 | brain.py, deepagents |
| `src/tools/vector_rag.py` | 向量 RAG（bge-m3 1024维） | databases/, RAG_files/ |
| `src/tools/data_sources.py` | DataSecretary，花名册/SAP/考勤 | Excel, SQLite |
| `src/scheduler/scheduler.py` | 定时任务调度（7个任务） | 所有数据模块 |
| `src/insight_agent/` | 洞察子代理 | scheduler.py, dispatcher.py |

## 4. 数据流

### 4.1 智能问答流程

```
用户输入 → 身份识别 → 渠道分流 → 情报包组装 → 大脑 agent loop
                                                        ↓
                                              工具调用（搜索/执行）
                                                        ↓
                                              结果格式化 → dispatch_actions
                                                        ↓
                                              分派器执行 → 回复用户
```

### 4.2 Marathon 执行流程

```
复杂任务 → Planner 拆解 → [Executor × N] → Validator → Committer
                                    ↓
                              RubricMiddleware 评分
                                    ↓
                              (未通过) → 重试（最多3次）
```

### 4.3 洞察生成流程

```
05:00 定时触发 → 数据更新（花名册+加班）
                        ↓
              (双数据源都成功)
                        ↓
              InsightDataProvider 聚合
                        ↓
              洞察子代理分析 → dispatch_actions
                        ↓
              通知路由 → 精准推送
```

## 5. 关键技术选型

| 选择 | 方案 | 理由 |
|------|------|------|
| **Agent 框架** | deepagents | 官方支持 Profile/Middleware/Skill 体系 |
| **LLM 编排** | LangChain + LangGraph | 标准化 agent loop + 状态图 |
| **大模型** | [大模型名称] | 本地部署，支持工具调用 |
| **Web 框架** | FastAPI | 高性能异步，自动 OpenAPI 文档 |
| **向量模型** | bge-m3 1024维 | 多语言支持，中文效果好 |
| **数据库** | SQLite | 轻量级，无需额外运维，适合当前规模 |
| **认证** | OAuth2 + JWT | 标准协议，支持 Token 刷新 |
| **CLI 框架** | 自定义终端 | 基于 input()/print()，简化依赖 |

## 6. 接口契约

> 详细接口定义见 `design/contracts/` 目录。

| 接口 | 文件 | 说明 |
|------|------|------|
| REST API | contracts/api-contract.md | FastAPI 40+ 端点定义 |
| dispatch_actions | contracts/dispatch-schema.md | 大脑输出 JSON Schema |
| 洞察通知 | contracts/insight-schema.md | 洞察通知 JSON Schema |

## 7. 非功能需求

- **性能**：单次问答 ≤ 5s，Marathon 复杂任务 ≤ 60s
- **安全**：OAuth2 认证 + RBAC 权限，敏感字段过滤，SQL 参数化查询
- **可扩展性**：新增数据源只需放入 `databases/` 目录，Skill 只需添加 `SKILL.md`
- **可观测性**：结构化日志 + Dashboard KPI + 定时心跳巡检
- **可靠性**：定时任务失败自动创建 HRIS 工单，RubricMiddleware 自校正

## 8. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| deepagents Internal API 可能变化 | Middleware/Profile 适配层失效 | 封装在 `staff/marathon/` 内部，业务代码不直接导入 `_HarnessProfile` |
| Windows + 子进程编码问题 | execute_skill 子进程输出乱码 | `PYTHONIOENCODING=utf-8` + stderr 重定向 |
| LLM 工具调用格式不正确 | 大脑无法调用搜索工具 | `staff/llm.py` ToolCallFixChatOpenAI 修复层 |
| SQLite 并发写入竞争 | 多定时任务同时写入损坏数据库 | 串行化写入 + 连接池 |
| RubricMiddleware 重试导致重复执行 | 发邮件/预约会议室重复 | execute_skill 幂等性缓存（exec_id + task_hash） |

## 9. 变更日志

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-07-02 | 初始版本，基于 memory/architecture.md v3.1 | Thomas |