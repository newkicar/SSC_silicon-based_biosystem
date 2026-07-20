# CI Feedback Workflow

> **用途**：处理 CI（持续集成）失败场景，自动分析失败原因并触发修复。
>
> **激活时机**：
> 1. 用户明确说「CI 失败了，帮我修复」
> 2. `verify-changes.md` 检测到 CI 失败
> 3. `session-end.md` Phase 1 发现 CI 状态异常

---

## 工作流程

> **增强**：使用 `codebase-memory-mcp` 精准定位失败代码。

```
Phase 0: 用户触发 / 自动触发
    │
    ▼
Phase 1: 读取 CI 日志
    ├── 确定 CI 平台（GitHub Actions / GitLab CI / Jenkins / Azure DevOps）
    ├── 获取失败作业的日志
    └── 记录到临时文件
    │
    ▼
Phase 2: 分析失败原因（codebase-memory 加速）
    ├── 测试失败 → trace_path(function=失败用例) → 定位调用链
    ├── 构建失败 → search_graph(query=编译错误) → 精准定位
    ├── lint 失败 → search_graph(query=代码风格问题) → 定位违规代码
    └── 其他失败 → 记录到 blockers.md
    │
    ▼
Phase 3: 自动修复（如可能）
    ├── 测试失败 → 修复测试代码或业务逻辑（基于 trace_path 结果）
    ├── 构建失败 → 修复语法/类型错误
    ├── lint 失败 → 自动格式化或手动修复
    └── 无法自动修复 → 记录到 blockers.md + 向用户报告
    │
    ▼
Phase 4: 重新提交
    ├── 提交修复代码
    ├── 触发 CI 重新运行
    └── 等待结果
    │
    ▼
Phase 5: 输出报告
    ├── CI 通过 → 一句话确认
    ├── CI 仍失败 → 记录失败原因 + 建议人工介入
    └── 严重偏差 → 追加到 blockers.md
```

---

## CI 平台适配

### GitHub Actions

```bash
# 获取最近 workflow run
gh run list --workflow="<workflow-name>" --limit 1

# 获取 run 详情
gh run view <run-id>

# 获取日志
gh run view <run-id> --log --fail-fast
```

### GitLab CI

```bash
# 获取 pipeline 状态
curl --header "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.com/api/v4/projects/$PROJECT_ID/pipelines"

# 获取 job 日志
curl --header "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.com/api/v4/projects/$PROJECT_ID/jobs/$JOB_ID/trace"
```

### Jenkins

```bash
# 获取构建状态
curl http://jenkins-server/job/<job-name>/<build-number>/api/json

# 获取控制台日志
curl http://jenkins-server/job/<job-name>/<build-number>/consoleText
```

---

## 输出格式

### CI 通过
```
CI Feedback: ✅ CI 状态良好，无需修复。
```

### CI 失败但已修复
```
CI Feedback: ⚠️ CI 失败，已自动修复以下问题：

**失败原因**：
- [测试/构建/lint]：[具体问题]

**修复内容**：
- [文件]：[修改说明]

已重新提交，CI 正在重新运行...
```

### CI 失败且无法自动修复
```
CI Feedback: ❌ CI 失败，以下问题需要人工介入：

**失败原因**：
- [测试/构建/lint]：[具体问题]

**建议**：
- [修复建议]

以上已追加到 memory/blockers.md。
```

---

## 与 session-end 的关系

- `session-end.md` Phase 1 验证闭环中检查 CI 状态
- 如果 CI 失败，自动触发本 workflow
- 修复结果记录到 `memory/progress.md` 的 Next 节

---

## 安全注意

1. **CI Token 安全**：不要将 CI Token 写入代码或日志
2. **权限最小化**：CI 自动化只读取必要的日志信息
3. **人工确认**：重大修改（如修改测试断言）需要人工确认