---
name: deepagents-advanced
description: "DeepAgents 平台特化：Event Streaming、Profiles、Interpreters、Programmatic Subagents、Rubric、Structured Output、Marathon 模式。编写 DeepAgents Agent 项目且需深入平台能力时激活。"
version: 2.0
---

# DeepAgents Advanced

> 通用工程底线见 `.clinerules/00-core.md`；DeepAgents 业务规则见 `.clinerules/l2/02-deepagents-code-rule.md`（启用 L2 后由 deploy 复制到 `.clinerules/` 根目录）。
> 本 Skill 仅包含**平台特化**内容。
> 最后更新：2026-06-26 | 基于 DeepAgents v3.0 最佳实践指南

---

## 一、Event Streaming —— 看见 Agent 正在做什么

> **核心**：不是只拿最终答案，而是订阅 agent **树**上发生的事件流。

### 1.1 最小可用：遍历子代理生命周期

```python
stream = agent.stream_events({...}, version="v3")

for subagent in stream.subagents:
    print(subagent.name, subagent.path, subagent.status)
    for message in subagent.messages:
        print(message.text)
```

### 1.2 分层消费：协调者 vs 子代理

```python
# 顶层（协调者）消息
for message in stream.messages:
    print("[coordinator]", message.text)

# 子代理各自的消息
for subagent in stream.subagents:
    for message in subagent.messages:
        print(f"[{subagent.name}]", message.text)
```

### 1.3 UI 实战关键

- **优先用 `stream.subagents`**（产品视角），别盯 `subgraphs`（实现视角）
- UI 场景一定要考虑 `interleave` / async 并发，否则出现"先跑完一边再显示另一边"的假象
- 嵌套子代理：`for nested in subagent.subagents:` 递归访问

---

## 二、Profiles —— 按模型/提供商打包默认配置

> **核心**：把"换模型就要改 prompt / 隐藏工具 / 加 middleware"变成**声明式配置**。

### 2.1 HarnessProfile vs ProviderProfile

| 类型 | 作用阶段 | 关键词 |
| --- | --- | --- |
| **HarnessProfile** | agent harness 装配后：prompt、工具可见性、middleware | `register_harness_profile(key, ...)` |
| **ProviderProfile** | 决定**如何构造 chat model** | `register_provider_profile(key, ...)` |

### 2.2 HarnessProfile 字段速查

```python
register_harness_profile(
    "openai:gpt-5.5",
    HarnessProfile(
        system_prompt_suffix="Respond in under 100 words.",
        excluded_tools={"execute"},
        excluded_middleware={"SummarizationMiddleware"},
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    ),
)
```

| 字段 | 作用 |
| --- | --- |
| `base_system_prompt` | 整体替换 Deep Agents 的基础 system prompt |
| `system_prompt_suffix` | 往拼好的 prompt 尾部追加文字 |
| `excluded_tools` | 按工具名丢弃工具（连 middleware 注入的工具也能杀） |
| `excluded_middleware` | 从默认栈剥离指定 middleware |
| `extra_middleware` | 追加 middleware（每条栈都生效） |
| `tool_description_overrides` | 单独覆盖某个工具的 description |
| `general_purpose_subagent` | 禁用/改名/改 prompt 通用子代理 |

### 2.3 Key 格式与合并语义

- **Key 格式**：`"openai"`（provider 级）或 `"openai:gpt-5.5"`（model 级，更优先）
- **合并语义**：同 key 重复注册 = **合并而非替换**
- **优先级**：`provider:model` > `provider` > 调用点显式参数

### 2.4 Internal API 适配层（实战经验）

`HarnessProfile` 在 deepagents v0.5.3 中是内部 API。**封装在单一适配层中**：

```python
# deepagents_compat.py
try:
    from deepagents.profiles import _HarnessProfile as HarnessProfile
    from deepagents.profiles import _register_harness_profile as register_harness_profile
except ImportError:
    try:
        from deepagents import HarnessProfile, register_harness_profile
    except ImportError:
        HarnessProfile = None
        register_harness_profile = None
```

### 2.5 禁用大脑的文件系统工具

```python
from staff.deepagents_compat import disable_brain_filesystem
disable_brain_filesystem("[大模型名称]")
```

> **[项目案例]** SSC 大脑被发现编造员工岗级"P6"——根因是大脑有文件系统工具→尝试读取不存在的文件→LLM 补全了合理但虚假的内容。用 `excluded_tools` 禁用后问题解决。

---

## 三、Interpreters —— 给 Agent 一个轻量级可编程工作区

> **核心**：把"模型 N 个 turn + 全量 context"压缩成"一段小代码 + 紧凑返回值"。

### 3.1 最小启动

```python
from langchain_quickjs import CodeInterpreterMiddleware

agent = create_deep_agent(
    model="openai:gpt-5.5",
    middleware=[CodeInterpreterMiddleware()],
)
```

### 3.2 默认能力与边界

