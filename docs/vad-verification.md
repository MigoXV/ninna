# VAD 数据与 preludio2 实际验证

验证日期：2026-10-04。平台：`http://127.0.0.1:8021`，项目 `vad-ava-energy`。

全部音频严格裁剪为 300 秒，16 kHz 单声道 PCM16。10h 的 train/validation/test 为 96/12/12 条；2h 为 20/2/2 条，是前者的严格子集。两者均有独立 AudioFolder 和内嵌 WAV Parquet 副本。来源、能量粗标注、版本和复现命令见 [数据契约](vad-data-contract.md)。

| 操作 | Run | 退出码 | 优化步 | 耗时 |
|---|---|---:|---:|---:|
| audiofolder-train-locked | [run-b391c5a4a1244429](http://127.0.0.1:8021/runs/run-b391c5a4a1244429) | 0 | 20 | 34.0s |
| parquet-train-locked | [run-cee5eb4d3118447c](http://127.0.0.1:8021/runs/run-cee5eb4d3118447c) | 0 | 20 | 34.6s |
| test-evaluate-final | [run-efef5bd0628d4c8e](http://127.0.0.1:8021/runs/run-efef5bd0628d4c8e) | 0 | — | 11.4s |

两种格式各完整训练一轮 train split，并使用完整 validation split；均为 20 个优化步骤，最终可训练参数哈希完全一致。容器内通过 datasets.load_dataset 加载了两种格式的三个 split，并实际解码确认 4,800,000 个采样点。两个训练 Run 均有 resolved.yaml、checkpoint 和参数更新证据。

最终独立评估读取 Parquet test 的 2 条音频（10 分钟），恢复 Parquet 训练 checkpoint，resolved 配置确认 validation_split=test、threshold=0.5、threshold_sweep=[0.5]。

测试粗标签上的 loss=0.549743，F1=0.834155，recall=1.0，predicted_positive_ratio=1.0。模型把所有评测帧判为活动，不能把该 F1 解释为模型已达标。本次验收结论是数据格式和运行流程通过；标签仍待人工修订，模型质量未验收。

实际消除或记录的操作障碍：

- 8000/8011 仍是旧 API；运行前通过 get_capabilities 选择已运行的 8021 v2 平台。
- Lightning 会从 checkpoint 恢复模型超参数，单独修改评估 YAML 不保证生效；最初两次诊断评估仍保留训练时阈值扫描。最终训练与评估配方均锁定 [0.5]，脚本下载并断言 resolved 配置。诊断 Run 保留，未用于选择测试阈值。
- WorkItem 完成后不能继续提交方案；补跑前通过 expected_version 显式恢复 ACTIVE，终态 Run 不变。
- Python 3.10 默认异常输出会掩盖 MCP 异常组的具体原因；运行脚本展开叶子错误，保留请求身份，避免 Agent 猜测或盲目重提。

沉淀：固定来源锁、构建和校验脚本、训练与评估配方、MCP 可恢复脚本、Agent Guide/Skill，以及 6 项数据规则测试。检查命令：`poetry run pytest tests/unit/test_vad_preparation.py -q`、`poetry run ruff check scripts/prepare-vad.py scripts/run-vad.py tests/unit/test_vad_preparation.py`。

紧凑证据：[vad-verification.json](vad-verification.json)。完整平台响应及工作上下文：`outputs/vad-ava-energy-v1/evidence.json`。数据清单：`data-bin/vad-ava-energy-v1/manifest.json`。
