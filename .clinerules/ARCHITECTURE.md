# Harness 体系架构

> 本文件定义整个 Harness 的分层结构和文件组织。Agent 应据此判断何时加载哪些规则。

---

## 语言策略

| 文件类型 | 语言 | 说明 |
|---------|------|------|
| `.clinerules/*.md` | 中文 | 规则文档面向中文用户，保持一致性 |
| `workflows/*.md` | 中文 | 工作流说明 |
| `hooks/*.ps1` 注释 | 英文 | PowerShell 社区惯例，保持与 PowerShell 生态一致 |
| `hooks/*.ps1` 消息 | 中文 | 用户可见的错误消息用中文 |
| `specs/*.md` | 中文 | 业务文档 |
| `memory/*.md` | 中文 | 业务文档 |
| `design/*.md` | 中文 | 业务文档 |

---

## 分层总览

```
Harness 体系
│
├── L1 — 核心规则（always loaded）
│   ├── 00-core.md              安全红线 / 代码质量底线 / 架构原则 / 交付清单
│   ├── 01-ponytail.md          开发哲学（lazy senior dev）
│   ├── CONTRIBUTING-RULES.md   如何添加新规则
│   └── hooks/                  Pre/Post ToolUse PowerShell 钩子
│       ├── PreToolUse.ps1      写文件前拦截（安全门禁）
│       ├── PostToolUse.ps1     写文件后审计（泄漏检测）
│       └── session-end.md      收工自动化流程
│
├── L2 — 领域特化规则（按需启用，默认在 l2/ 子目录，settings exclude）
│   ├── l2/02-deepagents-code-rule.md   ← Agent 项目
│   └── l2/03-pytorch-code-rule.md      ← 深度学习项目
│
├── L3 — 工作流（按任务类型选择）
│   │
│   ├── ★ 核心工作流（★ = 必装，覆盖 90% 日常场景）
│   │   ├── new-feature-workflow.md   ★ 新功能 / API 变更 / 多模块
│   │   ├── bugfix-workflow.md        ★ 修 bug / 小改动 / 单文件
│   │   ├── dl-experiment-workflow.md ★ PyTorch 实验（需 L2 03-pytorch 配合）
│   │   └── verify-changes.md         ★ L3 共享的验证步骤（所有 workflow 调用）
│   │
│   ├── ○ 扩展工作流（○ = 已默认部署，无需 -Extras）
│   │   ├── baseline-startup.md       ○ 项目跑不起来
│   │   ├── error-rescue.md           ○ 反复报错修不好
│   │   ├── drift-scan-workflow.md    ○ 代码/文档/依赖漂移检测
│   │   ├── ci-feedback-workflow.md   ○ CI 失败自动修复
│   │   ├── task-risk-gates.md        ○ 任务风险分级
│   │   ├── context-handoff.md        ○ 上下文交接格式
│   │   ├── ai-debt-audit.md          ○ AI 债务体检
│   │   ├── user-acceptance-walkthrough.md  ○ 用户验收陪跑
│   │   └── natural-language-routing.md   ○ 自然语言路由索引
│   │
│   └── ★ Speckit 子体系（可选激活，见下方）
│       └── speckit/                  ← 10 个 speckit workflow 移入此目录
│
│   └── INDEX.md                      ← 工作流选择索引（项目类型 + 任务类型决策树）
│
└── L4 — 模板
    ├── specs/
    │   ├── PRD.md                        产品需求文档模板
    │   └── acceptance-criteria.md        验收标准模板
    ├── design/
    │   ├── HLD.md                        高层设计文档（可选，大功能时使用）
    │   └── contracts/                    API 契约（可选，涉及外部接口时使用）
    └── memory/
        ├── progress.md                   进度记录
        ├── blockers.md                   阻塞记录
        └── decisions.md                  架构决策记录 (ADR)
```

---

## 工作流分级说明

### 核心工作流（★ 必装）

覆盖 90% 的日常开发场景。`deploy.ps1` 默认复制这些文件。

| 工作流 | 适用场景 | 何时触发 |
|--------|---------|---------|
| `new-feature-workflow` | 新功能、API 变更、多模块改动 | "我想做个新功能" |
| `bugfix-workflow` | 修 bug、改文案、小 refactor | "修这个 bug" |
| `dl-experiment-workflow` | PyTorch 实验 | "跑个新模型" |
| `verify-changes` | 验证闭环（所有 workflow 共享） | 每次收工/提交前 |