| 能力 | 默认 | 如何开放 |
| --- | --- | --- |
| JS 执行 | ✅ | 加 middleware 就有 |
| 文件系统 | ❌ | 把 filesystem tools 放进 PTC allowlist |
| 网络 | ❌ | 把特定网络 tool 通过 PTC 暴露 |
| Shell/包安装/OS | ❌ ❌ | 请用 Sandbox |
| Agent 工具 | ❌ | **PTC allowlist** |

### 3.3 状态持久化（Snapshot）

- 每次 agent run 结束后 middleware 快照 interpreter 的 JS 内存状态 → 存进 graph state → 下次 turn 恢复
- 快照保留的是**数据值**，不是 live runtime objects
- functions/classes 不可序列化——恢复后会报错
- 快照**不回滚真实世界的副作用**

### 3.4 安全底线

> QuickJS 是**同进程 VM**（隔离≠主机级沙箱），PTC allowlist = 权限边界，像写 RBAC 一样对待它。

---

## 四、Programmatic Subagents —— 用代码把子代理当函数调度

> **核心**：把"子代理"从模型的"离散动作选项"升级成解释器里的**一等可调用的异步函数**。

### 4.1 task() 签名

```jsx
const result = await task({
  description: "具体的 prompt / 任务文本",
  subagentType: "reviewer",          // 你在 subagents=[] 里配的 name
  responseSchema: { /* JSON Schema */ }, // 可选：结构化输出
});
```

### 4.2 五种编排模式

| 模式 | 形状 | 适用场景 |
| --- | --- | --- |
| **Fan-out + Synthesize** | N 个独立单元 × 同一 worker → collect → reduce | 批量处理、并行 review |
| **Classify & Act** | items → classifier → 路由到不同专家 | 按类别分派 |
| **Adversarial Verification** | auditor → findings → verifier 确认/反驳 | 降假阳性 |
| **Generate & Filter** | 多 generator 出方案 → 代码评分/筛最优 | 多选一、淘汰赛 |
| **Loop Until Done** | while true → task → fresh items → break | 范围不固定的穷举扫描 |

### 4.3 关闭开关

```python
CodeInterpreterMiddleware(subagents=False)
```

---

## 五、RubricMiddleware —— LLM-as-Judge 驱动的迭代自校正

> **核心**：在 Deep Agent 外层套了一个 **do-while + LLM judge**。

### 5.1 装配（需要两个 model）

```python
agent = create_deep_agent(
    model="google_genai:gemini-3.5-flash",   # 干活的主模型
    middleware=[
        RubricMiddleware(
            model="anthropic:claude-haiku-4-5",  # 打分员
            max_iterations=3,
        ),
    ],
)
```

### 5.2 四种 verdict

| Verdict | 含义 | 是否继续 |
| --- | --- | --- |
| `satisfied` | ✅ 每条都过 | 结束 |
| `needs_revision` | ❌ 至少一条没过，附反馈 | 再跑一次 agent |
| `max_iterations_reached` | 还没 satisfied 但到顶了 | 结束 |
| `failed` / `grader_error` | rubric 不可评 / grader 炸了 | 结束 |

### 5.3 最佳实践

- **给 grader tools**（能跑测试/计数/读文件），而不是只让它读 transcript 玄学判断
- `max_iterations ≤ 20`
- 与 Validator 互补：Validator 做硬检查（正则匹配），Rubric 做软质量把关

---

## 六、Structured Output —— 让 Agent/Model 返回可消费的结构化数据

> **核心**：把"模型的一段话"变成"应用层可直接消费的校验后对象"。

### 6.1 选型优先级

1. **直接传 schema 类型** → LangChain 自动选 strategy（推荐）
2. **显式 ProviderStrategy** → 走厂商原生结构化输出 API
3. **显式 ToolStrategy** → 走 tool calling 模拟结构化输出（兜底）

### 6.2 ToolStrategy 错误处理

- **`handle_errors` 别关掉**——tool calling 模拟路径上 schema 校验失败是常态
- 自动重试 + 错误反馈，多消耗一次模型 turn
- 支持 `Union[SchemaA, SchemaB]` 多 schema 二选一

### 6.3 支持的 Schema 类型

- ✅ Pydantic BaseModel → 返回校验后的 Pydantic 实例
- ✅ dataclass / TypedDict / JSON Schema → 返回 dict
- ✅ `Union[SchemaA, SchemaB]` → 模型按上下文二选一（仅 ToolStrategy）

---

## 七、子代理 (SubAgent) 最佳实践

1. **只传业务上下文**：子代理的 System Prompt 只写与当前任务直接相关的业务逻辑，**禁止**照搬父代理的完整系统提示（避免累积噪声）。
2. **压缩中间过程**：子代理返回的结果应在父代理中由 LLM 进行自然语言压缩，而非直接向用户抛 raw JSON。
3. **类型安全**：子代理的工具参数必须显式声明类型（`arg_types`），避免 LLM 编造参数。
4. **权限最小化**：每个子代理只授予完成当前任务所需的最小工具集。

---

## 八、Marathon 模式（长时间运行任务）

### 8.1 动态工具隔离

