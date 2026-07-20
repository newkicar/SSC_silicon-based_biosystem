# Session End 自动化流程

> 顺序：**先验证 → 再更新 Memory → 再确认**。

---

## Phase 0: 触发判断

在以下**任一**条件下执行 session-end：

1. **用户明确信号**：用户说「收工」「done」「finish」「结束」
2. **任务完成**：当前任务的所有步骤已完成，且 `verify-changes` 通过
3. **陷入循环**：连续 3 次工具调用返回相同错误（agent 无法自行突破）
4. **遇到 blocker**：检测到阻塞且无法自行解决

如果以上条件均不满足，**跳过 session-end**，继续工作。

---

## Phase 1: 验证闭环（必做）

> 权威参考：`.clinerules/workflows/verify-changes.md`

1. 执行 `verify-changes.md` 中的验证步骤（含 CI 反馈）。
2. **检查 CI 状态**：如果项目有 CI 平台（GitHub Actions / GitLab CI / Jenkins），检查最近一次 run 状态。
   - CI 通过 → 继续
   - CI 失败 → 自动触发 `ci-feedback-workflow.md` 处理
3. **（可选）detect_changes 影响分析**：如果有未提交的改动，运行 `detect_changes` 识别影响范围，辅助修复。
4. 验证失败且无法在本 Session 修复时，将详情写入 `memory/blockers.md`。
5. 向用户汇报验证结果（通过 / 失败项 / 未运行的检查 / CI 状态）。

---

## Phase 2: 读取 Memory 状态

- 读取 `memory/progress.md` 获取历史上下文。
- 读取 `memory/blockers.md` 确认已知阻塞。
- 读取 `memory/decisions.md` 确认历史决策。

---

## Phase 3: 写入 Memory

### progress.md（完整写回模式）

> ⚠️ 根据 `MEM-BANK-002` 规则，Memory Bank 文件禁止用 `replace_in_file` 修改。本步骤采用「读出现有内容 → 追加新 Session 记录 → 全量写回」模式。

1. 用 `read_file` 读取现有 `memory/progress.md`
2. 在文件末尾追加新的 Session 记录（格式见下方）
3. 用 `write_to_file` 全量写回整篇文件

新记录包含：

- Session 时间范围
- 本次完成的主要事项
- 验证结果摘要（test/lint 通过情况）
- 下次待办（从 blockers / 未完成项推断）

### decisions.md（完整写回模式）

> ⚠️ 同样禁止用 `replace_in_file`。

1. 用 `read_file` 读取现有 `memory/decisions.md`
2. 在末尾追加新 ADR 条目
3. 用 `write_to_file` 全量写回

内容：背景 + 选择 + 原因。

### blockers.md（完整写回模式）

> ⚠️ 同样禁止用 `replace_in_file`。

1. 用 `read_file` 读取现有 `memory/blockers.md`
2. 在末尾追加新阻塞项
3. 用 `write_to_file` 全量写回

内容：描述 + 影响 + 缓解措施。

---

## Phase 4: 文档健康度（Doc Health）

> OpenAI 启发：智能体生成的代码会复刻已有模式，包括过期的文档。定期清理是防止知识腐烂的关键。

### 4a. 核心真源检查（必做）

检查 5 份核心真源文档是否有效（非占位符）：

- [ ] `specs/PRD.md` 有实质性内容（非空标题）
- [ ] `specs/acceptance-criteria.md` 有 Given-When-Then 条目
- [ ] `memory/progress.md` 有最近的 Session 记录
- [ ] `memory/decisions.md` 有记录的 ADR
- [ ] `memory/architecture.md` 与当前代码一致（如有）

> 只做结构和明显漂移检查，不替代真实启动、测试、UI、API、数据库、安全或用户验收。

### 4b. 可选文档审计（按需）

检查本次 Session 是否有新的文档应该创建：

1. 本次涉及多模块架构变更 → 检查 `design/HLD.md` 是否需要更新
2. 本次涉及 API 变更 → 检查 `design/contracts/` 是否需要更新
3. 本次有安全/合规决策 → 检查是否需要创建 `dev-docs/security-boundary.md`
4. 本次准备上线 → 检查是否需要创建 `dev-docs/deployment-route.md`

### 4c. Drift Scan（条件触发）

> 如果 4a 发现过期文档，说明代码与文档之间可能已出现漂移（Drift），需要进一步量化偏差。

1. 如果 4a 中发现核心文档与代码不一致，执行 `.clinerules/workflows/drift-scan-workflow.md`：
   - scope = affected_modules_only（仅扫描受影响模块，非全量）
   - **session_count 计算**：`session_count = memory/progress.md` 中 `## Session —` 条目的数量。若 `session_count % 10 == 0`，执行全量扫描（scope = full）。

### 4d. 记录结果

1. 过期文档和漂移扫描结果统一记录到 `progress.md` 的 Next 节
2. 严重偏差（分层越界、已知漏洞等）追加到 `blockers.md`

---

## Phase 5: 自检确认

对照 `.clinerules/00-core.md` §5 交付清单，简要说明每项是否满足；未满足项记入 blockers 或 Next。

---

## Phase 6: 输出确认

对用户说：

> Memory Bank 已更新。
>
> - 验证：（pytest/npm test/… 结果）
> - CI 状态：（通过/失败/待处理）
> - progress.md：追加本次 Session 摘要
> - decisions.md：追加 X 条决策
> - blockers.md：追加 X 条阻塞

---

## progress.md 格式规范

```markdown
## Session — YYYY-MM-DD HH:MM ~ HH:MM

### Completed
- [事项1]

### Verification
- pytest: ✅ 12 passed
- ruff: ✅

### Next
- [下一步1]

### Decisions
- [决策1]：[原因]

### Blockers
- [阻塞1]：[描述 + 缓解措施]
```
