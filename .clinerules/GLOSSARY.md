# Harness 术语表

> 统一关键术语的定义和使用场景，避免 agent 在不同文件中产生歧义。

---

## 核心概念

| 术语 | 定义 | 何时使用 |
|------|------|---------|
| **轻量验证** | 只跑受影响文件的 lint + 相关测试 | `bugfix-workflow` 场景 |
| **全量验证** | 跑完整 test suite + lint + 类型检查 | `new-feature-workflow` Phase 4、`session-end` |
| **验证闭环** | `verify-changes.md` 的执行 + 结果报告 | 所有 workflow 的必经步骤 |
| **Smoke Test** | 最小可行性测试（1 batch forward/backward、dummy input shape 检查） | DL 项目 Phase 2、新建 Dataset/Model 后 |
| **收工 (Session End)** | 完成一个独立任务单元后的清理和 Memory 更新动作 | 见 `session-end.md` Phase 0 触发条件 |
| **Hook 审计** | PostToolUse 每次写文件后自动扫描单个文件（快、局部） | 检测密钥泄漏、debugger 残留、Windows 路径硬编码 |
| **Workflow 验证** | verify-changes 执行全项目 test/lint（慢、完整） | Session 结束时执行，确保整体质量 |

## 文件层级

| 术语 | 对应文件 | 说明 |
|------|---------|------|
| **L1 核心规则** | `00-core.md`, `01-ponytail.md`, `hooks/*` | 永远加载，不选择性跳过 |
| **L2 领域规则** | `02-deepagents-code-rule.md`, `03-pytorch-code-rule.md` | 按项目特征选择性加载 |
| **L3 工作流** | `workflows/*.md`（不含 `speckit/`） | 按任务类型三选一 |
| **L3 Speckit** | `workflows/speckit/*.md` | 可选激活的子体系，引用 L4 specs/ 模板 |
| **L4 模板** | `specs/*.md`, `memory/*.md` | 被 workflow 读写的数据文件 |

## 工具命名

| 术语 | Cline 工具名 | 说明 |
|------|-------------|------|
| **全量写文件** | `write_to_file` | 覆盖整个文件内容，Memory Bank 唯一允许的写入方式 |
| **部分修改** | `replace_in_file` | 搜索替换文件中的特定段落，**禁止用于 Memory Bank** |
| **读取文件** | `read_file` | 读取文件完整内容，Memory Bank 更新前的必要步骤 |
| **PreToolUse** | PowerShell hook | 文件写入**前**执行的安全拦截 |
| **PostToolUse** | PowerShell hook | 文件写入**后**执行的审计扫描 |

## 规则动作

| 术语 | 含义 | 效果 |
|------|------|------|
| **BLOCK** | 阻止操作 | Cline 取消该工具调用，显示错误信息 |
| **WARN** | 警告但不阻止 | 在输出中显示警告，继续执行 |
| **ALERT** | 严重警告 | 类似 WARN，但用于安全相关项（密钥泄漏等） |

## 项目检测信号

| 信号文件/内容 | 检测到的项目类型 | 加载的 L2 规则 |
|--------------|-----------------|---------------|
| `create_deep_agent(` 或 `@github/copilot-sdk` | Agent 项目 | `02-deepagents-code-rule.md` |
| `import torch` 或 `pyproject.toml` + torch | PyTorch 项目 | `03-pytorch-code-rule.md` |
| `.specify/extensions.yml` | Speckit 项目 | 激活 `speckit/` 工作流系列 |
| 以上都没有 | 普通项目 | 不加载 L2 规则 |