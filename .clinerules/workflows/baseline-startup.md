# 建立启动基线（Startup Baseline）

> 当项目跑不起来时，先建立启动基线，而不是盲目修 bug。
>
> 目标：确认项目有一个**可重复的启动方式**，即使功能不完整。

---

## 何时使用

| 场景 | 触发 |
|------|------|
| "项目跑不起来" | 用户报告启动失败 |
| 接手新项目 | 首次尝试启动 |
| 环境变更后 | 切换 Python/Node 版本、重装依赖后 |
| CI 失败 | 持续集成报告启动失败 |

---

## 流程

### Phase 1: 诊断（只读）

1. **找启动入口**：
   - Python 项目：`__main__.py`、`setup.py`、`pyproject.toml` 的 `scripts`
   - Node.js 项目：`package.json` 的 `main` / `scripts.start`
   - Web 项目：`index.html`、`App.jsx`、`main.ts`

2. **找依赖声明**：
   - Python：`requirements.txt` / `pyproject.toml` / `Pipfile`
   - Node.js：`package.json`

3. **检查启动脚本/命令**：
   - `python -m` / `npm start` / `npm run dev` / `docker-compose up`

### Phase 2: 尝试启动

1. **安装依赖**：
   ```bash
   # Python
   pip install -r requirements.txt
   # 或
   pip install -e .

   # Node.js
   npm install
   # 或
   yarn install
   ```

2. **执行启动命令**：
   ```bash
   # 根据 Phase 1 发现的入口执行
   python main.py
   npm start
   ```

3. **记录结果**：
   - ✅ 启动成功 → 基线建立完成
   - ❌ 启动失败 → 进入 Phase 3

### Phase 3: 修复阻断性问题

| 常见问题 | 修复方向 |
|---------|---------|
| 依赖缺失/版本冲突 | 更新 requirements/package，锁定版本 |
| 环境变量缺失 | 创建 `.env.example`，记录必需变量 |
| 端口被占用 | 修改端口配置或 kill 占用进程 |
| 路径错误 | 修正启动入口路径 |
| 导入错误 | 检查包结构，补充 `__init__.py` |

### Phase 4: 记录基线

启动成功后，写入 `memory/progress.md`：

```markdown
## Startup Baseline Established
- **启动命令**：[具体命令]
- **Python/Node 版本**：[版本信息]
- **必需环境变量**：[列表]
- **已知限制**：[如有]
- **时间**：[YYYY-MM-DD HH:MM]
```

---

## 输出格式

### 成功
```
✅ 启动基线已建立。

启动命令：[command]
环境：[Python/Node vX.X]
详情已记录到 memory/progress.md
```

### 失败
```
❌ 启动基线建立失败。

**阻断问题**：
1. [问题1 + 建议修复]
2. [问题2 + 建议修复]

请确认后继续修复，或说「我自己来」。
```

---

## 与 bugfix-workflow 的关系

- **先跑 baseline-startup**：确认项目能启动
- **再跑 bugfix**：解决具体功能 bug
- 如果启动基线已经存在，新的启动失败 → 先跑 baseline-startup 诊断，再决定是否进 bugfix

---

## 自动化提示

| 信号 | 建议触发 baseline-startup |
|------|--------------------------|
| 用户说"项目跑不起来" | ✅ 立即 |
| 用户说"帮我建个项目" | ✅ 创建后自动 |
| 依赖文件变更（requirements/package.json） | ⚠️ 建议 |
| CI 启动失败 | ✅ 自动 |