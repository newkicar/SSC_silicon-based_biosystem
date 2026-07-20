# Drift Scan Workflow

> **用途**：检测代码与文档/架构/依赖之间的「漂移」（Drift），防止代码仓库在长期迭代中积累不一致。
>
> **激活时机**（二选一）：
> 1. 用户明确说「跑 drift scan」
> 2. session-end Phase 4（文档除草）检测到过期文档，自动触发补充扫描

---

## 三个维度

### 1. 依赖漂移（Dependency Drift）

检查 `requirements.txt` / `pyproject.toml` / `package.json` 中的依赖版本与当前语义约束是否匹配。

| 检查项 | 检出条件 | 操作 |
|--------|---------|------|
| 已知漏洞 | `pip-audit` / `npm audit` 发现 `CRITICAL`/`HIGH` 级漏洞 | 记录到 `blockers.md` |
| 已安装未声明 | 代码 `import` / `require` 了不在 manifest 中的包 | 追加到 `requirements.txt` |
| 已声明未使用 | manifest 中的包未被代码使用 | 标记为 candidates for removal |
| 版本锁定漂移 | `requirements.txt` 用 `>=` 但下游 break | 考虑锁版本 |

### 2. 架构漂移（Architecture Drift）

检查代码结构是否偏离 `ARCHITECTURE.md` / `design/HLD.md` / `design/contracts/` 中定义的约定。

| 检查项 | 检出条件 | 操作 |
|--------|---------|------|
| 分层越界 | 表现层直接调 DAL / 模型层写文件 | 记录违规位置到 `blockers.md` |
| 接口失配 | API contract 中声明的 endpoint 在代码中不存在 | 更新 contract 或补充 endpoint |
| 模块消失 | HLD 中标记的模块在项目结构中已删除 | 更新 HLD 或记录决策 |
| 规则覆盖漂移 | 新增文件类型但 hooks 未覆盖（如 `.rs`、`.go`） | 考虑向 hooks 追加新规则 |

### 3. 技术债务漂移（Tech Debt Drift）

> **增强**：使用 `codebase-memory-mcp` 替代 grep，提速 100 倍。

检查代码中积累的临时/折衷实现是否已超出预定生命周期。

| 检查项 | 检出条件 | 操作 |
|--------|---------|------|
| `ponytail:` 标记 | `search_graph(query="ponytail:")` 毫秒级定位 | 评估是否已达 ceiling，需要升级 |
| `# TODO` 年龄 | `search_graph(query="# TODO")` + git blame | 记录到 `progress.md` 的 Next |
| Legacy 文件名 | `query_graph("MATCH (f) WHERE f.name CONTAINS 'old'")` | 评估能否删除或重命名 |
| 测试覆盖缺口 | `search_graph(query="test")` 对比代码模块 | 提出添加测试建议 |

---

## 执行流程

> **增强**：使用 `codebase-memory-mcp` 替代 grep，提速 100 倍。

```
Phase 0: 用户触发 / session-end 补充触发
    │
    ▼
Phase 1: 依赖扫描（codebase-memory 加速）
    ├── search_graph(query="import pip-audit") → 快速定位依赖
    ├── pip-audit / npm audit（如可用）
    ├── grep import 交叉 manifest（备选）
    └── 记录结果
    │
    ▼
Phase 2: 架构扫描
    ├── get_architecture() → 一次返回完整架构图
    ├── 读取 design/HLD.md / ARCHITECTURE.md
    ├── search_graph(query="分层越界") → 精准定位违规
    └── 记录偏差
    │
    ▼
Phase 3: 技术债务扫描（codebase-memory 加速）
    ├── search_graph(query="ponytail:") → 毫秒级定位 ponytail 标记
    ├── search_graph(query="# TODO") → 快速定位 TODO
    ├── query_graph("MATCH (f:Function) WHERE f.name CONTAINS 'old'") → 查找 legacy 代码
    └── 记录结果
    │
    ▼
Phase 4: 输出报告
    ├── 无漂移 → 一句话确认
    ├── 轻微漂移 → 追加到 progress.md Next
    └── 严重漂移 → 追加到 blockers.md + 向用户报告
```

---

## 输出格式

### 无漂移
```
Drift Scan: ✅ 三个维度均未检测到漂移。
```

### 有漂移
```
Drift Scan: ⚠️ 发现以下漂移

**依赖漂移**：
- [包名]：[具体问题]

**架构漂移**：
- [模块/文件]：[具体问题]

**技术债务**：
- [文件/标记]：[具体问题]

以上已追加到 memory/progress.md 的 Next 节。
严重项已追加到 memory/blockers.md。
```

---

## 与 session-end 的关系

- Phase 4（文档除草）仅扫描 `specs/` + `design/` + `memory/decisions.md` 文件本身是否过期
- Drift Scan（本 workflow）扫描**代码与文档的实际偏差**
- 两者互补：文档除草 → 发现过期 → 触发 Drift Scan → 量化偏差

### 触发规则

在 session-end Phase 4b 末尾，如果发现过期文档，则执行本 workflow。

```python pseudocode
# session_count = memory/progress.md 中 "## Session —" 条目数量
if doc_gardening_found_expired_docs:
    if session_count % 10 == 0:
        drift_scan(scope="full")  # 全量扫描
    else:
        drift_scan(scope="affected_modules_only")  # 仅受影响模块
