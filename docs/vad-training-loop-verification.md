# 人工 AVA：MCP 真实训练闭环验收

验收日期：2026-10-04。Ninna 与 preludio2 均在 `feature/mcp-vad-training-loop` 分支修改。

本次通过官方 MCP 客户端连接运行中的 Ninna API，完成完整人工 AVA 的数据准备、从零训练、基线导出、同一基线的全量与 LoRA 微调、各自导出、独立测试和新进程推理。13 次正式运行均由平台创建真实 Docker 容器，退出码为 0；3 次历史诊断运行和一次没有创建 Run 的检查失败完整保留。

这条 Attetion VAD 路径已经可以按固定输入和配方重复完成训练。新环境、数据契约和加载方式均已沉淀；本次没有把其他框架、其他 VAD 架构、分布式训练或生产精度列为已验收。

## 结果与交付权重

| 训练方式 | 优化步 | 可训练参数 | 冻结参数 | 导出 checkpoint 的 validation F1 | 独立 test F1 | 独立 test Accuracy |
|---|---:|---:|---:|---:|---:|---:|
| 从零训练基线 | 1278 | 605,698 | 0 | 0.829523 | 0.834794 | 0.810886 |
| 全量微调 | 355 | 605,698 | 0 | 0.826865 | 0.856694 | 0.847483 |
| LoRA 微调 | 355 | 58,000 | 605,698 | 0.829816 | 0.846927 | 0.834572 |

基线从配置初始化，模型输入只有 config.json 和说明，无任何预训练权重。模型为 128 维、3 层、605,698 参数；实际训练 18 轮，验证早停，导出第 13 轮、step 994 的最佳 checkpoint。验证 F1 0.829523 高于全语音常量参照 0.672847，预测没有退化为全部语音或全部非语音。完整 1,278 步训练的参数变化证据与被选 checkpoint 分别保存，不能将训练最后一步哈希当作最佳 checkpoint 哈希。

Full 与 LoRA 都从这一份 HF 基线导出开始，不串联微调；各实际训练 5 轮、355 步，均选第 3 轮最佳 checkpoint。Full 的全部 54 个参数张量发生变化。LoRA 总参数 663,698，仅训练 58,000 参数（约 8.74%），40 个 adapter 张量变化；605,698 底座参数、54 个冻结张量变化数为 0。独立参数审计确认两种微调初始化的 54 个底座张量均与基线完全一致，两份微调导出权重都与基线不同。

三份模型均为可直接加载的完整 HF 导出目录，含 config.json、model.safetensors 和自定义模型源码。LoRA 交付模型已合并 adapter；原始 adapter checkpoint 和参数审计仍在 Run 产物中。三次导出通过严格加载检查；三次独立推理又在新进程加载各自交付目录，拒绝缺失、额外、不匹配权重或加载错误，均得到有限输出。非零 LoRA 增量合并后的前向等价性也通过针对性测试。

| 模型 | 本地平台 asset_id | 权重目录 | model.safetensors SHA-256 |
|---|---|---|---|
| scratch | `asset-37cac0ca0aa44374` | `/workspace/apps/ninna/model-bin/preludio2-attetion-vad/ava-human-baseline-v4` | `4f7ecabebf9fe6e77d8a6fe1832b0b46a04a4976e99c5a56bfa23183772fa0c0` |
| full | `asset-2452ed28ec7e4ea7` | `/workspace/apps/ninna/model-bin/preludio2-attetion-vad/ava-human-full-v4` | `4a318a7aedc37e2bba015f17bbaafeb42e7740a2b261d69af0dafe3c28b6e20f` |
| lora | `asset-83ab718a34cb4783` | `/workspace/apps/ninna/model-bin/preludio2-attetion-vad/ava-human-lora-v4` | `9c823580cf7ddf74f1335257d6925db51e64758d33e4181963c09c830ef349a1` |

## 训练数据与发布

