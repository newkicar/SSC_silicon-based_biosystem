# Verify Changes（验证闭环）

> **每次收工、提交 PR、或完成一个任务后必须执行。** 这是 Harness 将「工程标准」落地的关键步骤。

---

## 1. 检测项目类型

按项目根目录存在的文件选择验证命令（可组合）：

| 信号 | 验证命令 |
|------|----------|
| `pyproject.toml` / `requirements.txt` + `tests/` | `pytest` 或 `python -m pytest` |
| 同上，无 tests 目录 | `ruff check .` 或 `python -m compileall .` |
| 存在 `.clinerules/03-pytorch-code-rule.md`（L2 已启用）或项目含 `import torch` | 除 pytest 外，确认 smoke test 存在且通过；完整训练前见 `dl-experiment-workflow.md` Phase 2 |
| `package.json` | `npm test`（若有 test script） |
| `package.json` + TypeScript | `npx tsc --noEmit`（若配置了） |
| `package.json` | `npx eslint .`（若配置了） |

**原则**：优先跑项目已有的 test/lint 命令，不要臆造不存在的脚本。

---

## 2. 执行验证

1. 在项目根目录运行上述命令。
2. **全部通过** → 继续自检清单（`00-core.md` §5）。
3. **有失败** →
   - 若能在当前 Session 修复：修复后重新验证。
   - 若无法修复（环境、第三方、需人工决策）：写入 `memory/blockers.md`，并在回复中说明。

---

## 3. 报告格式

验证完成后用以下格式汇报：

```
验证结果
- pytest: ✅ 12 passed / ❌ 2 failed
- ruff check: ✅
- 未运行: tsc（项目无 tsconfig）

结论: 可收工 / 需修复后再收工
```

---

## 4. 与 Hooks 的关系

- **PostToolUse**：每次写文件后自动 format/lint **单个文件**（快、局部）。
- **本 Workflow**：Session 级 **全项目验证**（慢、完整）。两者互补，不可替代。

---

## 5. 反向验证（Reverse Verification）

> 新增：不仅检查"有没有做"，还要检查"有没有做错"。这是主 Agent 的自我审查步骤。

执行完上述验证后，主 Agent 执行以下反向检查：

1. **对照 PRD 检查**：PRD 说支持 X，实际代码是否真的支持 X？
2. **对照验收标准检查**：acceptance-criteria.md 列了 N 条，是否每条都有对应代码和测试？
3. **边界情况检查**：PRD 没说但应该处理的情况（空输入、超大输入、异常值）是否处理了？
4. **反模式检查**：对照 `00-core.md` §5.1 反模式清单，排查"假测试"、"假文档"、"假覆盖"等问题。

---

## 6. CI 反馈闭环

> 增强：验证闭环不仅检查本地代码，还检查 CI 状态，形成完整反馈环。

### 6.1 CI 状态检测

验证完成后，检查 CI 平台状态：

| CI 平台 | 检测命令 |
|---------|---------|
| GitHub Actions | `gh run list --limit 1` |
| GitLab CI | `curl .../pipelines` |
| Jenkins | `curl .../api/json` |
| 无 CI 平台 | 跳过此步骤 |

### 6.2 CI 失败处理

如果检测到 CI 失败：

1. **自动触发** `ci-feedback-workflow.md` 处理失败
2. **记录到** `memory/blockers.md`
3. **向用户报告** CI 失败情况及修复建议

### 6.3 报告格式（含 CI）

```
验证结果
- pytest: ✅ 12 passed
- ruff check: ✅
- CI (GitHub Actions): ✅ 最新 run 通过

结论: 可收工 / 需修复后再收工 / CI 失败待处理
```
