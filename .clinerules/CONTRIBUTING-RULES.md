# 如何添加新规则

> 为 PreToolUse.ps1 或 PostToolUse.ps1 添加新的质量规则。

---

## 规则引擎结构

每个规则是一个 Hashtable，包含以下字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| RuleId | string | 是 | 唯一标识，格式见下方「命名空间」 |
| Name | string | 是 | 规则名称 |
| Description | string | 是 | 规则描述 |
| Severity | string | 是 | `CRITICAL` \| `HIGH` \| `MEDIUM` \| `LOW` |
| Scope | string | 否 | `Security` \| `FileAccess` \| `CodeQuality`（可选，用于分类统计） |
| ApplicableTools | array | 是 | 适用的工具列表 |
| MatchTarget | string | 是 | `Path` \| `Content` |
| Patterns | array | 是 | 正则表达式列表 |
| Action | string | 是 | `BLOCK` \| `ALERT` \| `WARN` |
| Enabled | bool | 是 | 是否启用 |
| ErrorMessage | string | 是 | 触发时的用户消息 |
| FixSuggestion | string | 否 | 修复建议（附加在 ErrorMessage 后的 `⚠️ Fix: ...`） |
| ValidationLogic | scriptblock | 否 | 复杂校验逻辑（仅 PreToolUse） |

---

## 命名空间（RuleId 前缀选择）

新增规则时，按以下流程图选择前缀：

```
新规则属于哪个系统？
│
├─ 安全/凭据/敏感文件读取 → SEC-*
│   例: SEC-READ-001, SEC-CODE-001
│
├─ 代码质量(Python) → CODE-PY-*
│   例: CODE-PY-001 (except: 检测)
│
├─ 代码质量(JS/TS) → CODE-JS-*
│   例: CODE-JS-001 (debugger 检测)
│
├─ 泛化性 → GEN-*
│   例: GEN-001 (测试数据检测)
│
├─ 格式/编码 → OPS-FMT-*
│   例: OPS-FMT-001 (Python 编码声明)
│
├─ Memory Bank 专属 → MEM-BANK-*
│   例: MEM-BANK-001, MEM-BANK-002
│
├─ 后置审计(PostToolUse) → AUDIT-*
│   例: AUDIT-SEC-001, AUDIT-CODE-001
│   ⚠️ 注意：与 PreToolUse CODE-* 重叠的规则，只在 Pre 中保留
│
└─ 其他/通用 → CAT-*
    例: CAT-NEW-001
```

### `Scope` 字段与 RuleId 前缀的对应关系

| Scope 值 | 推荐的 RuleId 前缀 |
|----------|-------------------|
| `Security` | SEC-*, AUDIT-SEC-* |
| `FileAccess` | SEC-READ-*, MEM-BANK-* |
| `CodeQuality` | CODE-PY-*, CODE-JS-*, OPS-FMT-*, AUDIT-CODE-*, GEN-* |

---

## 添加步骤

### 1. 确定规则类型

| 需求 | 工具 | 位置 |
|------|------|------|
| 写文件前拦截 | PreToolUse.ps1 | `$script:RuleEngine` 数组 |
| 写文件后审计 | PostToolUse.ps1 | `$RuleEngine` 数组 |

### 2. 编写规则 Hashtable

**简单 Path 匹配示例：**
```powershell
@{
    RuleId      = "SEC-NEW-001"
    Name        = "RuleName"
    Description = "规则描述"
    Severity    = "HIGH"
    ApplicableTools = @("write_to_file")
    MatchTarget = "Path"
    Patterns    = @('pattern_regex')
    Action      = "BLOCK"
    Enabled     = $true
    ErrorMessage = "拦截消息"
},
```

**复杂 Content 校验示例（PreToolUse only）：**
```powershell
@{
    RuleId      = "CODE-NEW-001"
    Name        = "ComplexRule"
    Description = "需要复杂逻辑的规则"
    Severity    = "HIGH"
    ApplicableTools = @("write_to_file")
    MatchTarget = "Content"
    Patterns    = @('\.py$')
    Action      = "BLOCK"
    Enabled     = $true
    ValidationLogic = {
        param($content, $filePath)
        $errors = @()
        # 自定义校验逻辑
        if ($content -notmatch "expected_pattern") {
            $errors += "❌ 缺少期望的模式"
        }
        return $errors
    }
    ErrorMessage = "校验失败消息"
},
```

### 3. 避免重复规则

添加规则前，**先检查现有规则是否已覆盖**：
- PreToolUse 的 `CODE-PY-001` 已检测 `except:` → PostToolUse 不需要 `AUDIT-PY-001`
- 同类检测只保留在 PreToolUse（更早拦截，效果更好）

### 4. 测试规则

在 Cline 中尝试触发规则，确认：
- 规则能正确匹配目标文件
- 触发时显示正确的 ErrorMessage
- 不影响正常操作

### 5. 更新文档

在本文档的规则目录中添加条目（如需要）。

---

## 常见陷阱

1. **PowerShell 单引号字符串中的单引号**：用 `'\"' + "'" + '\"'` 拼接
2. **正则表达式特殊字符**：`.` `*` `+` `?` 需要转义
3. **ValidationLogic 中的 `$` 符号**：需要用 `$$` 转义
4. **ApplicableTools 不匹配**：确认工具名与 Cline 内部名称一致
5. **Enabled = $false 忘记改回**：调试完成后记得启用

---

## 禁用/启用规则

临时禁用规则：将 `Enabled = $true` 改为 `Enabled = $false`。

全局开关：编辑文件顶部，注释掉对应规则块。