# 洞察通知 JSON Schema

> 洞察子代理（Insight Agent）生成的洞察输出必须包含此结构的 JSON 块。

---

## 格式要求

洞察子代理输出格式：
```
[洞察分析内容 - 自然语言描述]

【洞察通知】
{"insight_type": "...", "insight_level": "...", ...}
【/洞察通知】
```

---

## 洞察数据结构

### 洞察请求（发送给大脑的 prompt）

```json
{
  "roster_summary": {
    "total_employees": 44,
    "active": 42,
    "on_leave": 2,
    "new_hires_this_month": 3,
    "departures_this_month": 1
  },
  "overtime_summary": {
    "total_hours": 520,
    "avg_hours_per_emp": 12.5,
    "top_dept": "制造一中心",
    "top_dept_hours": 180,
    "month_over_month_change": -5.2
  },
  "system_metrics": {
    "total_tickets": 156,
    "pending_tickets": 23,
    "resolved_today": 5,
    "total_queries_today": 89,
    "active_users_today": 31
  },
  "roster_detail": [
    {"dept": "制造一中心", "headcount": 120, "avg_age": 32.5},
    {"dept": "研发中心", "headcount": 85, "avg_age": 29.8}
  ],
  "overtime_detail": [
    {"dept": "制造一中心", "hours": 180, "employees": 45},
    {"dept": "研发中心", "hours": 120, "employees": 32}
  ]
}
```

### 洞察输出（大脑返回的结构化数据）

```json
{
  "insight_type": "overtime_alert",
  "insight_level": "center",
  "insight_org": "制造一中心",
  "insight_title": "制造一中心6月加班时长环比下降5.2%",
  "insight_content": "制造一中心6月累计加班180小时，环比下降5.2%。主要原因为...建议...",
  "data_sources": ["overtime_detail", "system_metrics"],
  "action_items": [
    {
      "action": "create_notification",
      "title": "制造一中心6月加班分析报告",
      "content": "制造一中心6月累计加班180小时...",
      "target_user": "110136"
    }
  ]
}
```

---

## 字段定义

### insight_type（洞察类型）

| 值 | 说明 | 触发条件 |
|----|------|---------|
| `overtime_alert` | 加班异常 | 加班时长超过阈值或环比变化 > 10% |
| `roster_change` | 人员变动 | 本月入职/离职人数超过阈值 |
| `ticket_trend` | 工单趋势 | 工单量环比变化 > 15% |
| `system_health` | 系统健康 | 活跃用户数/查询量异常 |
| `dept_anomaly` | 部门异常 | 某部门数据显著偏离平均值 |
| `general_insight` | 一般洞察 | 其他值得关注的趋势 |

### insight_level（洞察级别）

| 值 | 接收者 | 说明 |
|----|--------|------|
| `company` | 总经理/副总经理 | 公司级全局洞察 |
| `center` | 中心总监/HRBP | 中心级别洞察 |
| `department` | 部门经理/HRBP | 部门级别洞察 |
| `ssc_op` | SSC操作层员工 | SSC操作相关洞察 |

### insight_org（洞察组织）

- 公司级：`null` 或 `"all_companies"`
- 中心级：中心名称，如 `"制造一中心"`
- 部门级：部门名称，如 `"生产部"`

---

## 验证规则

洞察子代理的 `validate_insight_output()` 确保：

1. 必须包含 `insight_level`、`insight_org`、`insight_type` 三个字段
2. `insight_level` 必须是有效值（company/center/department/ssc_op）
3. `insight_type` 必须是预定义类型之一
4. 验证失败时返回错误信息，让子代理重新生成（最多3次）

---

## 通知路由规则

`resolve_notification_targets()` 根据洞察类型和级别精准路由：

| 洞察级别 | 接收者匹配规则 |
|---------|---------------|
| `company` | 总经理/副总经理按公司归属隔离 |
| `center` | 中心总监 + HRBP，洞察org必须匹配用户org |
| `department` | 部门经理 + HRBP，洞察org必须匹配用户org |
| `ssc_op` | 按 specialization 匹配岗位职责 |