按步骤 `capability` 标签动态创建 brain agent，**只注入当前步骤需要的工具**：
- `query_data` 等搜索类 → 仅搜索工具
- `skill-outlook-controller` 等 → 搜索 + execute_skill

> **[项目案例]** "帮我查讲师申请政策，然后发到我邮箱"——Step 1 的大脑拥有 execute_skill 工具，LLM 看到最终要发邮件就提前发了，导致重复发邮件。改用动态工具隔离后，Step 1 只有搜索工具，物理上无法发邮件。

### 8.2 幂等性缓存

RubricMiddleware 重试时会重新执行整个 brain agent loop，导致 execute_skill 被重复调用。
- 缓存 key = hash(execution_context_id + task_description)
- LRU 上限 64 条，60 秒 TTL
- 不同步骤/不同 attempt 不共享缓存

### 8.3 Skill 内容预注入

executor 在调用 execute_skill 前，根据 task_description 匹配最可能的 Skill，读取其 SKILL.md 核心指令注入到任务中。

### 8.4 验证器设计（证据优先原则）

优先级：硬证据（正则匹配工单号）> 正面信号 > 保守负面信号 > 默认通过

### 8.5 节点序列化要求

所有节点必须返回纯 dict，不能返回 dataclass 对象（LangGraph StateGraph dict.update() 无法合并嵌套对象）。

---

## 九、Windows 平台适配

1. **子进程编码**：Windows 下创建子进程时必须设置环境变量 `PYTHONIOENCODING=utf-8`，防止中文输出乱码。
2. **路径分隔符**：使用 `pathlib.Path` 而非 `os.path`，自动处理 `\\` vs `/`。
3. **终端命令**：PowerShell/CMD 的 chaining 语法不同（`&&` vs `;`），生成命令时需检测当前 Shell 类型。
4. **CUDA 可见性**：用环境变量 `CUDA_VISIBLE_DEVICES`，不要在代码里写死 GPU 编号。
5. **DataLoader**：默认 `num_workers=0`；`pin_memory=True` 仅在 CUDA 可用时开启。

---

## 十、PTC (Patch Tool Calls — 工具调用修复)

**适用场景**：当 Agent 的工具调用格式错误时，PTC 在调用执行层之前自动修复。

1. **不要依赖 PTC 修复业务逻辑错误**：PTC 仅修复格式/协议层错误。
2. **修复失败时明确报错**：返回明确错误（含原始调用与修复尝试），禁止静默丢弃。
3. **PTC 修复日志**：启用 PTC 时配置 `PTC_DEBUG=1`，便于追踪修复频率和模式。
4. **⚠️ PTC 不触发 interrupt_on**：程序化工具调用走 bridge 路径，不要在 PTC 中暴露敏感工具。

---

## 十一、上下文管理最佳实践

| 策略 | 说明 |
| --- | --- |
| **Checkpointer** | 用 `thread_id` 隔离不同用户/会话 |
| **Memory** | AGENTS.md 长期记忆文件，只放始终相关的规则 |
| **Skills** | 任务特定知识放 SKILL.md，按需加载 |
| **子代理隔离** | 重型任务委托给子代理 |
| **大输出写文件** | 子代理结果写入文件，主 agent 按需读取 |
| **限制工具返回长度** | 截断过长的工具结果 |
| **重试清空上下文** | 避免 LLM 围绕错误信息讨论 |
| **Interpreters 压缩上下文** | 把多轮计算压缩成 JS 代码 + 紧凑返回值 |

---

## 十二、安全（DeepAgents 特化）

> 通用安全红线见 `.clinerules/00-core.md` §2。以下为 Agent 平台增量：

1. **禁止大脑访问文件系统**：用 HarnessProfile 排除文件系统工具，防止 LLM 编造数据。
2. **子代理权限最小化**：每个子代理只授予完成当前任务所需的最小工具集。
3. **PTC allowlist = 权限边界**：只给解释器它真正需要的工具。
4. **解释器安全**：QuickJS 是同进程 VM（隔离≠主机级沙箱）。
5. **代码执行审计**：解释器执行的代码块记录到审计日志。
6. **敏感工具标记**：数据库写入、文件删除、网络请求等工具标记 `requires_approval=True`。

---

## 核心原则速查

| # | 原则 |
|---|------|
| 1 | 不做 Skill 匹配，交给 progressive disclosure |
| 2 | **用 stream.subagents 做 UI**（非 subgraphs） |
| 3 | **Profiles 统一装配**模型差异 |
| 4 | **Interpreters 压缩上下文**（JS 代码 + 紧凑返回值） |
| 5 | **task() 编排子代理**（循环/分支/并行） |
| 6 | **动态工具隔离**（按 capability 裁剪工具集） |
| 7 | **幂等性缓存**防重复执行 |
| 8 | **Grader 给工具而非玄学** |
| 9 | **PTC allowlist = 权限边界** |
| 10 | **场景特化指令放 Skill 里** |
| 11 | **重试清空上下文** |
| 12 | **节点返回纯 dict**（Marathon 序列化） |
| 13 | **证据优先验证**（硬证据 > 正面信号 > 保守负面信号 > 默认通过） |