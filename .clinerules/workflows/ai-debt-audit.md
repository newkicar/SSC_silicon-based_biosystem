# AI 债务体检（AI Debt Audit）

> 借鉴 Sliver Vibe Coding 的 AI 债务体检思想，审计 AI 生成的重复文件、假数据、自定义 wrapper、依赖蔓延。

---

## 体检维度

### 1. 重复文件

| 检查项 | 检出条件 | 操作 |
|--------|---------|------|
| 重复组件 | 同名或相似名的组件文件 | 标记为 candidates for merge |
| 重复工具函数 | 功能相似的 util/helper 文件 | 标记为 candidates for merge |
| 重复测试文件 | 同名或相似名的测试文件 | 标记为 candidates for merge |

### 2. 假数据 / Mock 数据

| 检查项 | 检出条件 | 操作 |
|--------|---------|------|
| Mock API 响应 | 代码中包含硬编码的假 JSON | 标记为 candidates for removal |
| Fake 用户数据 | `create_user()` 返回固定值 | 改为工厂函数或配置 |
| 假成功标志 | 代码中 `success = True` 硬编码 | 标记为风险点 |

### 3. 自定义 Wrapper

| 检查项 | 检出条件 | 操作 |
|--------|---------|------|
| 不必要的 wrapper | 对标准库/流行库的多余封装 | 标记为 candidates for removal |
| 重复实现 | 自己实现已有成熟方案的功能 | 标记为 candidates for replacement |

### 4. 依赖蔓延

| 检查项 | 检出条件 | 操作 |
|--------|---------|------|
| 未使用依赖 | manifest 中的包未被代码使用 | 标记为 candidates for removal |
| 过多依赖 | 项目依赖数量超过 20 个 | 建议审查每个依赖的必要性 |
| 过时依赖 | 依赖版本超过 2 年未更新 | 建议升级或寻找替代 |

### 5. 依赖文件

| 检查项 | 检出条件 | 操作 |
|--------|---------|------|
| 死文件 | 代码中引用但不存在的文件 | 标记为 dead reference |
| 孤立文件 | 存在但无代码引用的文件 | 标记为 candidates for removal |
| 循环引用 | A 导入 B，B 也导入 A | 标记为 architecture smell |

---

## 执行流程

```
Phase 0: 用户触发 / session-end 补充触发
    │
    ▼
Phase 1: 扫描重复文件
    ├── grep 同名/相似名文件
    └── 记录结果
    │
    ▼
Phase 2: 扫描假数据
    ├── grep "mock" / "fake" / "dummy"
    ├── grep 硬编码 JSON
    └── 记录结果
    │
    ▼
Phase 3: 扫描自定义 wrapper
    ├── grep "wrapper" / "helper" / "util"
    ├── 检查是否重复实现
    └── 记录结果
    │
    ▼
Phase 4: 扫描依赖蔓延
    ├── pip list / npm list
    ├── grep import / require
    └── 交叉比对
    │
    ▼
Phase 5: 输出报告
    ├── 无债务 → 一句话确认
    ├── 轻微债务 → 追加到 progress.md Next
    └── 严重债务 → 追加到 blockers.md + 向用户报告
```

---

## 输出格式

### 无债务
```
AI Debt Audit: ✅ 未检测到 AI 债务问题。
```

### 有债务
```
AI Debt Audit: ⚠️ 发现以下 AI 债务

**重复文件**：
- [文件路径]：[具体问题]

**假数据**：
- [文件路径]：[具体问题]

**自定义 wrapper**：
- [文件路径]：[具体问题]

**依赖蔓延**：
- [包名]：[具体问题]

以上已追加到 memory/progress.md 的 Next 节。
严重项已追加到 memory/blockers.md。
```

---

## 与 session-end 的关系

- session-end Phase 4（文档除草）定期触发 AI 债务体检
- 频率：每 10 个 session 一次全量扫描
- 触发条件：用户说「AI 债务体检」或「项目越来越乱了」

---

## 自动修复建议

| 债务类型 | 自动修复 | 人工审核 |
|---------|---------|---------|
| 重复文件 | 建议合并 | ✅ 需要 |
| 假数据 | 标记为 TODO | ✅ 需要 |
| 自定义 wrapper | 建议替换 | ✅ 需要 |
| 未使用依赖 | 建议移除 | ✅ 需要 |
| 死文件 | 建议删除 | ✅ 需要 |
| 循环引用 | 建议重构 | ✅ 需要 |

> **原则**：AI 债务体检发现的所有问题都需要人工审核，AI 不自动删除或合并文件。