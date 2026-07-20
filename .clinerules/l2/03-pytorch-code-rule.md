# PyTorch 深度学习编码规则（精简版）

> **深度学习项目专用**。默认存放在 `.clinerules/l2/`，**不会**被 Cline 自动加载。使用 `deploy.ps1 -L2 pytorch` 复制到 `.clinerules/` 根目录后生效。
> 进阶主题（分布式/AMP/Windows/CUDA/导出）见 `.agents/skills/pytorch-advanced/SKILL.md`，按需激活。
> 安全、泛化、架构原则见 `.clinerules/00-core.md`（单一真理源）。
> 最后更新：2026-06-22

---

## 一、项目结构（层次清晰）

推荐按职责拆分，禁止把所有逻辑堆在一个 `train.py`：

```
project/
├── configs/          # 超参、路径、实验名（YAML 或 dataclass）
├── data/             # Dataset、DataLoader、transforms、collate_fn
├── models/           # nn.Module 定义
├── trainers/         # 训练/验证循环（或 Lightning 模块）
├── metrics/          # 损失函数、评估指标
├── inference/        # 推理入口（与训练解耦）
├── utils/            # seed、logging、checkpoint 工具
└── tests/            # 单元测试（Dataset、model forward shape 等）
```

**原则**：改超参不动模型结构；换数据集不改训练循环；推理不依赖训练脚本。

---

## 二、配置外置（反硬编码）

> 泛化原则见 00-core §3.2；DL 场景额外要求：

1. **超参进 config**：`lr`、`batch_size`、`epochs`、`num_classes`、数据路径等禁止写死在训练循环里。
2. **维度从数据推断**：`num_classes`、`input_channels` 从数据集或 config 读取，禁止假设「这个数据集一定是 10 类」。
3. **实验可复现**：在 config 或 CLI 中显式记录 `seed`；改动 seed/数据划分/version 时写入 `memory/decisions.md`。
4. **路径用 pathlib**：数据根目录、checkpoint 目录、日志目录可配置，禁止 scattered 绝对路径。

---

## 三、模型设计（nn.Module）

1. **`forward` 只做张量计算**：数据加载、优化器 step、日志记录放在 Trainer，不放在 Module 内。
2. **输入输出契约明确**：在 docstring 中说明 `forward` 的 shape，例如 `(B, C, H, W) -> (B, num_classes)`。
3. **子模块用 `nn.Sequential` / 独立 Block**：复杂网络拆成可复用 Block，避免 200 行 `forward`。
4. **初始化**：需要时使用 `reset_parameters` 或 documented init；不要随意复制粘贴 init 代码到每个项目层。

---

## 四、数据管道（Dataset / DataLoader）

1. **Train / Val / Test 严格分离**：划分逻辑集中在一处；禁止用测试集调参（数据泄露）。
2. **`Dataset.__getitem__` 只返回单样本**：batch 组装交给 `DataLoader`；复杂 padding 用 `collate_fn`。
3. **Transform 分 train / eval**：增强只用于训练集；验证/测试用确定性 transform。
4. **Windows 注意**：`num_workers > 0` 在 Windows 上常出问题；默认 `num_workers=0`，需多进程时再显式开启并加 `if __name__ == "__main__"` 保护。
5. **泛化**：Dataset 接受 root path + split 参数，禁止写死「只读某一张图片路径」。

---

## 五、训练循环（Trainer）

1. **`model.train()` / `model.eval()` 成对使用**：训练阶段与验证/推理阶段必须切换模式。
2. **验证/推理用 `torch.no_grad()`**：禁止在 eval 路径保留不必要的计算图。
3. **损失与指标分离**：`criterion` 用于反传；`metrics`（accuracy、F1 等）单独计算，不混在一个函数里。
4. **Optimizer 只更新 `requires_grad=True` 的参数**：冻结层时显式 `param.requires_grad = False`。
5. **Checkpoint 规范**：
   - 保存：`model_state_dict`、`optimizer_state_dict`（可选）、`epoch`、`config` 快照、**metrics**。
   - 加载：兼容 `map_location`；推理脚本只加载必要字段。
6. **禁止静默吞训练异常**：NaN loss、空 DataLoader、CUDA OOM 必须显式报错或中断（见 00-core §3.1）。

---

## 六、设备与 dtype

1. **设备抽象**：`device = torch.device(config.device)`；张量与模型 `.to(device)`，禁止散落硬编码 `"cuda:0"`。
2. **CPU 回退**：检测 CUDA 不可用时回退 CPU 并**打印一次**明确警告，禁止假装在用 GPU。
3. **dtype 一致**：混合精度等进阶用法见 Skill `pytorch-advanced`；默认保持 `float32` 直到有性能需求。

---

## 七、实验与可维护性

1. **日志用结构化工具**：`tensorboard` / `wandb` / 标准 `logging`，禁止只靠 `print` 散落训练曲线。
2. **实验目录隔离**：`runs/{experiment_name}/` 或 `checkpoints/{timestamp}/`，禁止覆盖上一次最佳模型而不备份。
3. **Notebook 与库代码分离**：探索在 notebook；可复用逻辑迁入 `data/`、`models/`、`trainers/` 并加测试。
4. **小步验证**：新建 Dataset 或 Model 后，先跑 **1 batch forward + loss backward** smoke test，再开完整训练。

---

## 八、测试与验证闭环

> 通用 verify 见 `.clinerules/workflows/verify-changes.md`。

DL 项目额外建议：

- [ ] `tests/test_model.py`：`dummy input` forward，输出 shape 正确
- [ ] `tests/test_dataset.py`：`__len__`、`__getitem__`、label 范围合法
- [ ] 收工前至少跑通 **1 epoch 或 1 batch** smoke run（或说明 GPU/数据未就绪，写入 blockers）

---

## 九、安全与依赖

> 通用安全见 00-core §2。DL 增量：

1. **不下载/run 不可信权重或脚本**；预训练权重来源必须可说明。
2. **`torch.load` 慎用 `weights_only=False`**（PyTorch 2.x 优先 `weights_only=True` 加载纯权重）。
3. **依赖版本**：`requirements.txt` 或 `pyproject.toml` 中 pin `torch` 等核心包版本。

---

## 核心原则速查

| # | 原则 |
|---|------|
| 1 | **Config 驱动**，超参/DataPath 不进业务逻辑 |
| 2 | **Model / Data / Train / Infer 四层分离** |
| 3 | **Train/Eval 模式 + no_grad 纪律** |
| 4 | **Checkpoint 含 config + metrics，可复现** |
| 5 | **Dataset 泛化**，不写死样本路径或类别数 |
| 6 | **先 smoke test 再长跑训练** |
| 7 | **结构化日志**，实验目录隔离 |
| 8 | **Windows：num_workers 默认 0** |
| 9 | **无数据泄露**，测试集不参与调参 |
| 10 | 进阶：AMP/DDP/导出见 Skill `pytorch-advanced` |
