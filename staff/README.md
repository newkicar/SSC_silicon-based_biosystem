# SSC硅基生物系统 — 员工终端 (Staff Terminal)

**最后更新：** 2026-06-05

---

## 一、项目目录结构总览

```
基于deepagents的SSC硅基生物系统/
│
├── src/                            # 【服务端】核心业务代码（部署在服务器上）
│   ├── api/                        #   FastAPI 服务端
│   │   ├── server.py               #     所有API端点
│   │   │                           #       认证 / Dashboard / 智能问答
│   │   │                           #       用户管理 / 工单 / 通知
│   │   │                           #       ★ Skill管理 API（上传/列表/下载/检查更新）
│   │   ├── services.py             #     工单/通知/用户资料服务
│   │   └── static/                 #     前端静态资源
│   ├── brain.py                    #   大脑（LLM决策中枢）
│   ├── main.py                     #   消息处理主流程
│   ├── spine/                      #   脊髓（上行识别 + 下行分派）
│   │   ├── ascending.py            #     上行：身份识别+意图增强
│   │   ├── descending.py           #     下行：任务翻译+编排
│   │   └── dispatcher.py           #     ★ 分派器（执行大脑的dispatch_actions）
│   ├── ganglion/                   #   中枢神经节（反射弧）
│   ├── memory/                     #   三层记忆系统
│   ├── security/                   #   认证/权限/RBAC
│   ├── tools/                      #   秘书（数据采集）
│   ├── data/                       #   数据层
│   │   ├── cli_tasks.py            #     任务队列（大脑→员工的桥梁）
│   │   └── skill_registry.py       #     ★ Skill注册中心（服务端管理）
│   ├── skills/                     #   大脑层Skill（role_routing等，仅决策用）
│   └── config/                     #   配置
│
├── staff/                          # 【员工端】员工终端（部署在员工电脑上）
│   ├── terminal.py                 #   ★ 终端主程序（登录/对话/任务管理/Skill同步）
│   ├── role_agent.py               #   ★ 角色Agent（读取本地Skill，自动执行）
│   ├── skill_sync.py               #   ★ Skill同步（从服务端检查+下载+删除）
│   ├── skills/                     #   本地Skill存放（自动同步，勿手动改）
│   │   └── {skill-name}/           #     每个Skill一个目录
│   │       ├── SKILL.md            #       技能说明（AI读这个来决定如何执行）
│   │       └── scripts/            #       可执行脚本
│   │           └── helper.py       #       示例：工作总结脚本
│   ├── work_summaries/             #   ★ 工作总结输出目录（skill-work-summary 专用）
│   └── README.md                   #   本文件
│
├── data/                           # 【运行时数据】
│   ├── auth.db                     #   SQLite数据库（用户/工单/任务/Skill注册）
│   ├── ssc_memory.db               #   对话记忆数据库（Episodic Memory）
│   ├── skill_packages/             #   ★ Skill包仓库存储（管理员上传的zip包）
│   │   ├── {skill-name}.zip        #     原始zip包（供CLI下载）
│   │   └── {skill-name}/           #     解压后的目录（供服务端读取元数据）
│   └── chroma_db/                  #   向量数据库（RAG知识库）
│
├── docs/                           # 【文档】
├── scripts/                        # 【脚本】测试和工具脚本
│   ├── test_skill_registry.py      #   Skill注册中心测试（32项）
│   └── test_phase11.py             #   Phase 11 任务分派测试
├── resources/                      # 【资源】Logo等静态资源
└── .gitignore
```

**★ 标记** = 本次新增/重点改动的文件

---

## 二、快速开始

### 1. 启动服务端（在服务器上）

```bash
cd "d:\Python Project\基于deepagents的SSC硅基生物系统"
python -m src.api.server
```

服务端启动后：
- API地址：`http://localhost:8000`
- Swagger UI（操作手册）：`http://localhost:8000/docs`
- 门户前端：`http://localhost:8000/portal`

### 2. 启动员工终端（在员工电脑上）

