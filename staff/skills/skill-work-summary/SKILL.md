---
name: skill-work-summary
description: 工作总结自动化系统，通过标准化工作流执行数据分析、报告撰写与落盘。
target_roles:
  - HR_SSC学科经理
  - 高级HRIS工程师
  - 招聘主管
  - 员工关系专员
  - 薪酬主管
  - 薪酬专员
  - 考勤专员
---

# ⚠️ 核心约束（强制执行，违反任何一条即为任务失败）

1. **严禁日期计算**：所有日期必须通过 `get_date_range()` 获取，禁止 `timedelta` 或手动解析
2. **文件名一致性**：必须使用 `generate_filename()` 返回值，禁止手动拼接
3. **路径限定**：所有输出必须保存到 `staff/work_summaries/`，禁止绝对路径或 `..` 上溯
4. **流程顺序**：严格按步骤 1→2→3→4→5→6→7→8→9 顺序执行，禁止跳步
5. **🔴 严禁编造数据**：步骤 6 必须严格基于步骤 5 的真实对话数据，宁缺毋滥
6. **🔴 必须保存文件**：步骤 8 必须调用 `write_file` 工具保存文件到磁盘，禁止只输出内容而不保存
7. **🔴 六段式格式**：步骤 6 必须严格按六段式规范输出，每段以 `## ` 开头

---

# 工具调用方式

**重要：使用 `execute` 工具运行 helper.py，命令格式如下：**

```bash
python staff/skills/skill-work-summary/scripts/helper.py get_date_range "{\"type\": \"daily\"}"
```

注意：
- 不要用 `%PYTHON_PATH%`，直接用 `python`
- 不要用 `resources/skills_subagents/`，用 `staff/skills/`
- JSON 参数用 `"{\"key\": \"value\"}"` 格式（外层双引号 + 内部转义）

---

# 流程检查表 (SOP)

**你必须按以下顺序逐步执行，每一步都不能跳过：**

| 步骤 | 操作 | 命令/说明 |
|------|------|-----------|
| **1** | 获取日期范围 | `execute: python staff/skills/skill-work-summary/scripts/helper.py get_date_range "{\"type\": \"daily\"}"` |
| **2** | 生成文件名 | `execute: python staff/skills/skill-work-summary/scripts/helper.py generate_filename "{\"type\": \"daily\", \"date\": \"步骤1返回的start_date\"}"` |
| **3** | 检查文件是否存在 | `execute: python staff/skills/skill-work-summary/scripts/helper.py file_exists "{\"filename\": \"步骤2返回的filename\"}"` |
| **4** | 获取数据源信息 | `execute: python staff/skills/skill-work-summary/scripts/helper.py get_data_source_info "{\"start_date\": \"步骤1的start_date\", \"end_date\": \"步骤1的end_date\"}"` |
| **5** | 🔴 **读取对话数据**（核心步骤，绝对不能跳过） | `execute: python staff/skills/skill-work-summary/scripts/helper.py read_conversations_from_db "{\"start_date\": \"步骤1的start_date\", \"end_date\": \"步骤1的end_date\"}"` |
| **6** | 🔴 **生成六段式内容** | **不使用任何工具**，仅基于步骤5的真实数据，在脑中生成六段式工作总结 |
| **7** | 自动处理 | Guardrail 自动脱敏（无需操作） |
| **8** | 🔴 **保存文件到磁盘** | 调用 `write_file` 工具，路径：`staff/work_summaries/{步骤2的filename}.md` |
| **9** | 更新索引 | `execute: python staff/skills/skill-work-summary/scripts/helper.py update_index "{\"filename\": \"步骤2的filename\", \"summary_type\": \"daily\", \"start_date\": \"步骤1的start_date\", \"end_date\": \"步骤1的end_date\", \"word_count\": \"实际字数\"}"` |

---

# 六段式内容规范（步骤 6 必须严格遵守）

⚠️ **极其重要**：
1. **只能描述用户的实际工作**，禁止描述 Agent 自身的执行过程
2. **宁缺毋滥**：如果对话内容不足以填充某个部分，写"无相关内容"，**绝不能虚构**
3. **视角**：站在用户的角度去写总结（用户要向上级汇报使用）
4. **基于真实数据**：所有内容必须来自步骤5返回的对话记录

**生成的文件内容必须严格按照以下格式：**

```markdown
# 工作总结

**姓名**：[用户姓名]
**日期**：[日期范围]
**类型**：日报/周报/月报

---

## 一、整体思维逻辑

（描述用户面对任务时的决策过程、优先级排序和时间分配节奏。如无相关内容可省略此节。）

---

## 二、成果展示

（使用 STAR 法则展示用户的核心业务贡献。基于步骤5的真实对话数据，实事求是。）

---

## 三、困难与解决

（用户遇到了什么具体业务障碍？如何突破的？如无困难可写"无"或省略。）

---

## 四、个人成长

（本次工作给用户带来了什么新的认知或技能提升？如无明显成长可省略。）

---

## 五、KISS 反思

- **Keep**（保持）：哪些做法有效，需要继续？
- **Improve**（改进）：哪些环节可以做得更好？
- **Stop**（停止）：哪些行为低效，必须停止？
- **Start**（开始）：下一步要尝试什么新方法？

（如无明显反思点可省略此节。）

---

## 六、下阶段规划

（基于当前进度，列出用户下一步的优先级任务。如无明确计划可省略。）
```

---

# 环境变量

执行 `read_conversations_from_db` 时，helper.py 会自动处理数据源：
- 如果本地数据库存在，直接读取 SQLite
- 如果本地数据库不存在，自动通过 HTTP API 从服务端获取

HTTP API 需要以下环境变量（由终端自动设置）：
- `SSC_SERVER_URL`：服务端地址
- `SSC_TOKEN`：认证 Token

---

# 安全纪律

- **步骤6期间**：禁止使用任何工具（包括 read_file、ls、execute 等）
- **禁止文件系统操作**：禁止 glob、grep、ls、find、mkdir、cd、pwd
- **路径约束**：仅限 `staff/work_summaries/` 目录
- **终止条件**：完成步骤9后，输出"总结已保存至 staff/work_summaries/xxx.md"，任务立刻结束