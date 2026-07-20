# 数据管理操作手册

> SSC硅基生物系统 — 花名册、加班数据、向量索引、Skill管理的日常维护操作指南

**最后更新：** 2026-06-22

---

## 一、总体流程

```
┌─────────────────────────────────────────────────────────┐
│                    每日自动流程 (05:00)                     │
│                                                          │
│  CC/DL清册 ──→ refresh_roster.py ──→ 员工花名册.xlsx     │
│  SAP考勤API ─→ build_overtime.py ──→ 加班基础数据.xlsx   │
│                                      ↓                   │
│                              向量索引增量更新              │
│                              (db_index.pkl)              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    手动触发流程                            │
│                                                          │
│  运行脚本 → 数据文件更新 → 手动更新索引                   │
│  python -m src.api.server --update-db <文件名.xlsx>      │
└─────────────────────────────────────────────────────────┘
```

---

## 二、花名册自动刷新

### 数据来源

| 来源 | 文件路径 | 内容 |
|------|---------|------|
| CC人员清册 | `{{INTERNAL_HR_PATH}}...\新版CC人员清册(日期).xlsx` | 管理层+技术人员（加密，密码{{EXCEL_PASSWORD_CC}}） |
| DL人员清册 | `{{INTERNAL_HR_PATH}}...\新版DL人员清册(日期).xlsx` | 产线员工（加密，密码{{EXCEL_PASSWORD_CC}}111） |
| [ERP系统接口] | `http://{{SAP_API_HOST}}:8080/system/sap/querySapRoster` | 岗级(postLevel)数据 |

### 运行

```bash
python -X utf8 scripts/refresh_roster.py
```

**注意：** CC/DL路径已改为通配解析，无需手动更新文件名。`_resolve_latest()` 自动匹配目录中最新的文件。

### 处理流程（12步）

解密CC/DL → 合并4个sheet → [ERP系统接口]岗级匹配 → 部门规范化(15条规则) → 中心补全 → 衍生字段 → 蓝领白领分类 → 特殊修正 → 删除高管 → 大级别识别 → 括号替换 → 写入Excel

### 输出

- `databases/员工花名册.xlsx`（覆盖"花名册"sheet，保留"人数预算"sheet）
- ~4244行，~79列

### 刷新后更新索引

```bash
python -m src.api.server --update-db 员工花名册.xlsx
```

---

## 三、加班数据自动构建

### 数据来源

| 来源 | 说明 |
|------|------|
| SAP考勤API `http://{{SAP_API_HOST}}:8080/system/sap/queryAttendance` | 每日考勤打卡记录 |
| 员工花名册 | 员工基础信息+蓝领白领分类 |
| `databases/assistance/不统计的人.xlsx` | 排除名单（含日期范围） |

### 运行

```bash
# 默认：当天=1日拉上月整月，≥2日拉本月1日~昨天
python -X utf8 scripts/build_overtime.py

# 指定日期范围
python -X utf8 scripts/build_overtime.py --begin 2026-01-01 --end 2026-06-17
```

### 日期逻辑

| 运行日期 | 默认拉取范围 |
|---------|-------------|
| 6月1日 | 5月1日~5月31日（上月整月） |
| 6月15日 | 6月1日~6月14日（本月1日~昨天） |

### 写入逻辑（追加，非覆盖）

读取已有文件 → 删除目标月份旧数据 → 追加新数据 → 保留其他月份（当月覆盖，跨月累加）

### 加班时长计算

| 类型 | 公式 |
|------|------|
| 白领 | `attendanceDuration + leaveDuration(合计) - 8`（不低于0） |
| 蓝领 | `overtimeDuration + overtimeHDuration + overtimeWDuration` |

### 排除规则

- 大级别9级及以上不统计
- 实习生排除
- 大客户管理部排除
- 当月入职/离职排除
- 产假/陪产假/流产假/工伤假/婚假排除
- 不统计的人.xlsx特定人员排除

### 输出

- `databases/加班基础数据.xlsx`（44列，按月追加）

### 刷新后更新索引

```bash
python -m src.api.server --update-db 加班基础数据.xlsx
```

---

## 四、服务端启动与索引管理

```bash
# 正常启动
python -m src.api.server

# 指定端口
python -m src.api.server --port 8001

# 只更新指定文件的向量索引
python -m src.api.server --update-db 员工花名册.xlsx
python -m src.api.server --update-db 加班基础数据.xlsx

# 全量重建所有向量索引
python -m src.api.server --update
```

