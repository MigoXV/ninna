# 六框架接入验收记录

记录日期：2026-10-03。六个框架、十类任务均已完成真实 Docker 短跑训练、独立导出、晋升 Model 和重载推理。每个训练 Run 都记录了真实优化步数、变化的参数摘要、完整 checkpoint 与解析配置。这里只验收执行与资产链路，不判定模型已经达到生产质量。

## 使用入口

- 主平台：[训练框架目录](http://127.0.0.1:8000/assets/framework)。六套 Framework、Image、Runtime、Workspace、操作配方，以及验证用输入数据、底座和十个导出模型已注册。
- 验证平台：[验收项目](http://127.0.0.1:8011/projects/framework-integration)。状态目录为 `outputs/framework-integration/platform`；主平台继续使用 `outputs/platform`，原有运行未覆盖。
- Agent 使用根目录 `AGENTS.md` 与 MCP 提供的 `ninna://guide`，通过 MCP 发现 Framework、读取框架 Skill、执行 preflight，再创建任务。各框架的镜像默认 WORKDIR 为 `/app`，该目录直接包含 `AGENTS.md`、`.agents/skills/` 和 `ninna-framework.yaml`；宿主机根目录使用同一套说明。
- [协议与构建说明](framework-integration.md)；[机器可读验收证据](framework-verification.json)包含真实容器 ID、image ID、代码快照、输入摘要、配方摘要、参数更新证据和产物摘要。完整日志与产物由对应 Run 保管。

## 已注册的最终镜像

Framework 契约版本均为 `ninna-v1`，与 Image/Runtime/Recipe 版本分别管理。下表版本表示本地已构建、已通过真实容器依赖验证并接入主平台的镜像；没有推送镜像仓库。

| 框架 | Image / Runtime / Recipe 版本 | 主平台 Workspace | 镜像 ID 前缀 | 源码提交 |
|---|---|---|---|---|
| demo-mnist | ninna-v3 | `demo-mnist-main-v3` | `928aa8320d62` | `f17f237` |
| arietta | ninna-v4 | `arietta-main-v4` | `73ccb7294a53` | `e90f123` |
| preludio2 | ninna-v4 | `preludio2-main-v4` | `6ca5a3e47103` | `373d7a7` |
| notturno2 | ninna-v4 | `notturno2-main-v4` | `df83eae64e32` | `61a6b97` |
| richiamo | ninna-v4 | `richiamo-main-v4` | `30b67f3b11a9` | `1ada33c` |
| serenata | ninna-v3 | `serenata-main-v3` | `b7ab1b3b9b18` | `4187e4b` |

镜像标签为 `ninna/<框架>:<版本>`。构建标签同时保存 Git revision 与实际构建上下文 SHA-256；表内源码提交可能包含构建后的纯测试修改，实际镜像身份以 JSON 中的 image ID 和 build_source 为准。验收过程中使用过较早 Runtime 搭配修正后的 Workspace；每个 Run 都封存了自己的真实组合，不能把它们误读为全部使用最终镜像。主平台已用最终 MNIST 镜像独立完成训练。

## 十类任务的真实链路

每行均为成功 Run。训练模式只表示本轮实际运行的代表模式，不表示所有 Scratch / Full / LoRA 组合均经过端到端验收。训练一般仅做 2 个优化步。

| 框架 / 任务 | 实测模式 | 训练 | 导出 | 独立推理 |
|---|---|---|---|---|
| demo-mnist / classification | scratch | [run-301d080c1592](http://127.0.0.1:8011/runs/run-301d080c1592) | [run-2be0ddcfdde3](http://127.0.0.1:8011/runs/run-2be0ddcfdde3) | [run-a6dd4f52c87f](http://127.0.0.1:8011/runs/run-a6dd4f52c87f) |
| arietta / decision | lora | [run-9645b27956e5](http://127.0.0.1:8011/runs/run-9645b27956e5) | [run-9c6663f0f1b7](http://127.0.0.1:8011/runs/run-9c6663f0f1b7) | [run-12a7d612ef36](http://127.0.0.1:8011/runs/run-12a7d612ef36) |
| preludio2 / attetion-vad | scratch | [run-2ee434c00aff](http://127.0.0.1:8011/runs/run-2ee434c00aff) | [run-52df973cd43a](http://127.0.0.1:8011/runs/run-52df973cd43a) | [run-cbd155f792b1](http://127.0.0.1:8011/runs/run-cbd155f792b1) |
| preludio2 / firered-vad | scratch | [run-80b084fb5887](http://127.0.0.1:8011/runs/run-80b084fb5887) | [run-39aad471bb04](http://127.0.0.1:8011/runs/run-39aad471bb04) | [run-60cd352c3206](http://127.0.0.1:8011/runs/run-60cd352c3206) |
| preludio2 / qwen-vad | head | [run-b843d66dd9fd](http://127.0.0.1:8011/runs/run-b843d66dd9fd) | [run-19c0d7f2c6ec](http://127.0.0.1:8011/runs/run-19c0d7f2c6ec) | [run-413a4f9ac467](http://127.0.0.1:8011/runs/run-413a4f9ac467) |
| notturno2 / gtcrn | scratch | [run-13ce1d80fa77](http://127.0.0.1:8011/runs/run-13ce1d80fa77) | [run-4632e5b5a171](http://127.0.0.1:8011/runs/run-4632e5b5a171) | [run-2d8c11ef913a](http://127.0.0.1:8011/runs/run-2d8c11ef913a) |
| notturno2 / mossformer | scratch | [run-ade5546d2300](http://127.0.0.1:8011/runs/run-ade5546d2300) | [run-f4835cd635d4](http://127.0.0.1:8011/runs/run-f4835cd635d4) | [run-f6f97fc13c88](http://127.0.0.1:8011/runs/run-f6f97fc13c88) |
| notturno2 / mossformer-dns | lora | [run-89c10af7cffb](http://127.0.0.1:8011/runs/run-89c10af7cffb) | [run-9e3b81b1bc3a](http://127.0.0.1:8011/runs/run-9e3b81b1bc3a) | [run-97e3fab991b8](http://127.0.0.1:8011/runs/run-97e3fab991b8) |
| richiamo / qwen3-asr | lora | [run-17e33592ab06](http://127.0.0.1:8011/runs/run-17e33592ab06) | [run-8cd73ab56eee](http://127.0.0.1:8011/runs/run-8cd73ab56eee) | [run-6fce34342a6a](http://127.0.0.1:8011/runs/run-6fce34342a6a) |
| serenata / qwen3-tts | lora | [run-d11422e0fd78](http://127.0.0.1:8011/runs/run-d11422e0fd78) | [run-fe927d6eda74](http://127.0.0.1:8011/runs/run-fe927d6eda74) | [run-5fc06a571a26](http://127.0.0.1:8011/runs/run-5fc06a571a26) |

MNIST 的导出链路源于表内首次成功训练；随后另建训练与恢复 Run 验证原生 checkpoint 的恢复语义。语音推理中，ASR 产生文本，TTS 产生 24 kHz、2.48 秒 WAV，GTCRN 产生增强音频；Online MossFormer 和 DNS 当前的接入推理产物是有限值预测张量报告，尚未提供音频重建文件。

## 其他真实验证

- MNIST 原生 ModelCheckpoint 训练：[run-91af94be371d](http://127.0.0.1:8011/runs/run-91af94be371d)。
- MNIST 完整 checkpoint 恢复：global_step 2 → 4，本次真实优化 2 步且参数再次变化：[run-11daf6ef94e1](http://127.0.0.1:8011/runs/run-11daf6ef94e1)。
- MNIST prepare，并晋升为新 Dataset：[run-fc26f2d6350f](http://127.0.0.1:8011/runs/run-fc26f2d6350f)。
- MNIST 独立 checkpoint 评估：[run-ec24329a88d1](http://127.0.0.1:8011/runs/run-ec24329a88d1)。
- TTS 原始 AudioFolder → 原生 codec 编码 → 16/4/4 Parquet、音频与参考音频，并晋升为 Dataset：[run-305a0d5e42c5](http://127.0.0.1:8011/runs/run-305a0d5e42c5)。
- TTS 使用刚晋升的 Dataset 再次完成 LoRA 训练：[run-43c3b3903eb2](http://127.0.0.1:8011/runs/run-43c3b3903eb2)。
- ASR 独立 checkpoint 评估：[run-fe0132953f6b](http://127.0.0.1:8011/runs/run-fe0132953f6b)。
- TTS 独立 checkpoint 评估：[run-c768cd0e53d9](http://127.0.0.1:8011/runs/run-c768cd0e53d9)。
- DNS 独立 checkpoint 评估：[run-7d8ae8ee38d8](http://127.0.0.1:8011/runs/run-7d8ae8ee38d8)。
- Qwen VAD 独立 checkpoint 评估：[run-ac96283c30d1](http://127.0.0.1:8011/runs/run-ac96283c30d1)。
- 主平台以最终 MNIST 镜像、独立 Workspace 和已注册输入完成真实训练：[run-3b86c64904dd](http://127.0.0.1:8000/runs/run-3b86c64904dd)。

恢复时必须同时延长 `max_steps` 和可容纳新增步骤的 `max_epochs`；仅延长步数而仍触及 epoch 上限会被判定为没有真实优化。所有恢复、评估和导出均创建新 Run，保留来源身份。

## 回归与界面验证

| 项目 | 验证结果 |
|---|---|
| Ninna 单元测试 | 57 passed |
| demo-mnist | 14 passed |
| arietta | 50 passed |
| preludio2 | 143 passed |
| notturno2 | 142 passed |
| richiamo | 33 passed |
| serenata | 18 passed |

Python 测试使用对应项目的 `poetry run pytest tests`（Ninna 为 `tests/unit`），不扫描框架忽略目录中的旧工作区。合计 457 项通过，日志保存在 `outputs/framework-integration/`。前端构建通过；Playwright 检查真实资产页面、任务表单、重训预填、任务指标、1440/375 像素布局与 axe 可访问性。训练框架目录、创建任务、运行详情已同步为 Figma 原生可编辑页面，目录包含完整六框架；索引见 `docs/figma-pages.json`。

## 边界与后续使用

- `smoke-v1` 数据和短跑配方用于验证接口与执行链路。数据量很小，不能据此评价识别率、音质或泛化能力；短音频 STOI 等指标不用于质量结论。Run 的质量状态保持 `not_evaluated`。
- 当前平台串行调度 CPU 或显式指定的一张 GPU。本轮 CUDA 仅使用当时空闲的 `GPU-3985457f-7e5a-7488-e714-7320a54a9b98`，没有触碰其他占用设备。多卡、多机、流式服务和生产性能尚未验收。
- prepare 按各框架操作契约执行。MNIST 与 TTS 已分别验证通用数据物化和专用 codec 编码；其他框架的 prepare 配方、全部训练模式以及所有恢复组合未逐一端到端运行。各任务训练时的验证循环均已实际执行。
- 主平台导入的验证产物保留 `validation_api` 与外部验证来源，未伪装为主平台新产生的 Run。生产使用应选择正式数据、底座与新配方版本，重新训练和评估。
- 原有失败 Run 全部保留。已修复的问题包括音频运行依赖、模型远程代码导出、LoRA/原生 checkpoint 导出、恢复步数计算、文本状态序列化、ASR generation 输出、DNS Parquet 输入以及 Docker 传输超时误判。失败摘要见 JSON 的 `preserved_failures`，不能将这些失败记录算作通过。
- Ricercare 与三个 meetnote 决策/主训练仓库排除在本次修改之外。六个框架在 `feature/ninna-agent-integration`，Ninna 在 `feature/multi-framework-training`，改动已按功能分批提交。Arietta 的远程认证未成功，使用已存在的 dev 基线，未声称同步到最新远端。未推送、合并或发布 tag。
