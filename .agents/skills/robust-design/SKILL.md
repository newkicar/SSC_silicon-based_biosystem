---
name: robust-design
description: "确保代码泛化、处理边界情况，避免只为单个测试用例写的死代码。写业务逻辑或实现新功能时激活。"
version: 1.1
---

# robust-design

> 原则权威来源：`.clinerules/00-core.md` §3.2。本 Skill 提供**可执行步骤**。

## 何时使用

- 实现新功能或修改业务逻辑时
- 发现代码里出现具体名字、数字、字符串常量时
- 测试只覆盖 prompt 中的示例输入时

## 步骤

1. **识别变量**：需求里哪些是示例值，哪些是不变常量？
2. **参数化**：示例值 → 函数参数或配置文件项。
3. **定义边界**：明确合法输入的类型、范围、必填项。
4. **边界测试**：每个逻辑分支至少 2 个用例——一个合法、一个非法/边界。
5. **重构条件**：`if value == 5` → `if value > threshold`；`if name == "张三"` → 通用匹配逻辑。

## 自检清单

- [ ] 逻辑是否依赖测试用例的特定措辞或示例值？
- [ ] 魔法数字是否已替换为命名常量？
- [ ] 输入稍微不同于示例时，代码是否仍正确？
- [ ] 3 个不在 prompt 里的输入能否正确处理？（00-core §3.2）

## 反模式

```python
# BAD: 只为测试用例写死
if user_input == "帮我查张三的考勤":
    return query("110430")

# GOOD: 通用逻辑
employee_id = resolve_employee(user_input)  # LLM 或结构化解析
return query(employee_id)
```
