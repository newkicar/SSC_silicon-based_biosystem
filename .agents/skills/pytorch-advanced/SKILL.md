---
name: pytorch-advanced
description: "PyTorch 进阶：混合精度、分布式训练、梯度累积、实验追踪、模型导出、Windows/CUDA 适配。深度学习项目需上述能力时激活。"
version: 1.0
---

# PyTorch Advanced

> 工程底线见 `.clinerules/00-core.md`；DL 基础结构见 `.clinerules/l2/03-pytorch-code-rule.md`（启用 L2 后在 `.clinerules/` 根目录）。
> 本 Skill 仅包含**进阶实现**内容。

---

## 何时使用

- 训练慢 / 显存不足 → AMP、梯度累积
- 多卡训练 → DDP
- 需要实验对比 → TensorBoard / W&B
- 部署导出 → ONNX / TorchScript
- Windows + CUDA 环境排查

---

## 混合精度 (AMP)

```python
scaler = torch.cuda.amp.GradScaler(enabled=use_amp)

for batch in loader:
    optimizer.zero_grad(set_to_none=True)
    with torch.autocast(device_type="cuda", enabled=use_amp):
        loss = criterion(model(inputs), targets)
    scaler.scale(loss).backward()
    scaler.unscale_(optimizer)
    torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm)  # 可选
    scaler.step(optimizer)
    scaler.update()
```

- `use_amp` 来自 config；CPU 训练时 `enabled=False`。
- loss 出现 NaN 时先关闭 AMP 排查，禁止静默跳过 batch。

---

## 梯度累积

显存不够时增大「有效 batch size」：

```python
accum_steps = config.grad_accum_steps
for step, batch in enumerate(loader):
    loss = criterion(...) / accum_steps
    loss.backward()
    if (step + 1) % accum_steps == 0:
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
```

- Learning rate 是否随有效 batch 缩放，必须在 config 中**显式决定**并记录到 `memory/decisions.md`。

---

## 分布式 (DDP) 要点

1. 仅主进程写 checkpoint / 日志。
2. 使用 `DistributedSampler`，每个 epoch 调用 `sampler.set_epoch(epoch)`。
3. 模型用 `DistributedDataParallel` 包装；推理导出用 `model.module` 取内部网络。
4. Windows 上 DDP 支持有限；优先 Linux 或单卡 + 梯度累积。

---

## 实验追踪

| 工具 | 记录内容 |
|------|----------|
| TensorBoard | `loss`、`lr`、图像、histogram（可选） |
| W&B | 同上 + config 快照、artifact |

**必须记录**：experiment name、git commit（若有）、config 文件路径、最佳 val metric。

---

## Checkpoint 最佳实践

```python
torch.save({
    "epoch": epoch,
    "model_state_dict": model.state_dict(),
    "optimizer_state_dict": optimizer.state_dict(),
    "scheduler_state_dict": scheduler.state_dict(),
    "best_metric": best_metric,
    "config": dataclasses.asdict(config),
}, path)
```

- 推理加载：`weights_only=True`（PyTorch ≥2.0 加载纯 tensor 时）。
- 保留 `best.pt` 与 `last.pt`；删除旧实验前确认已备份。

---

## 学习率调度

- Scheduler step 时机与 loss 计算方式一致（ per epoch vs per step 二选一，写进 config）。
- `ReduceLROnPlateau` 监控的 metric 与 early stopping 监控项保持一致。

---

## 模型导出

1. **TorchScript**：`model.eval()` + `torch.jit.trace` / `script`；输入 shape 固定时在 config 声明。
2. **ONNX**：`opset_version` 与部署端对齐；导出后用一个 dummy batch 做数值 smoke compare。
3. 导出脚本放在 `inference/export.py`，与训练代码分离。

---

## Windows / CUDA 适配

1. **编码**：子进程设置 `PYTHONIOENCODING=utf-8`（与 deepagents-advanced 一致）。
2. **DataLoader**：默认 `num_workers=0`；`pin_memory=True` 仅在 CUDA 可用时开启。
3. **CUDA 可见性**：用环境变量 `CUDA_VISIBLE_DEVICES`，不要在代码里写死 GPU 编号。
4. **路径**：一律 `pathlib.Path`；数据集路径避免中文空格未转义问题。

---

## 显存与调试

- OOM：减小 batch、gradient checkpointing、或 grad accum；禁止无限 retry 同一 batch。
- 调试过拟合：单 batch / 单样本应先能过拟合，再扩数据；这是 sanity check，不是最终目标。
- `torch.cuda.empty_cache()` 仅作调试，不要放进训练热路径。

---

## 反模式

| ❌ 避免 | ✅ 改为 |
|--------|--------|
| 训练脚本里改 `num_classes=10` | config + 从数据集读取 |
| 验证集结果反哺改模型结构 | 固定 val，最终才看 test |
| 每个 epoch 手动改 lr 常数 | Scheduler + config |
| `torch.load(path)` 无 `map_location` | `map_location=device` |
| Notebook 里 500 行训练循环 | 抽到 `trainers/` 并测试 |
