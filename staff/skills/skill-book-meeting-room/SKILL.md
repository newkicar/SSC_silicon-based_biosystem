---
name: skill-book-meeting-room
title: 操作鼠标和键盘预约会议室
description: 本指南用于指导代理操作鼠标和键盘预约会议室时，读取指定的文件、路径及参数
when_to_use: |
  当需要：
  - （模拟）操作键盘鼠标预约会议室时
priority: high
instructions: |
  当用户请求预约会议室时，按以下步骤处理：
  1. 从用户输入中提取动态参数（meeting_name、participant）
  2. 如果用户未提供某个参数，使用该参数的默认值
  3. 将 skill_name 固定为 "skill-book-meeting-room"
  4. 调用 execute_workflow 工具，传入 workflow_filename、skill_name 和 dynamic_params
---


## 提示词与文件名映射关系
**下表体现了用户的提示词对应的操作流程文件名称，你需要根据用户提供的信息，判断用户需要使用的流程文件，读取其名称，并在调用tool的时候将名称（带后缀）发送给tool**
| 提示词中关键词 | 操作流程文件名称         | skill文件路径           |
| ------------ -| ---------------------- | ----------------------- |
| 预约, 会议室   | 预约会议室工作流.xlsx | skill-book-meeting-room |



## 动态参数定义

**重要说明**：
- 所有参数名使用花括号括起来，如 `{meeting_name}`
- 如果用户未提供参数值，**必须使用默认值**
- `skill_name` 是固定值，不需要从用户输入提取

### 参数表

| 参数名           | 类型   | 默认值                    | 说明         | 提取规则                                                       |
| ---------------- | ------ | ------------------------- | ------------ | -------------------------------------------------------------- |
| `skill_name`     | 固定值 | `skill-book-meeting-room` | 技能目录名称 | 固定值，直接填入                                               |
| `{meeting_name}` | 字符串 | `重要会议`                | 会议名称     | 用户提到"会议名称XXX"时提取；未提供时使用默认值                |
| `{meeting_date}` | 字符串 | `2026-06-06`              | 会议日期     | 用户提到"会议日期XXX"时提取；未提供时使用默认值                |
| `{start_time}`   | 字符串 | `08:30`                   | 开始时间     | 用户提到"开始时间XXX"时提取；未提供时使用默认值                |
| `{end_time}`     | 字符串 | `17:00`                   | 结束时间     | 用户提到"结束时间XXX"时提取；未提供时使用默认值                |
| `{participant}`  | 字符串 | `李顺`                    | 参会人员姓名 | 用户提到"参会人员是XXX"、"姓名是XXX"时提取；未提供时使用默认值 |



## 实际文件结构（必须严格参照，不要编造文件名）

```
skill-book-meeting-room/
├── SKILL.md                          # 本说明文件
├── scripts/
│   └── execute_workflow.py           # 唯一可执行脚本（必须用这个文件名）
├── references/
│   └── 预约会议室工作流.xlsx          # 工作流配置文件
└── icon_shot/
    └── *.png                         # 操作截图
```

**⚠️ 重要：此 Skill 只有一个脚本 `scripts/execute_workflow.py`，没有其他 Python 脚本。**
**不要编造文件名（如 booking.py、reserve.py 等），只使用上面列出的实际文件。**

## 执行方式

使用 `execute` 工具运行脚本，构建命令时注意：
- 脚本路径用引号包裹（路径含空格）
- 使用相对路径：`staff/skills/skill-book-meeting-room/scripts/execute_workflow.py`
- 参数通过 `--params` 传入 JSON 字符串（所有动态参数放在一起）
- `--workflow` 只需传工作流文件名（不含路径前缀，脚本会自动从 references/ 查找）

**CLI 参数说明：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `--workflow` | 是 | 工作流Excel文件名，如 `预约会议室工作流.xlsx` |
| `--skill-name` | 否 | Skill目录名，默认 `skill-book-meeting-room`（注意：用连字符 `-`，不是下划线） |
| `--params` | 否 | 动态参数JSON字符串，如 `'{"meeting_name":"重要会议","participant":"李顺"}'` |
| `--confidence` | 否 | 图标匹配置信度，默认 0.7 |

**命令格式示例：**
```bash
python "staff/skills/skill-book-meeting-room/scripts/execute_workflow.py" --workflow "预约会议室工作流.xlsx" --params "{\"meeting_name\":\"重要会议\",\"participant\":\"李顺\"}"
```

**⚠️ 注意事项：**
- `--skill-name` 用连字符（`-`），不是 `--skill_name` 用下划线
- 不要把会议名称、参会人员等作为单独的命令行参数，它们必须通过 `--params` JSON 传入
- `--workflow` 只需文件名（如 `预约会议室工作流.xlsx`），脚本会自动从 `references/` 目录查找

## 调用示例

### 示例 1：用户提供所有参数

**用户输入**：