### 扩展工作流（○ 已默认部署）

默认部署全部 13 个工作流（含 9 个扩展工作流）。AI 会根据你的自然语言描述自动选择最合适的工作流，无需人工判断哪个是"核心"或"扩展"。

| 工作流 | 适用场景 | 触发条件 |
|--------|---------|---------|
| `baseline-startup` | 项目跑不起来 | "项目跑不起来" |
| `error-rescue` | 反复修不好 | "一直修不好，报同样的错" |
| `drift-scan` | 代码/文档/依赖漂移 | session-end Phase 4 自动触发 |
| `ci-feedback` | CI 失败自动修复 | verify-changes 检测到 CI 失败 |
| `task-risk-gates` | 任务风险分级 | 大功能开工前 |
| `context-handoff` | 上下文交接 | "上下文太长，换窗口继续" |
| `ai-debt-audit` | AI 债务体检 | "项目越来越乱了" |
| `user-acceptance` | 用户验收陪跑 | 功能完成后 |
| `natural-language-routing` | 自然语言路由索引 | 辅助决策 |

> **注意**：`-Extras` 参数已废弃，扩展工作流已默认包含在 `.clinerules/workflows/` 部署中。

### 分级管理

```
deploy.ps1（默认）  → 复制全部 13 个工作流
deploy.ps1 -L2 deepagents  → 同时启用 L2 领域规则
```

### 引用关系（双向，非单向链）

```
L1 (核心规则)
  │
  ├── 被 L2 引用：安全 §2、泛化 §3.2、正则 §3.3
  ├── 被 L3 引用：交付清单 §5
  └── 被 hooks/ 执行：PreToolUse/PostToolUse 将 L1 规则机械化为可执行检查

L2 (领域规则) — 通过 deploy.ps1 -L2 或手动复制 l2/ 文件到 .clinerules/ 根目录后激活
  │
  ├── 引用 L1（安全红线、泛化原则、正则禁用）
  └── 被 L3 中的特定 workflow 引用（如 dl-experiment 引用 03-pytorch）

L3 (工作流) — 按任务类型选择
  │
  ├── 引用 L1 + L2（视项目类型）
  ├── 内部互引：session-end.md → verify-changes.md → L4 memory/
  └── Speckit 子体系：引用 L4 specs/ 模板，非完全独立

L4 (模板) — 被 workflow 读写
     │
     ├── specs/ 在 new-feature Phase 1 写入
     ├── design/ 在 new-feature Phase 1 写入（大功能时）
     └── memory/ 在 session-end Phase 3 追加
```

> **关键变化**：Speckit 不再标为「独立 L3 分支」，改为「可选激活的 L3 子体系」，因为它引用 L4 模板。

---

## Speckit 子体系（可选激活的 L3 子体系）

```
L3 — Speckit 子体系
│
└── speckit/                          ← 所有 speckit-* 文件移入此目录
    ├── speckit-specify.md            创建/更新 feature spec
    ├── speckit-clarify.md            澄清需求
    ├── speckit-plan.md               生成实施计划
    ├── speckit-tasks.md              拆解任务
    ├── speckit-implement.md          执行实现
    ├── speckit-checklist.md          生成交付清单
    ├── speckit-converge.md           收敛完成
    ├── speckit-analyze.md            分析变更
    ├── speckit-agent-context-update.md
    ├── speckit-taskstoissues.md
    └── speckit-constitution.md       创建项目宪法

（共 10 个文件）

激活条件（二选一）：
  A. 项目根目录存在 .specify/extensions.yml
  B. 用户明确说「用 speckit 流程」

切换方式：
  - 主工作流 → 说「用标准流程」或直接描述任务
  - Speckit → 说「speckit specify」/「speckit plan」等
```

---

## 文件命名约定

| 前缀 | 含义 | 示例 |
|------|------|------|
| `00-` | 核心规则（永远加载） | `00-core.md` |
| `01-` | 开发哲学 | `01-ponytail.md` |
| `02-` | Agent 项目特化 | `02-deepagents-code-rule.md` |
| `03-` | 深度学习项目特化 | `03-pytorch-code-rule.md` |
| `speckit-*` | Speckit 工作流步骤 | `speckit-plan.md` |
| `*-workflow` | 通用工作流 | `new-feature-workflow.md` |
| `verify-*` / `*-changes` | 验证步骤 | `verify-changes.md` |
