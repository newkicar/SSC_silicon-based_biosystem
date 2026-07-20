# dispatch_actions JSON Schema

> 大脑（Brain）在需要转交任务时，必须在回复末尾输出此格式的 JSON 代码块。

---

## 格式要求

```json
{
  "dispatch_actions": [
    {
      "type": "create_ticket",
      "title": "工单标题",
      "description": "详细描述",
      "priority": "normal",
      "category": "员工关系",
      "target_role": "员工关系专员",
      "assignee_name": "李四"
    }
  ]
}
```

**注意**：必须用 ````json` 和 ```` 包裹，否则系统无法识别。

---

## 动作类型定义

### 1. create_ticket — 创建工单

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值 `"create_ticket"` |
| `title` | string | 是 | 工单标题（≤50字） |
| `description` | string | 是 | 详细描述（含上下文） |
| `priority` | string | 否 | `low`/`normal`/`high`/`urgent`，默认 `normal` |
| `category` | string | 否 | 分类，默认使用 `target_role` |
| `target_role` | string | 是 | 目标角色（从 users.json 角色中选择） |
| `assignee_name` | string | 否 | 精确指派人（从 users.json 姓名中选择） |

**示例**:
```json
{
  "type": "create_ticket",
  "title": "考勤异常申诉处理",
  "description": "员工张三(110031)申诉6月15日迟到记录，原因是地铁故障",
  "priority": "normal",
  "target_role": "考勤专员",
  "assignee_name": "王五"
}
```

### 2. create_notification — 创建通知

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值 `"create_notification"` |
| `title` | string | 是 | 通知标题 |
| `content` | string | 是 | 通知内容 |
| `target_user` | string | 否 | 目标用户，`all_ssc`/`all_managers`/逗号分隔用户名 |
| `notif_type` | string | 否 | `info`/`warning`/`alert`，默认 `info` |

**示例**:
```json
{
  "type": "create_notification",
  "title": "6月考勤数据更新完成",
  "content": "全公司人均加班12小时，环比下降5%",
  "target_user": "all_managers",
  "notif_type": "info"
}
```

### 3. dispatch_cli_task — 分派 CLI 任务

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值 `"dispatch_cli_task"` |
| `title` | string | 是 | 任务标题 |
| `description` | string | 是 | 任务描述 |
| `priority` | string | 否 | `low`/`normal`/`high`/`urgent` |
| `category` | string | 否 | 分类 |

**示例**:
```json
{
  "type": "dispatch_cli_task",
  "title": "刷新花名册数据",
  "description": "执行 refresh_roster.py 更新员工花名册.xlsx",
  "priority": "normal"
}
```

---

## 优先级定义

| 值 | 说明 | 使用场景 |
|----|------|---------|
| `low` | 低优先级 | 数据查询、报表生成 |
| `normal` | 普通 | 常规工单处理 |
| `high` | 高 | 时效性强的任务（24h内） |
| `urgent` | 紧急 | 敏感话题、系统故障、仲裁/举报 |

---

## 验证规则

分派器（dispatcher.py）执行前的验证：

1. `type` 必须是上述三种之一
2. `title` 非空且 ≤100 字符
3. `description` 非空
4. `priority` 必须是有效值（默认 `normal`）
5. `target_role` 必须在 users.json 中存在对应角色
6. `assignee_name` 如果提供，必须在 users.json 中存在对应人员

验证失败的 action 将被跳过并记录错误日志。