# DeepAgents 编码规则（精简版）

> **Agent 项目专用**。默认存放在 `.clinerules/l2/`，**不会**被 Cline 自动加载。使用 `deploy.ps1 -L2 deepagents` 复制到 `.clinerules/` 根目录后生效。
> 平台特化（子代理/解释器/Windows/PTC/Rubric）见 `.agents/skills/deepagents-advanced/SKILL.md`，按需激活。
> 安全、泛化、正则边界见 `.clinerules/00-core.md`（单一真理源）。
> 最后更新：2026-06-26 | 基于 DeepAgents v3.0 最佳实践指南

---

## 一、核心架构认知

`create_deep_agent()` 已内置完整的 middleware 栈（Skills、TodoList、Filesystem、SubAgent、Summarization、PatchToolCalls）。**不要手写 Planner→Searcher→Verifier 节点——LLM 天然具备推理能力。**

### 1.1 执行模型

```
协调者（coordinator）+ 子代理（subagents）+ 工具（tools）+ 中间件栈（middleware）
```

| 维度 | 组件 | 一句话本质 |
| --- | --- | --- |
| **可观测** | Event Streaming | 订阅 agent 树事件流：消息、工具调用、子代理生命周期 |
| **可装配** | Profiles | 按 provider:model 自动匹配 prompt/middleware/工具集 |
| **运行时计算** | Interpreters | Agent 写 JS 代码做循环/分支/重试/聚合，压缩上下文 |
| **子代理编程** | Programmatic Subagents | 用 `task()` 把子代理当可调 worker 来 fan-out/verify/recur |
| **质量闭环** | Grading Rubrics | LLM-as-Judge 按 rubric 打表，不过关重做直到满足 |

### 1.2 参数速查

```python
agent = create_deep_agent(
    model=get_llm(),           # 必须：LLM 模型实例
    system_prompt="你是...",    # 自定义系统提示
    tools=[search_policy],     # 自定义工具列表
    backend=StateBackend(),    # 文件系统后端
    checkpointer=MemorySaver(),# 跨轮次记忆
    memory=["./memories/AGENTS.md"],  # 长期记忆
    skills=["./skills/"],      # 技能目录（整个目录）
    middleware=[               # 自定义中间件栈
        CodeInterpreterMiddleware(),  # JS 解释器
        RubricMiddleware(...),         # 评分自校正
    ],
)
```

---

## 二、核心心智：信任 LLM，拒绝过度防御

1. **语义匹配原则**：详见 00-core §3.3。严禁用正则对非结构化自然语言做语义匹配。
2. **去防御性编程**：需要三层以上防御逻辑说明架构错了，应推翻重来。
3. **信息获取策略**：
   - **显式优先**：系统已知信息（如登录态用户ID、工号）必须直接传参。
   - **推断兜底**：用户输入文本允许 LLM 提取实体；置信度低或信息缺失时才反问澄清。
   - **禁止盲目猜测**：无上下文依据时禁止编造数据。

---

## 三、System Prompt

1. **只写业务逻辑**，不要复制官方 harness prompt（避免注意力稀释）。
2. **用「信息充足性原则」**代替硬编码映射表：审视已有信息→判断足够性→不足则调工具→仍不足则调整关键词→最终无法获取则明确告知「暂无该数据」。
3. **重试时清空上下文**：当步骤执行失败需要重试时，不要把错误信息带入下一轮（`if attempts > 1: context_summary = ""`）。

---

## 四、工具设计

1. **语义拆分**：拆分成独立工具（如 `search_policy`、`query_attendance`），禁止大而全的 `do_everything`。
2. **返回值双轨制**：
   - **底层协议**：工具返回**结构化数据**（包含来源、字段解释、原始数据），供 LLM 进行逻辑判断。
   - **输出呈现**：在 System Prompt 中指导 LLM，**仅在对用户的最终回复中**，将数据转换为自然语言描述。
3. **工具描述要具体**：说明能获取什么、什么时候用，拒绝「搜索文档」等模糊描述。

---

## 五、Skills

1. **传入整个 skills 目录**：`create_deep_agent(skills=["./skills/"])`，禁止自己做匹配。
2. **交给框架 progressive disclosure**：禁止手写正则/LLM 匹配逻辑。
3. **SKILL.md 的 description 要具体**：说明做什么和何时用（如 "Extract text from PDF, fill forms" 而非 "Helps with PDFs"）。
4. **场景特化指令放 Skill 里**：不要污染通用执行上下文，由 progressive disclosure 按需注入。
5. 添加新 skill 只需创建目录和 SKILL.md，无需改动业务代码。

---

## 六、Profiles（按模型装配配置）

> `register_harness_profile(key, HarnessProfile(...))` 把模型差异的配置收口到注册处。

1. **安全沙箱隔离**：使用 `excluded_tools` 排除 `ls`/`read_file`/`write_file`/`edit_file`/`glob`/`grep` 等底层文件系统工具。
2. **Key 格式**：`"openai"`（provider 级）或 `"openai:gpt-5.5"`（model 级，更优先）。
3. **合并语义**：同 key 重复注册 = 合并而非替换。
4. **Internal API 适配层**：版本升级可能变化，封装在单一适配层中，不要在业务代码中直接导入 `_HarnessProfile`。
5. `FilesystemMiddleware`、`SubAgentMiddleware` 不能用 `excluded_middleware` 排除，只能通过 `excluded_tools` 隐藏工具。

---

