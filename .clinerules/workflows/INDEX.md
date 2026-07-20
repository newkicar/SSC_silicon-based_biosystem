# Workflow Index（工作流索引）

> 选择正确的工作流，避免 agent 在该用哪个流程时困惑。

---

## 第一步：判断项目类型（L2 领域规则）

> L2 存放在 `.clinerules/l2/`，**默认不加载**。通过 `deploy.ps1 -L2` 复制到 `.clinerules/` 根目录后生效。

| 项目特征 | 启用方式 |
|---------|---------|
| Agent / `create_deep_agent()` | `deploy.ps1 -L2 deepagents` → `02-deepagents-code-rule.md` |
| PyTorch / `import torch` | `deploy.ps1 -L2 pytorch` → `03-pytorch-code-rule.md` |
| 普通项目 | 不启用 L2 |

## 第二步：判断任务类型

### ★ 核心工作流（90% 场景用这些）

| 任务描述 | 使用工作流 |
|---------|-----------|
| 新功能 / API 变更 / 多模块改动 | `new-feature-workflow.md` |
| 修 bug / 改文案 / 小 refactor（< 100 行） | `bugfix-workflow.md` |
| PyTorch 实验（新数据集 / 新模型 / 新训练范式） | `dl-experiment-workflow.md` |

### ○ 扩展工作流（已默认部署，无需 -Extras）

| 任务描述 | 使用工作流 |
|---------|-----------|
| 项目跑不起来 | `baseline-startup.md` |
| 反复报错修不好 | `error-rescue.md` |
| 上下文太长换窗口 | `context-handoff.md` |
| 项目越来越乱 | `ai-debt-audit.md` |
| PR 审查 | 作为 `new-feature-workflow.md` Phase 4 的可选步骤 |

---

## Speckit 子体系

> 当激活条件满足时，使用 `speckit/` 目录下的 workflow 系列。

**激活条件（二选一）**：

1. 项目根目录存在 `.specify/extensions.yml`
2. 用户明确说「用 speckit 流程」

**Speckit 工作流序列**：

```
speckit-specify.md    → 创建/更新 feature spec
speckit-clarify.md    → 澄清需求（可选）
speckit-plan.md       → 生成实施计划
speckit-tasks.md      → 拆解任务
speckit-implement.md  → 执行实现
speckit-checklist.md  → 生成交付清单
speckit-converge.md   → 收敛完成
```

**与主工作流的关系**：

- Speckit 是**独立的完整流程**，有自己的 phase 系统和 memory 路径（`.specify/memory/`）
- 使用 Speckit 时**不**走 `new-feature-workflow.md`
- Speckit 的 `speckit-converge.md` 完成后，仍需走 `session-end.md` 更新主 `memory/`

---

## 通用步骤（所有 workflow 共享）

| 步骤 | 文件 | 说明 |
|------|------|------|
| 验证 | `verify-changes.md` | 所有 workflow 的 Phase 4 调用 |
| 收工 | `session-end.md` | 完成任务后更新 Memory |
| 自检 | `00-core.md` §5 | 交付清单逐项确认 |

---

## 决策流程图

```
收到任务
  │
  ├─ 用户说「用 speckit」或有 .specify/extensions.yml？
  │   └─ YES → 使用 speckit/ 系列 workflow
  │
  ├─ 项目含 create_deep_agent()？→ deploy -L2 deepagents
  ├─ 项目含 import torch？→ deploy -L2 pytorch
  │
  ├─ 项目跑不起来？→ baseline-startup
  ├─ 反复报错修不好？→ error-rescue
  ├─ 上下文太长换窗口？→ context-handoff
  ├─ 项目越来越乱？→ ai-debt-audit
  │
  ├─ 新功能 / API 变更 / 多模块？→ new-feature-workflow
  ├─ 修 bug / 小改动？→ bugfix-workflow
  └─ PyTorch 实验？→ dl-experiment-workflow