```bash
# 如果在同一台电脑上测试
python -m staff.terminal --server http://localhost:8000

# 如果在局域网内的其他电脑上（用服务器的IP地址）
python -m staff.terminal --server http://10.212.49.122:8000

# 自动登录
python -m staff.terminal --server http://10.212.49.122:8000 --user zhangsan --password 123456
```

登录后终端会自动同步 Skill：
```
📦 正在同步 Skill...
  ✅ Skill 'skill-work-summary' new → v1.0.0
✅ Skill 同步完成: 1个新增, 0个更新, 0个删除
```

---

## 三、Skill 管理完整操作指南

### 3.1 创建 Skill

#### 文件夹结构

```
my-skill/                     # Skill名称（英文，用-连接）
├── SKILL.md                  # 必须有！技能说明文件
└── scripts/                  # 可选，放可执行脚本
    ├── script_a.py           # 主脚本
    └── script_b.py           # 辅助脚本
```

#### SKILL.md 模板

```markdown
---
name: my-skill
display_name: 我的技能
description: 这个技能的功能描述（AI会读这段来判断何时使用）
target_roles:
  - 人事专员
  - SSC主管
input_schema:
  param1:
    type: string
    required: true
    description: 参数说明
---

# 我的技能

## 用途
描述这个技能的用途和使用场景。

## 使用说明
描述如何调用脚本，参数格式等。

## 脚本说明
- `scripts/script_a.py`: 功能说明
- `scripts/script_b.py`: 功能说明
```

**关键字段说明：**

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ | Skill 唯一标识（英文+数字+连字符） |
| `display_name` | ❌ | 显示名称（中文可） |
| `description` | ❌ | 功能描述（AI 靠这个判断是否使用此 Skill） |
| `target_roles` | ✅ | **指定哪些角色可以使用此 Skill** |
| `input_schema` | ❌ | 输入参数定义（文档性质） |

#### 脚本约定

1. **调用方式**：`python scripts/script_a.py --params '{"key": "value"}'`
2. **输出格式**：必须输出 JSON 到 stdout
3. **返回值**：`{"success": true, "message": "..."}` 或 `{"success": false, "message": "..."}`

示例脚本：
```python
import sys, json, argparse
parser = argparse.ArgumentParser()
parser.add_argument("--params", type=str, default="{}")
args = parser.parse_args()
params = json.loads(args.params)
# ... 执行业务逻辑 ...
print(json.dumps({"success": True, "message": "执行完成"}, ensure_ascii=False))
```

### 3.2 打包 Skill

```bash
# 在 Skill 目录的父目录执行
# 假设 my-skill/ 在当前目录下
# Windows: 选中 my-skill 文件夹 → 右键 → 发送到 → 压缩(zipped)文件夹

# Linux/Mac:
cd my-skill/..
zip -r my-skill.zip my-skill/
```

打包后的结构：
```
my-skill.zip
└── my-skill/
    ├── SKILL.md
    └── scripts/
        └── script_a.py
```

### 3.3 上传 Skill 到服务端

#### 方法一：通过 Swagger UI（推荐）

1. 启动服务端 `python -m src.api.server`
2. 浏览器打开 `http://localhost:8000/docs`
3. 点击顶部 **Authorize** 按钮 → 输入管理员账号（admin / {{ADMIN_PASSWORD}}）→ Authorize
4. 找到 **POST /api/skills/registry** → 点 **Try it out**
5. 填写参数：

| 参数 | 示例值 | 说明 |
|------|--------|------|
| `skill_name` | `my-skill` | 必须和文件夹名一致 |
| `display_name` | `我的技能` | 显示名称 |
| `description` | `功能描述` | AI用的描述 |
| `version` | `1.0.0` | 版本号 |
| `target_roles` | `["人事专员","SSC主管"]` | **JSON数组格式** |
| `file` | 选择 zip 文件 | 点 Choose File |

6. 点击 **Execute**

#### 方法二：通过 curl

