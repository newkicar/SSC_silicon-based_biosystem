# DL Experiment Workflow（深度学习实验）

> **PyTorch / 深度学习项目专用**。需已通过 `deploy.ps1 -L2 pytorch` 启用 `03-pytorch-code-rule.md`。
> 小改动（改 lr、修 bug）仍可用 `bugfix-workflow.md`。

---

## Phase 1: 问题定义（无长训）

1. 明确任务类型：分类 / 检测 / 分割 / 回归 / 生成。
2. 更新或确认 `specs/acceptance-criteria.md` 中的**可量化指标**（如 val accuracy ≥ X）。
3. 记录数据路径、划分比例、类别数到 **config**（不写死在代码里）。
4. 重大选择（预训练权重、损失函数、backbone）写入 `memory/decisions.md`。

---

## Phase 2: Smoke Test（必做，先于完整训练）

1. **Model**：dummy tensor forward，输出 shape 正确（见 `tests/test_model.py`）。
2. **Dataset**：取 1–2 个样本，label 合法、transform 不报错。
3. **Train loop**：**1 batch** forward + backward + optimizer step；确认 loss 有限值、无 NaN。
4. 失败则停止，不启动 multi-epoch 训练；问题写入 `memory/blockers.md`。

---

## Phase 3: 实验迭代

1. 每次实验变更**只动一个变量**（lr / aug / backbone 等），实验名反映变量。
2. 日志写入 `runs/` 或 W&B；checkpoint 按 `03-pytorch-code-rule.md` §五 规范保存。
3. 用 **val set** 选模型；**test set** 仅在最终报告时使用一次。
4. 需要 AMP / DDP / 导出时，激活 Skill `pytorch-advanced`。

---

## Phase 4: 收工 / 交付

1. 执行 `verify-changes.md`（含 tests + 可选 smoke run）。
2. 对照 `03-pytorch-code-rule.md` 核心原则速查表。
3. 收工走 `session-end.md`：记录最佳 metric、checkpoint 路径、下次实验计划。

---

## 与 new-feature-workflow 的关系

| 场景 | 使用 |
|------|------|
| 新数据集 / 新模型架构 / 新训练范式 | 本 workflow + new-feature Phase 1（specs） |
| 调参、修 DataLoader bug | bugfix-workflow |
| 部署导出 ONNX | pytorch-advanced Skill + inference 模块 |

---

## 与 verify-changes 的关系

- 本 workflow Phase 4 调用 `verify-changes.md` 时，检测信号 `03-pytorch-code-rule.md` 即指向本规则文件
- DL 项目的验证需额外确认 smoke test 通过