---

## 五、Skill管理

### 5.1 Skill体系概述

系统支持两类 Skill：

| 类型 | 位置 | 说明 |
|------|------|------|
| 服务端 Skill | `src/skills/` | 通过 API 注册到 Skill Registry，CLI 端可自动同步 |
| CLI 端 Skill | `staff/skills/` | 本地安装，终端直接执行 |

### 5.2 CLI 端 Skill 同步

员工终端登录时自动向服务端检查 Skill 更新：
1. 终端登录 → 调用 `/api/skills/check-update`
2. 服务端比对版本 → 返回需新增/更新/删除的 Skill 列表
3. 终端下载 zip 包 → 解压到 `staff/skills/`
4. 更新本地版本清单 `staff/skills/local_manifest.json`

### 5.3 Skill 目录结构

```
staff/skills/
├── local_manifest.json              # 本地版本清单
├── skill-outlook-controller/        # Outlook邮件/会议控制
│   ├── SKILL.md                     # Skill说明（含HTML邮件格式要求）
│   └── scripts/
│       └── outlook_cli.py           # Outlook COM自动化脚本
├── skill-book-meeting-room/         # 会议室预约
│   ├── SKILL.md
│   └── scripts/
└── employment-certificate/          # 在职证明开具
    ├── SKILL.md
    └── scripts/
```

### 5.4 添加新 Skill

1. 在 `staff/skills/` 下创建目录（如 `skill-my-new/`）
2. 编写 `SKILL.md`（含 YAML frontmatter: name、description、target_roles）
3. 在 `scripts/` 下放置执行脚本
4. 重启终端即可使用——Marathon 的 capability_registry 会自动发现新 Skill

**SKILL.md 模板：**
```markdown
---
name: skill-my-new
description: 描述这个 Skill 做什么、什么时候用（具体，不要写"帮助xxx"）
target_roles:
  - HR_SSC学科经理
  - 考勤专员
---

## 操作说明
...
```

### 5.5 Skill 指令最佳实践

- **场景特化要求放在 SKILL.md 中**：如 Outlook 的 HTML 邮件格式、路径规则等
- **不要污染通用执行上下文**：executor 会自动将匹配到的 SKILL.md 内容注入到任务中
- **SKILL.md 的 description 要具体**：说明做什么和什么时候用，帮助 LLM 匹配

---

## 六、常见问题

| 问题 | 解决 |
|------|------|
| 端口被占用 | `python -m src.api.server --port 8001` |
| CC/DL文件名更新 | 无需操作，`_resolve_latest()` 自动匹配最新文件 |
| 新增数据文件需索引 | `python -m src.api.server --update-db 新文件名.xlsx` |
| 重启后索引需重建吗 | 不需要，索引已持久化到 `data/db_index.pkl` |
| 花名册人数预算sheet会被覆盖吗 | 不会，只覆盖"花名册"sheet |
| Marathon 执行发了重复邮件 | 检查 executor.py 的幂等性缓存是否命中，确认 execution_context_id 一致 |
| Marathon 查询步骤提前执行了后续操作 | 检查 capability_registry 是否正确标注步骤类型 |

---

## 七、文件清单

| 文件 | 作用 |
|------|------|
| `scripts/refresh_roster.py` | 花名册自动刷新 |
| `scripts/build_overtime.py` | 加班数据自动构建 |
| `scripts/aggregate_overtime.py` | 加班数据聚合分析 |
| `scripts/verify_overtime.py` | 加班数据校验 |
| `scripts/sync_users_from_json.py` | 用户信息同步 |
| `scripts/replace_overtime.py` | 加班数据替换 |
| `databases/员工花名册.xlsx` | 员工花名册（输出） |
| `databases/加班基础数据.xlsx` | 加班基础数据（输出） |
| `databases/assistance/不统计的人.xlsx` | 加班排除名单 |
| `src/scheduler/scheduler.py` | 定时任务调度器（7个定时任务） |
| `src/tools/vector_rag.py` | 向量索引管理（bge-m3 1024维） |
| `staff/marathon/` | Marathon多步骤执行引擎 |
| `staff/marathon/capability_registry.py` | 能力注册表（动态发现搜索工具+Skill+系统能力） |
| `staff/marathon/nodes/executor.py` | Marathon执行节点（动态工具隔离+幂等性缓存） |
| `staff/skills/` | CLI端Skill目录 |
| `staff/skill_sync.py` | CLI端Skill同步（登录时自动检查更新） |