```bash
# 第1步：登录获取 token
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"{{ADMIN_PASSWORD}}"}'
# 从返回中取 token 字段

# 第2步：上传 Skill
curl -X POST "http://localhost:8000/api/skills/registry" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "skill_name=my-skill" \
  -F "display_name=我的技能" \
  -F "description=功能描述" \
  -F "version=1.0.0" \
  -F 'target_roles=["人事专员","SSC主管"]' \
  -F "file=@my-skill.zip"
```

#### 方法三：通过 Python 脚本（批量上传用）

```python
import requests
# 登录
resp = requests.post("http://localhost:8000/api/auth/login", json={"username":"admin","password":"{{ADMIN_PASSWORD}}"})
token = resp.json()["token"]

# 上传
with open("my-skill.zip", "rb") as f:
    resp = requests.post(
        "http://localhost:8000/api/skills/registry",
        headers={"Authorization": f"Bearer {token}"},
        data={"skill_name": "my-skill", "display_name": "我的技能", "version": "1.0.0",
              'target_roles': '["人事专员","SSC主管"]'},
        files={"file": ("my-skill.zip", f, "application/zip")},
    )
print(resp.json())
```

### 3.4 修改 Skill 的目标角色（不需要重新上传）

```bash
# Swagger UI: PUT /api/skills/registry/my-skill/roles
# curl:
curl -X PUT "http://localhost:8000/api/skills/registry/my-skill/roles" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_roles":["人事专员","SSC主管","员工关系专员"]}'
```

修改后，下次员工终端登录时自动同步：
- 新增的角色 → 自动下载 Skill
- 被移除的角色 → 自动删除本地 Skill

### 3.5 更新 Skill 版本

修改本地的 Skill 文件后，重新打包上传即可。注意 version 字段要比上一次的大：

```bash
curl -X POST "http://localhost:8000/api/skills/registry" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "skill_name=my-skill" \
  -F "version=1.1.0" \
  -F "target_roles=[\"人事专员\"]" \
  -F "file=@my-skill-v1.1.0.zip"
```

员工终端登录时会检测到版本更新，自动下载新版本。

### 3.6 禁用/删除 Skill

```bash
# 禁用（不删数据，员工终端自动清理本地Skill）
curl -X PUT "http://localhost:8000/api/skills/registry/my-skill/status?status=disabled" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 重新启用
curl -X PUT "http://localhost:8000/api/skills/registry/my-skill/status?status=active" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 彻底删除
curl -X DELETE "http://localhost:8000/api/skills/registry/my-skill" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 3.7 查看所有已注册的 Skill

```bash
# Swagger UI: GET /api/skills/registry
curl -X GET "http://localhost:8000/api/skills/registry" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 四、员工终端使用指南

### 4.1 启动和登录

```bash
python -m staff.terminal --server http://10.212.49.122:8000
```

启动后：
1. 显示 Banner
2. 输入用户名和密码登录
3. 自动同步 Skill（从服务端下载最新版本）
4. 进入交互模式

### 4.2 可用命令

| 命令 | 功能 |
|------|------|
| `/help` | 显示帮助 |
| `/whoami` | 显示当前用户信息 |
| `/tasks` | 查看待处理任务 |
| `/task exec` | 自动处理所有任务（Agent 执行匹配的 Skill） |
| `/task done <id>` | 标记任务完成 |
| `/roster` | 查询花名册统计 |
| `/search 关键词` | 搜索员工 |
| `/knowledge 关键词` | 知识库检索 |
| `/logout` | 登出 |
| `/quit` | 退出 |

直接输入消息即可与 SSC 智能问答对话。

### 4.3 Skill 自动同步流程

```
员工终端启动 → 登录成功
       ↓
📦 正在同步 Skill...
       ↓
POST /api/skills/check-update
  发送: {"local_versions": {"skill-a": "1.0.0", "skill-b": "1.0.0"}}
       ↓
服务端返回:
  new:    [skill-c v1.0.0]           → 下载 → 解压到 staff/skills/skill-c/
  update: [skill-a v2.0.0]           → 下载 → 替换 staff/skills/skill-a/
  delete: [skill-b → 已被管理员禁用]  → 删除 staff/skills/skill-b/
       ↓
✅ Skill 同步完成: 1个新增, 1个更新, 1个删除
```

