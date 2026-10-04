# VAD 数据准备与真实运行约定

本约定用于 `scripts/prepare-vad.py` 与 `scripts/run-vad.py`，将下载、格式、划分、粗标注和验收固定为可重复操作，避免 Agent 临时拼接规则。

## 来源与版本

本次选用 [AVA-Speech 的 WhisperSeg 音频整理版](https://huggingface.co/datasets/nccratliri/vad-human-ava-speech)，固定 commit `fefdf18c196e4b3de0c2cf84652e3983efb8530d`。原始任务说明见 [Google AVA 下载页](https://sites.research.google/gr/ava/download/)。它含电影语音、背景音乐和噪声；相比只含朗读的音频，更适合检查活动检测流程。另一个可选来源是 [MUSAN](https://www.openslr.org/17/)，本次未混入。

`examples/vad/source-lock.json` 固定 40 个 15 分钟录音及目标 split。选择方式是对上游 train WAV 路径计算 `SHA256("42:" + path)`，排序取前 40 个，前 32/接着 4/最后 4 个分别进入 train/validation/test。这是本地实验划分，不是官方 AVA benchmark 划分。按原始录音隔离，不能宣称跨影片说话人身份也已隔离。

只下载 WAV 和来源 README，不使用上游人工区间作为本轮标签。原始文件留在 `original/`；清单记录来源 commit 和每个文件 SHA-256。上游卡片声明 Apache-2.0，原始影片权利归属另行保留，不由整理版数据卡推断影片再授权。

## 固定音频与划分

每条输出必须是真实裁剪的 **300 秒**，16,000 Hz、单声道、16-bit PCM WAV，即 **4,800,000 个采样点**。不补零凑时长，不重复音频凑总量，不重采样未知输入；源格式或时长不符合时直接失败。

| 版本 | train | validation | test | 总量 |
|---|---:|---:|---:|---:|
| 10h | 96 条 / 8 小时 | 12 条 / 1 小时 | 12 条 / 1 小时 | 120 条 / 10 小时 |
| 2h | 20 条 / 100 分钟 | 2 条 / 10 分钟 | 2 条 / 10 分钟 | 24 条 / 2 小时 |

每个 15 分钟源录音裁为三个相邻的 5 分钟片段。2h 选择锁定顺序中前 20 个训练源、前 2 个验证源、前 2 个测试源的中间片段（源内 300–600 秒）。2h 是 10h 的严格子集：音频字节、ID、区间和 split 均不变。24 条不能精确按 80/10/10 整数划分，因此固定采用 20/2/2，不由 Agent 四舍五入决定。

## 粗标注

固定 `energy-v1`：20 ms RMS 窗、10 ms hop、阈值 −35 dBFS，先合并不超过 150 ms 的间隔，再去除不足 100 ms 的活动，最后前后各扩 50 ms，裁剪到音频边界并合并重叠。

这是能量活动粗标注。音乐、噪声可能成为假阳性，低音量语音可能漏检。所有行必须保留 `annotation_method=energy-v1`、`annotation_status=unreviewed`。训练、验证和测试均是粗标签，指标只证明与粗标注的一致性，不能用作真实 VAD 质量结论。人工修标另建版本，不能修改已注册资产。

## 两种等价存储

AudioFolder：`train/`、`validation/`、`test/` 各自包含 `audio/*.wav` 和 `metadata.jsonl`。

```json
{"file_name":"audio/example.wav","id":"example","seconds":{"starts":[0.25],"durations":[0.5]},"source_id":"original-recording","source_offset_seconds":300,"audio_sha256":"...","annotation_method":"energy-v1","annotation_status":"unreviewed"}
```

`seconds` 单位秒，采用左闭右开区间；两个数组等长、有限、升序、不重叠、不越界，持续时间严格大于零。无活动用两个空数组。`file_name` 相对当前 split，不写宿主机绝对路径。

Parquet 单独输出 `10h-parquet/` 和 `2h-parquet/`，各有三个 split 文件。`audio` 使用标准 Hugging Face Audio struct：`bytes` 内嵌 WAV，`path` 为相对标识，文件移动后仍能解码。其余字段保持一致，Arrow schema 明确声明浮点区间列表，避免空列表推断成 null。每行写入后核对音频 SHA-256 和区间。训练统一经 `datasets.load_dataset(目录, split=...)` 加载。

## 复现与验收

```bash
# 数据转换工具的额外依赖；训练依赖由已发布 preludio2 镜像提供。
poetry run pip install 'pyarrow>=17,<22'
poetry run python scripts/prepare-vad.py build
poetry run python scripts/prepare-vad.py check data-bin/vad-ava-energy-v1/10h
poetry run python scripts/prepare-vad.py check data-bin/vad-ava-energy-v1/2h
NINNA_INTEGRATION=1 poetry run python scripts/run-vad.py --api http://127.0.0.1:8021
```

构建拒绝覆盖已有数据版本。换数据、标签或规则必须选择新版本目录并更新锁定配置。运行脚本保存固定请求身份及 `outputs/vad-ava-energy-v1/evidence.json`，中断后原命令恢复；新实验使用新的 `--request-prefix` 和 `--evidence`，不能拿旧请求 ID 改参数重提。恢复时校验 API、数据目录与配方摘要；不一致直接拒绝。

运行前读取 `ninna://guide` 和 `get_capabilities`。本次 8021 是已经运行的 v2 平台，8000/8011 仍提供旧 API。连接成功不等于版本兼容；能力探测失败应报告具体接口，不调用退役的 create_task，也不启动第二个执行器。

运行复用 `preludio2-main-v4` 的已发布环境，执行 `attetion-vad`。原生配置固定在 `examples/vad/train.yaml` 和 `evaluate-test.yaml`，前者一轮完整训练 split、完整 validation，无 max_samples 截断、无 fast_dev_run；后者恢复该 checkpoint，在 test split 上评估固定阈值，不扫阈值。框架的 evaluate 调用 Lightning `validate`，因此配方显式将 `validation_split` 指向 `test`，日志里的 `val_*` 在这个独立 Run 中表示 test 结果。

必须核对：容器 ID、退出码、真实优化步数、参数更新、resolved config、checkpoint、数据总量及独立测试结果。准备阶段需在受管 CPU 容器实际执行两种格式的 `datasets.load_dataset` 和音频解码。只有 Job 成功不能报告训练成功；必须等 Run 终态。每个失败 Run 保留，修复后创建新方案及新 Run。

本次实际发现：评估 invocation 配置为 `[0.5]`，但 resolved 配置仍为训练时的 0.1–0.9；原因是 Lightning 从 checkpoint 恢复模型超参数，并非空列表导致默认扫描。最终训练与评估配方都锁定为 `[0.5]`，分别注册为 `vad-ava-energy-train:v2` 和 `vad-ava-energy-evaluate:v2`，重新训练产生一致的 checkpoint。前两次诊断评估保留，只引用后续配置一致的 Run 作为最终测试证据；不根据 test 指标选择阈值。
