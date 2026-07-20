---
name: semantic-extraction
description: "从非结构化文本中用语义理解提取信息，替代脆弱的正则。处理用户消息、LLM 输出、自然语言文档时激活。"
version: 1.1
---

# semantic-extraction

> 原则权威来源：`.clinerules/00-core.md` §3.3。本 Skill 提供**可执行步骤**。

## 何时使用

- 从用户聊天、会议纪要、LLM 回复中提取实体
-  tempted 写 `re.search(...)` 匹配自然语言时

## 步骤

1. **先判断格式**：输入是强格式死数据（UUID、工号、ISO 日期）还是自然语言？
   - 强格式 → 可用正则（见 00-core §3.3 允许列表）
   - 自然语言 → **禁止正则**，继续下面步骤
2. **结构化输出（首选）**：定义 JSON schema，让 LLM 按 schema 返回。
3. **语义分块**：无法 JSON 时，按段落/句子边界切分，而非关键词匹配。
4. **向量检索（进阶）**：长文档用 embedding 找相关段落。

## 示例

**输入**：「会议记录：Project Alpha 因服务器宕机延期。」

| 做法 | 评价 |
|------|------|
| `re.search(r'Project [A-Za-z]+')` | ❌ 换说法就失败 |
| LLM + JSON schema `{"project","reason"}` | ✅ 泛化 |

## 自检

- [ ] 这个句子换个说法表达，我的代码还能工作吗？
- [ ] 能 → 不应使用正则