---

## 五、已部署的 Skill 列表

### skill-work-summary（工作总结自动化）

| 属性 | 值 |
|------|-----|
| 名称 | `skill-work-summary` |
| 功能 | 通过标准化工作流生成日报/周报/月报 |
| 目标角色 | HR_SSC学科经理, 高级HRIS工程师, 招聘主管, 员工关系专员, 薪酬主管, 薪酬专员, 考勤专员 |
| 输出位置 | `staff/work_summaries/` |
| 脚本 | `staff/skills/skill-work-summary/scripts/helper.py` |

**工作流程：**
1. 用户在终端中说"生成今天的日报"
2. Agent 读取 SKILL.md，了解工作流程
3. 调用 helper.py 获取日期范围
4. 从数据库读取该用户当天的对话记录
5. 基于真实对话数据生成六段式工作总结
6. 保存到 `staff/work_summaries/` 目录
7. 更新索引

**角色隔离机制：** 工作总结只读取当前登录用户自己的对话记录，不会交叉（详见下方"常见问题"）。

---

## 六、Skill 同步与执行架构

```
┌──────────────────────────────────────────────────────┐
│  服务端（一台机器）                                     │
│                                                       │
│  data/skill_packages/                                 │
│  ├── skill-work-summary.zip          ← 管理员上传      │
│  └── skill-work-summary/                              │
│      ├── SKILL.md                                    │
│      └── scripts/helper.py                           │
│                                                       │
│  data/auth.db                                        │
│  └── skills_registry 表               ← 元数据        │
│                                                       │
│  API: /api/skills/*                   ← 管理接口      │
│  API: /api/skills/check-update       ← CLI 查询接口   │
│  API: /api/skills/download/{name}    ← CLI 下载接口   │
└────────────────────────┬─────────────────────────────┘
                         │ HTTP
    ┌────────────────────┼────────────────────┐
    │                    │                    │
┌───┴───┐          ┌────┴───┐          ┌────┴───┐
│ CLI-A │          │ CLI-B  │          │ CLI-C  │
│人事专员│          │考勤专员│          │SSC主管 │
│       │          │        │          │        │
│skills/ │          │skills/ │          │skills/ │
│skill-a │          │skill-a │          │skill-a │
│skill-c │          │(无skill-c│        │skill-c │
│       │          │ 权限)  │          │        │
│work_  │          │        │          │work_   │
│summaries│         │        │          │summaries│
└───────┘          └────────┘          └────────┘
```

---

## 七、常见问题

**Q: 如何指定哪个 Skill 给哪些人？**
A: 上传时 `target_roles` 参数就是指定哪些角色可以使用。支持 JSON 数组格式 `["角色1","角色2"]` 或逗号分隔格式 `角色1,角色2`。

**Q: 如何修改 Skill 的目标角色？**
A: 不需要重新上传。用 `PUT /api/skills/registry/{name}/roles` 接口修改即可。

**Q: 员工能不能自己开发 Skill？**
A: 可以。开发好后打包成 zip 交给管理员（HRIS），管理员通过 Swagger UI 上传并指定目标角色。

**Q: Skill 的脚本安全吗？**
A: 脚本在员工本地电脑上执行，使用员工自己的权限。管理员上传前应审核脚本内容。

**Q: 如果服务端连不上怎么办？**
A: Skill 同步失败不影响终端基本功能（对话/查询），只是无法更新 Skill。本地已有的 Skill 继续可用。

**Q: 工作总结会交叉吗？招聘主管的信息会不会影响薪酬专员的总结？**
A: 不会。每个员工登录终端时有独立的身份（用户名+角色），工作总结只读取当前登录用户的对话记录，通过 `username` 字段过滤。详见 `staff/skills/skill-work-summary/scripts/helper.py` 中的 `read_conversations_from_db()` 函数。

**Q: 两个文件夹有什么区别？`data/skill_packages/` vs `staff/skills/`？**
