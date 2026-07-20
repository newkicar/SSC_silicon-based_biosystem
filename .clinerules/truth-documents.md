# 真源文档体系（Truth Documents）

> 借鉴 Sliver Vibe Coding 的真源文档思想，确保项目决策可追溯、可验证。

---

## 核心原则

**真源文档 = 项目的单一事实来源**

- 聊天决策不是正式真源，直到写入相关真源文档
- 用户中途变更需求 → 先更新真源文档，再写代码
- 真源文档是项目方向的锚，不是会议纪要

---

## 最小真源集（5 份核心文档）

| 文档 | 用途 | 何时创建 |
|------|------|---------|
| `specs/PRD.md` | 产品需求：做什么、给谁用 | 项目初始化 |
| `specs/acceptance-criteria.md` | 验收标准（Given-When-Then） | 每功能 |
| `memory/progress.md` | 进度 + 阻塞 + 下次待办 | 每次 Session |
| `memory/decisions.md` | 架构决策（ADR 格式） | 每次决策 |
| `memory/architecture.md` | 当前架构快照 | 架构变更时 |

---

## 可选文档（按需创建）

> 不要预先创建这些文件。当实际需求出现时，从下方模板清单中复制对应模板到项目目录。

| 文档 | 触发条件 | 模板位置 |
|------|---------|---------|
| `design/HLD.md` | 多模块 / 多服务 | `design/HLD.md` |
| `design/contracts/*.md` | 涉及外部 API | `design/contracts/` |
| `dev-docs/security-boundary.md` | 有安全合规要求 | 见下方模板 |
| `dev-docs/deployment-route.md` | 准备上线 | 见下方模板 |
| `dev-docs/quality-evidence.md` | 阶段完成后 | 见下方模板 |

### 可选文档模板

```markdown
<!-- 复制到 dev-docs/security-boundary.md 时使用 -->
# 安全边界报告

## 信任边界
| 边界 | 左侧信任级 | 右侧信任级 | 校验点 |
|------|-----------|-----------|--------|

## 数据分类
| 数据类型 | 敏感级 | 存储方式 | 传输加密 |
|---------|--------|---------|---------|

## 认证与授权
- 认证方式：
- 授权模型：
- Token 有效期：
```

```markdown
<!-- 复制到 dev-docs/deployment-route.md 时使用 -->
# 部署路线

## 目标环境
- 环境：
- 部署方式：

## 部署步骤
1.
2.

## 回滚计划
- 回滚命令：
- 数据迁移反向操作：
```

```markdown
<!-- 复制到 dev-docs/quality-evidence.md 时使用 -->
# 质量和测试证据

## 测试结果
- 测试框架：
- 覆盖率：
- 通过命令：

## 性能基准
- 响应时间：
- 吞吐量：
```

---

## 真源文档管理

### 创建真源文档时

- 使用 `specs/PRD.md` 和 `specs/acceptance-criteria.md` 作为需求层模板
- 使用 `memory/decisions.md`（ADR 格式）记录架构决策
- **不要**直接复制模板而不适配项目证据

### 真源文档审计

在 session-end Phase 4（文档除草）中，检查核心真源是否有效：

- [ ] `specs/PRD.md` 有实质性内容（非空标题）
- [ ] `specs/acceptance-criteria.md` 有 Given-When-Then 条目
- [ ] `memory/progress.md` 有最近的 Session 记录
- [ ] `memory/decisions.md` 有记录的 ADR
- [ ] `memory/architecture.md` 与当前代码一致（如有）

> 只做结构和明显漂移检查，不替代真实启动、测试、UI、API、数据库、安全或用户验收。

---

## 真源文档与开发流程的关系

```
立项 → PRD → 验收标准 → 进度记录 → 决策记录 → 实施 → 验收 → 发布
  ↓      ↓        ↓          ↓          ↓         ↓       ↓       ↓
project  accept   progress   decisions  arch     quality release
 PRD     criteria progress   decisions  arch     evidence  route
```

**核心 5 份文档必须持续维护，可选文档按需创建。**

---

## 真源文档 vs 聊天决策

| 类型 | 是否正式真源 | 说明 |
|------|-------------|------|
| 聊天中的决策 | ❌ 不是 | 直到写入真源文档 |
| 写入真源文档的决策 | ✅ 是 | 项目的单一事实来源 |
| 用户口头变更需求 | ❌ 不是 | 先更新真源文档，再改代码 |

---

## Harness 内置模板

Harness 内置的模板位置：

- `specs/PRD.md` — 产品需求文档模板
- `specs/acceptance-criteria.md` — 验收标准模板（Given-When-Then 格式）
- `memory/decisions.md` — 架构决策记录模板（ADR 格式）
- `memory/progress.md` — 进度记录模板（Session 格式）
- `memory/blockers.md` — 阻塞记录模板
- `memory/architecture.md` — 架构快照模板

使用时必须结合：

- 用户项目实际内容
- 文件路径和命令
- Owner 和验证证据

**不要原样复制成项目真源。**
