# New Feature Workflow（推荐模板）

> 此为通用建议流程，根据项目实际情况调整。**不要机械执行**——核心是确保变更可追溯、可审查。

### 何时使用 / 何时跳过

| 场景 | 使用 |
|------|------|
| 新功能、API 变更、多模块改动 | 本 workflow |
| 修 bug、小改动 | `bugfix-workflow.md` |

### Phase 1: Requirements & Design（无代码）

1. 确认或更新 `specs/PRD.md` 和 `specs/acceptance-criteria.md`。
2. 若涉及架构变更，更新 `design/HLD.md`（若项目有 design 目录）。
3. 若涉及 API 变更，更新 `design/contracts/`（若存在）。
4. 与 Tech Lead 对齐后方可进入实现。

### Phase 2: Task Breakdown

1. 将功能拆分为原子任务（建议 < 200 行代码/任务）。
2. 每个任务关联对应的 acceptance criteria。
3. 重大决策写入 `memory/decisions.md`。

### Phase 3: Implementation（迭代）

1. 一次处理一个任务。
2. 应用 `.clinerules/00-core.md` 质量基线；需要时激活 `robust-design` / `semantic-extraction` skill。
3. 代码 + 测试同步编写。
4. 每完成一个任务，执行 `verify-changes.md`。

### Phase 4: 对抗性评审（Adversarial Review）

> 在最终审查前，启动子 Agent 做独立只读审查。主 Agent 对自己写的代码有"确认偏误"，很难客观发现自身问题。

**触发条件**：完成 Phase 3 所有任务后，用户说"启动评审"或工作流自动提示。

**执行步骤**：

1. **启动子 Agent**：在 Cline 对话中使用 `use_subagents` 机制，派发以下指令：

   ```
   Use subagents to conduct an adversarial code review. Each subagent should:
   - Read the recently modified files
   - Check against 00-core.md security red lines (§2)
   - Check for anti-patterns (hardcoding, silent exceptions, missing edge cases)
   - Check test coverage (Happy Path + boundary + error paths)
   - Report findings with file paths and line numbers
   ```

2. **子 Agent 能力边界**：
   - ✅ 可以做：read_file、list_files、search_files、list_code_definition_names、只读 execute_command
   - ❌ 不能做：写文件、browser_action、MCP 工具

3. **收集评审报告**：子 Agent 交报告后，主 Agent 根据报告修复所有 HIGH/CRITICAL 级别问题

4. **确认修复**：修复完成后，执行 `verify-changes.md` 确认问题已解决

### Phase 5: Final Review

1. 确认变更范围与初始计划一致。
2. 对照 `00-core.md` §5 自检清单逐项确认（含 §5.1 反模式检查）。
3. 执行 `verify-changes.md` 全项目验证。

#### 可选：PR 代码审查

提交 PR 后，如需审查，执行以下步骤：

1. 使用 `gh pr diff` 获取当前 PR 的变更内容
2. 使用 `read_file` 读取被修改文件的完整内容，理解上下文
3. 分析代码变更，重点检查：
   - 是否符合 `00-core.md`（安全 §2、泛化 §3、架构 §4、自检 §5）
   - 是否有潜在的逻辑错误或性能问题
   - 是否包含必要测试（Happy Path + 边界 + 错误路径）
4. 执行 `verify-changes.md`（或确认 CI 已通过）
5. 将审查意见总结成列表，询问 Tech Lead 反馈
6. 根据指令，使用 `gh pr review` 提交审查结果（批准或请求修改）

**注意**：不需要等待「签约」才能继续下一个任务。收工时走 `session-end.md` 更新 Memory。
