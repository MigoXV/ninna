# 完整人工 AVA 的固定训练配方

原始资产固定为 `MigoXV/vad-human-ava-speech@ee5e35d06a268fe051d3cf8c6672c42c05e60887`，原音频和 11 个字段保持完整。训练资产新增 `seconds.starts=onset`、`seconds.durations=offset-onset`，内嵌无损 FLAC；不裁剪或重新标注。按原 train 录音路径的固定哈希选 16 条 validation，得到 142/16/2，共 35.5h/4h/10min。原 test 保持独立，全部训练和权重选择结束后才评估。

| 配方 | 输入模型 | Task / 行为 |
|---|---|---|
| prepare.yaml | 无 | 固定 AVA 转换；Arrow writer_batch_size=1、每片最多 16 条 |
| scratch.yaml | model-config.json，无权重 | AttetionVadFromScratchTask，最多 20 轮，验证 F1 早停 |
| full.yaml | 基线的完整 HF 导出目录 | AttetionVadFullFinetuneTask，最多 5 轮 |
| lora.yaml | 同一个基线 HF 导出目录 | AttetionVadLoraFinetuneTask，r=8 / alpha=16，最多 5 轮 |
| export.yaml | 与源 checkpoint 相同的底座 | 完整权重导出；LoRA 合并到独立 HF 模型 |
| evaluate.yaml | 新导出模型 | 独立 test；原生 validate 绑定 validation_split=test |
| infer.yaml | 新导出模型 | 新进程重新加载，第一条 test 录音推理 |

全部采用原生 LightningCLI class_path/init_args；阈值与阈值列表固定 0.5，不用 test 选择超参。scratch 随机种子 42，学习率 3e-4、dropout 0.1；full 1e-4、LoRA 3e-4。显式 augmentation.enabled=false，缓存与增强不隐式互相覆盖。批量 2 条原录音，4 个 CPU 数据工作进程，持久特征缓存；GPU 必须显式 UUID，平台只使用单卡，FP32。optimizer、完整解析配置和每轮真实指标在 Run 中保存。

通过 MCP 调用一次 `start_run` 指定已就绪 WorkItem、数据和模型 asset_id、该配方的精确注册版本；等待 Job 返回 run_id 后跟踪 Run。手动审查可用 prepare_run_plan → READY → submit_run。导出必须指定已封存 checkpoint，promote_model 保存新本地资产，远端发布另行显式调用。

`evidence.json` 记录优化步、训练方法、总参数/可训练/冻结参数数目；`parameter_updates.json` 记录逐参数初末哈希与变化列表。LoRA 冻结底座变化数必须为 0，Full 和 Scratch 全部参数可训练。执行成功、可加载交付权重与生产精度分别验证。

可恢复真实验收：

```bash
NINNA_INTEGRATION=1 poetry run python scripts/run-vad-training-loop.py \
  --api http://127.0.0.1:8021 --framework-source /workspace/opus/preludio2 \
  --evidence outputs/vad-training-loop/state.json --version v5 --publish
```

MCP 需要连接已有服务；首次运行使用已发布 `preludio2-ava-human-v2` 环境（框架 `preludio2:ninna-v2`），或恢复证据文件中的 WorkItem。可通过 `list_environments(query="preludio2-ava-human-v2", published_only=true)` 取得固定环境版本；本次版本为 `environment_revision-e39a1784375148e3`。它封存了修正后的 AVA 转换、FLAC 解码、参数审计、独立 HF 权重评估和严格推理入口，并在真实 Docker 中验证依赖。已有环境的工作区无需每次安装依赖。

首次运行显式固定来源和创建 Project/WorkItem，源文件通过 MCP 的 SHA256 保护编辑，Scratch 小型配置通过流式上传 CLI 传输，不要求两台机器共享路径。--framework-source 是客户端的框架检出目录；--publish 是用户明确要求发布时才启用的选项，使用服务端 HF_TOKEN 变量，不在请求中传令牌。没有 evidence 时创建完整新实验；已有 evidence 时恢复封存身份。新实验使用新的 evidence 路径和 version。

重连使用相同 evidence 和 version，已保存的 Job、Run、数据及模型资产不会重复生成；配方或桥接源码改变需要新 evidence/version。全部验收完成后保存工作摘要并结束 WorkItem。完整实际结果见 [训练闭环验收](../../docs/vad-training-loop-verification.md)。

可直接使用的训练资产已公开发布：[MigoXV/vad-human-ava-speech-training](https://huggingface.co/datasets/MigoXV/vad-human-ava-speech-training)，固定提交 `849203aa634ce04d184290ed2b4f4b0fda384292`。本平台数据资产为 `asset-bd3d6dfe70ed46a0`；从零模型配置和三份可加载权重的资产身份见验收报告。复用这些资产时，可直接给新 WorkItem 调用 `start_run`，无需重新准备数据。