公开训练集：[MigoXV/vad-human-ava-speech-training](https://huggingface.co/datasets/MigoXV/vad-human-ava-speech-training)。固定提交 `849203aa634ce04d184290ed2b4f4b0fda384292`，平台资产 `asset-bd3d6dfe70ed46a0`。服务端使用 HF_TOKEN 环境变量中的已有令牌完成 MCP 发布，请求和报告不包含令牌。

原始镜像固定为 `MigoXV/vad-human-ava-speech@ee5e35d06a268fe051d3cf8c6672c42c05e60887`。保留全部 160 条录音：158 条 900 秒、2 条 300 秒，16kHz、单声道、PCM16 无损 FLAC；不裁剪、不重采样、不重新粗标注。原 11 个字段和音频字节保持完全一致。仅在训练副本增加 seconds.starts=onset、seconds.durations=offset-onset，以及 recording_id、duration_seconds、speech_seconds、pcm_sha256，形成 17 列。音频和标注直接放在 Parquet。

| 划分 | 录音数 | 时长（小时） | 有效语音（小时） | 非语音（小时） |
|---|---:|---:|---:|---:|
| train | 142 | 35.500000 | 18.670808 | 16.829192 |
| validation | 16 | 4.000000 | 2.027214 | 1.972786 |
| test | 2 | 0.166667 | 0.089531 | 0.077136 |

总计 39 小时 40 分钟，有效语音 20.787553 小时（52.405595%），非语音 18.879114 小时（47.594405%）；按原标签区间并集统计。validation 从原 train 按 sha256(ava-validation-v1:audio.path) 排序取最小 16 条，选择不依赖标签；原 test 两条录音和归属保持不变，三个 split 的 recording_id 不交叉。

训练集全部文件共 2,701,166,372 字节（约 2.701 GB、2.516 GiB），16 个文件，其中 11 个 Parquet 分片。原格式 FLAC 镜像共 2,700,890,085 字节；原 WAV+JSON 为 4,570,636,993 字节。训练转换复用已经压缩好的 FLAC 字节，大小增加来自训练字段、重新分片和可复现说明，未再次做有损压缩。Arrow writer_batch_size=1，Parquet 每片最多 16 条，避免大音频 binary 批次的 2 GB 偏移限制。

逐条验证全部 160 条：原字段相等、FLAC SHA-256 相等、训练 seconds 精确相等、test 归属不变。远端公开版本另以匿名访问核验全部 16 个文件的大小与哈希，并读取 README。数据卡为中文，包含格式、划分、时长、比例、来源、边界、使用方式和转换源码；LICENSE、provenance.json 与 tools/prepare_ava.py 同步上传。

## 最短固定操作与环境

首次准备之后，智能体只需指定就绪 WorkItem、task、operation、输入 asset_id、配方精确版本与 resources，调用 start_run；随后轮询 get_job 取得 run_id，再轮询 get_run 并核验指标、产物。这是一个提交写操作和两种查询操作，查询次数由实际运行耗时决定。需要先审查时仍可 prepare_run_plan → READY → submit_run。

start_run 内部复用已有检查与封存流程，保存不可变 Plan、代码快照、依赖镜像、原生解析配置和输入身份。检查失败不创建 Run。相同 request_id 和参数返回同一持久 Job；已结束工作仍允许查询与重放原请求，但不允许新增训练。流式文件上传重放也返回同一资产，并校验当前客户端内容是否与封存文件一致。

已发布环境名 `preludio2-ava-human-v2`，版本 `environment_revision-e39a1784375148e3`，框架 `preludio2:ninna-v2`。通过 list_environments(query="preludio2-ava-human-v2", published_only=true) 找到它，再创建新 WorkItem 即可。数据、模型和配方与环境独立，复用训练数据无需再转换。

该环境从已经封存的 LoRA 导出 Plan 镜像和代码创建，只新增框架清单版本，随后由平台发布并在真实 Docker 检查依赖：Torch 2.8.0+cu128、Lightning 2.6.5、Transformers 5.4.0、datasets 4.8.4。已经完成的训练与导出属于原 ninna-v1 工作快照；三次独立测试与推理使用新 ninna-v2 工作快照，两边共享同项目资产。未修改旧版本或历史运行。

配方位于 [examples/vad-human](../examples/vad-human/README.md)：原生 LightningCLI class_path/init_args；固定随机种子 42、阈值 0.5、单卡 FP32、全量数据、不启用 fast_dev_run、augmentation.enabled=false。Full lr=1e-4，Scratch/LoRA lr=3e-4；LoRA r=8、alpha=16、all-linear。测试输入、模型加载和 checkpoint 选择由脚本固定，智能体无需发明字段或加载方法。

完整可恢复入口（Ninna 已运行并存在上述发布环境）：

```bash
NINNA_INTEGRATION=1 poetry run python scripts/run-vad-training-loop.py \
  --api http://127.0.0.1:8021 --framework-source /workspace/opus/preludio2 \
  --evidence outputs/vad-training-loop/state.json --version v5 --publish
```

已有 evidence 恢复现有实验；新实验使用新的 evidence 路径和 version。脚本固定来源 revision、配方和桥接文件哈希，经 MCP 传输文本，Scratch 小型配置经流式上传，不依赖客户端与服务端共享路径。完整验收含 13 次正式操作；导出、成果登记、独立评估和远端发布仍各自有明确身份和结果。

本次重启 API 后建立全新 MCP 会话，再运行同一脚本，13 个成功 Run 身份完全不变，项目仍为 16 个 Run（13 SUCCESS、2 FAILED、1 CANCELLED）。重复上传、重复 start_run、新会话读取和已完成 WorkItem 的恢复均验证通过。两项 WorkItem 已保存摘要并完成。

MCP 资产与环境列表省略逐文件清单并支持名称过滤，详情仍可 inspect；工作恢复默认精简元数据，compact=false 可读取完整上下文。本次环境查询从完整 HTTP 列表 178,838 字节降为指定已发布环境 1,691 字节；两个 WorkItem 上下文分别从 232,380/132,845 降为 41,853/21,547 字节。

## 实际运行与诊断

Project：`vad-human-training-loop`；训练 WorkItem：`work_item-1fd089bedea74221`；独立验收 WorkItem：`work_item-c2ffb816ba3145e4`。使用空闲 GPU UUID `GPU-3985457f-7e5a-7488-e714-7320a54a9b98`，未占用其他正在使用的卡。

| 操作 | Run ID | 结果 |
|---|---|---|
| prepare | `run-87b918a07700410a` | SUCCESS / exit 0 |
| scratch | `run-ebb0b32c05d24ac9` | SUCCESS / exit 0 |
| scratch-export | `run-762670a8a45240de` | SUCCESS / exit 0 |
| full | `run-b1f428037d7a4730` | SUCCESS / exit 0 |
| full-export | `run-7bc59ce204b14ac3` | SUCCESS / exit 0 |
| lora | `run-7a3c70cd1a7c46d4` | SUCCESS / exit 0 |
| lora-export | `run-947e017f1b034cf0` | SUCCESS / exit 0 |
| scratch-test | `run-13062460926c4074` | SUCCESS / exit 0 |
| scratch-infer | `run-08a836d4f0ad41f2` | SUCCESS / exit 0 |
| full-test | `run-259113e9694046ef` | SUCCESS / exit 0 |
| full-infer | `run-00fb24e505004f20` | SUCCESS / exit 0 |
| lora-test | `run-a77fbd3da32546a6` | SUCCESS / exit 0 |
| lora-infer | `run-1f630f0f4e4c4838` | SUCCESS / exit 0 |

保留的诊断和修复：

- run-cd251c90996d4a42：长音频 map 的 Arrow binary 偏移溢出；转换采用单行 writer 与最多 16 条分片。
- run-f88543474ccd464d：DataModule 将内嵌 FLAC 当成已解码 array；共享加载器支持 decode=false 音频字节并保持 PCM 归一化语义。
- run-5c5921bf48144b8c：默认增强关闭缓存、CPU 混响处理变慢，诊断后取消；新配方明确禁用增强并启用缓存，重新创建基线训练。
- job-9f65776a969f4c65：旧 evaluate 清单强制源 checkpoint，独立 HF 权重被阻断，未生成 Run；发布新框架清单 ninna-v2 后完成独立评估。

## 指标解释与验收证据

独立测试使用全部两条原 test 录音，共 10 分钟；配方使用原生 validate，并显式绑定 validation_split=test，因此指标名称保留 val_ 前缀，输入实际为 test。模型以 HF pretrained 方式加载，没有从 checkpoint 恢复或覆盖超参数。所有训练和 checkpoint 选择完成后才进行测试，阈值与 threshold_sweep 始终为 0.5，未根据测试集调参。

原生 Attetion VAD 每 39 帧输出 7 个上下文位置；这里的 F1、Accuracy 是这些有效位置的帧分类指标，没有加入区间平滑、边界容忍或事件级统计。每次重新加载推理取第一条 300 秒 test 录音，输出形状 [769,7,2]、5,383 个有效帧位置；独立 test 则覆盖两条录音。小测试集上的结果证明本次模型与闭环可用，不能替代更广泛的生产评测。

Ninna 全部单元测试 80 项通过；preludio2 针对嵌入音频解码、数据与标注契约、LoRA 冻结约束、checkpoint 导出及非零 adapter 合并前向等价性等 19 项通过。修改文件 Ruff 检查和 git diff --check 通过。真实 Docker 闭环单独报告，不以 mock 训练作为其证据。

可提交的结构化证据为 [vad-training-loop-verification.json](vad-training-loop-verification.json)，包含 13 个 Run 的容器身份、执行规格、时间、退出码和指标，数据与模型哈希、逐模式参数审计、环境发布检查、重连结果及历史诊断。完整本地证据位于 outputs/vad-training-loop/：state.json、attempt-v1 至 v4、各 Run 的 evidence.json、parameter_updates.json、metrics.json、resolved.yaml、推理 predictions.json，以及 data/public/parameter/final-mcp 验证记录。大数据、模型与日志不加入 Git。
