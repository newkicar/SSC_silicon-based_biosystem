---
name: employment-certificate
display_name: 开具在职证明
description: >
  为员工开具在职证明文件，并通过邮件发送给员工本人。
  当任务包含"在职证明"关键词时，自动调用此技能。
target_roles:
  - 员工关系专员
  - 员工关系主管
  - HR_SSC经理
input_schema:
  employee_name:
    type: string
    required: true
    description: 员工姓名
  employee_id:
    type: string
    required: false
    description: 员工工号
  purpose:
    type: string
    required: false
    description: "用途（如：银行贷款、签证、入职等）"
output_description: 返回生成的在职证明文件路径和发送结果
requires_approval: false
---

# 开具在职证明

## 技能说明

本技能用于自动为员工开具在职证明文件。

## 执行流程

1. 从花名册中查询员工信息（姓名、工号、部门、岗位、入职日期等）
2. 生成在职证明文件（格式化文本）
3. 保存到 `data/certificates/` 目录
4. 通过邮件发送给员工本人（MVP阶段为模拟发送）

## 调用方式

执行脚本：`execute.py`

```bash
python execute.py --employee_name "张三" --purpose "银行贷款"
```

或通过Python API调用：

```python
from src.skills.employment_certificate.execute import execute
result = execute({"employee_name": "张三", "purpose": "银行贷款"})
```

## 输入参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| employee_name | string | 是 | 员工姓名 |
| employee_id | string | 否 | 员工工号（用于精确匹配） |
| purpose | string | 否 | 用途，默认"个人事务" |

## 输出

```json
{
  "success": true,
  "message": "已为张三（研发二部 / 高级工程师）开具在职证明...",
  "file_path": "data/certificates/在职证明_张三_20260604162303.txt",
  "email_sent": true
}
```

## 注意事项

- 员工必须在花名册中存在，否则返回失败
- 文件保存在 `data/certificates/` 目录下
- 邮件发送为MVP模拟，实际环境需接入邮件API
- 该操作为低风险操作，无需人工审批