## 七、数据查询

1. **通用化向量检索**：Excel/CSV 每行所有字段转文本块向量化，禁止硬编码返回字段。
2. **索引构建策略**：
   - **静态知识（政策/文档）**：启动时构建索引。
   - **动态数据（考勤/人员信息）**：提供实时查询工具连接数据库。
3. **渠道分流**：Web 端走 RAG 政策文档，CLI 端走 RAG + 数据库。
4. **正则使用边界**：见 00-core §3.3。Input Guardrails 层可用正则做强格式预处理，再交给 LLM。

---

## 八、Interpreters & Programmatic Subagents

### 8.1 Interpreters（轻量级 JS 工作台）

- 价值：把"模型 N 个 turn + 全量 context"压缩成"一段小代码 + 紧凑返回值"。
- 默认能力：JS 执行、变量保持；**无 FS/net/shell**（严格隔离）。
- PTC allowlist = 权限边界，像写 RBAC 一样对待它。
- 跨 turn 通过 snapshot 序列化/恢复。

### 8.2 Programmatic Subagents（`task()` 编排）

- 子代理变成可在 JS 里 `await task(...)` / `Promise.all(...)` / `for` 循环的一等异步函数。
- 五种编排模式：Fan-out + Synthesize / Classify & Act / Adversarial Verification / Generate & Filter / Loop Until Done。
- 关闭：`CodeInterpreterMiddleware(subagents=False)`。

### 8.3 动态工具隔离（Marathon 模式）

按步骤 `capability` 标签动态创建 brain agent，**只注入当前步骤需要的工具**：
- `query_data` 等搜索类 → 仅搜索工具
- `skill-outlook-controller` 等 → 搜索 + execute_skill

---

## 九、Grading Rubrics（LLM-as-Judge 自校正）

> `RubricMiddleware` 在 Deep Agent 外层套一个 **do-while + LLM judge**。

1. **需要两个 model**：主模型（干活）+ grader model（打分）。
2. **给 grader tools**：能跑测试/计数/读文件，不凭空猜。
3. **max_iterations ≤ 20**。
4. 与 Validator 互补：Validator 做硬检查（正则匹配），Rubric 做软质量把关（完整性、风格）。

---

## 十、上下文管理

| 策略 | 说明 |
| --- | --- |
| **Checkpointer** | 用 `thread_id` 隔离不同用户/会话 |
| **Memory** | AGENTS.md 长期记忆文件，只放始终相关的规则 |
| **Skills** | 任务特定知识放 SKILL.md，按需加载 |
| **子代理隔离** | 重型任务委托给子代理 |
| **大输出写文件** | 子代理结果写入文件，主 agent 按需读取 |
| **限制工具返回长度** | 截断过长的工具结果 |
| **Interpreters** | 把多轮计算压缩成 JS 代码 + 紧凑返回值 |
| **Programmatic Subagents** | fan-out 结果在解释器内聚合后再回模型 |

---

## 十一、Human-in-the-Loop

1. **中断工具调用**：`interrupt_on={"delete_file": {"allowed_decisions": ["approve", "reject"]}}`。
2. **决策类型**：approve / edit / reject / respond。
3. **⚠️ PTC 不触发 interrupt_on**：程序化工具调用走 bridge 路径，不要在 PTC 中暴露敏感工具。

---

## 十二、结构化输出（Structured Output）

> `response_format` 让 Agent/Model 强制按 schema 返回。

1. **选型优先级**：直接传 schema 类型（自动选 strategy）> ProviderStrategy > ToolStrategy。
2. **`handle_errors` 别关掉**：tool calling 模拟路径上 schema 校验失败是常态。
3. 跟 `task().responseSchema` 是同一能力的两个入口：
   - `create_deep_agent(response_format=...)` → 整个 agent 最终产出结构化
   - `task({responseSchema: ...})` → 单个子代理产出结构化

---

## 十三、安全

> 通用安全红线见 `.clinerules/00-core.md` §2。DeepAgents 平台增量：

1. **禁止大脑访问文件系统**：用 HarnessProfile 排除文件系统工具，防止 LLM 编造数据。
2. **子代理权限最小化**：每个子代理只授予最小工具集。
3. **PTC allowlist = 权限边界**：只给解释器它真正需要的工具。
4. **解释器安全**：QuickJS 是同进程 VM（隔离≠主机级沙箱）。
5. **代码执行审计**：解释器执行的代码块记录到审计日志。
6. **敏感工具标记**：数据库写入、文件删除、网络请求等工具标记 `requires_approval=True`。

---

## 核心原则速查

| # | 原则 |
|---|------|
| 1 | 不做 Skill 匹配，交给框架 progressive disclosure |
| 2 | **显式优先，推断兜底** |
| 3 | 数据查询通用化，区分动静 |
| 4 | **底层结构化，表层自然语言** |
| 5 | **沙箱隔离，受控访问** |
| 6 | 正则仅用于强格式预处理（见 00-core §3.3） |
| 7 | System Prompt 只写业务 |
| 8 | 批量任务用 PTC，编排用 task() |
| 9 | 质量要求用 Rubric |
| 10 | UI 用 stream.subagents |
| 11 | **用 Profiles 统一装配** |
| 12 | **Interpreters 压缩上下文** |
| 13 | **PTC allowlist = 权限边界** |
| 14 | **Grader 给工具而非玄学** |
| 15 | **动态工具隔离** |
| 16 | **场景特化指令放 Skill 里** |
