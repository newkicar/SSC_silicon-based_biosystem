# Bugfix Workflow（小改动 / 修 bug）

> 修 bug、改文案、小 refactor 时使用。**跳过** new-feature 的 PRD/HLD 阶段，但仍走验证闭环。

---

## 适用场景

- 修复已知 bug
- 单文件或小范围改动（通常 < 100 行）
- 不涉及 API 契约或架构变更

## 流程

1. **定位**：读相关代码 + 错误信息，用 1–2 句话说明根因假设。
2. **修复**：最小改动原则——只改与 bug 相关的代码，不顺手重构无关部分。
3. **测试**：为 bug 补充回归测试（若项目有 tests/）；至少手动验证复现步骤已消失。
4. **对抗性评审**（可选）：对于复杂 bug 或多次修复未成功的场景，启动子 Agent 做独立审查（见 `new-feature-workflow.md` Phase 4）。
5. **验证**：执行 `.clinerules/workflows/verify-changes.md`。
6. **自检**：对照 `00-core.md` §5 交付清单（可简化，但安全与泛化项不可跳过，含 §5.1 反模式检查）。

## 不适用

- 新功能 → 用 `new-feature-workflow.md`
- 涉及 API 变更、数据库迁移、多模块重构 → 用 `new-feature-workflow.md` Phase 1
