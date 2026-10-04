# 多框架训练资产协议

## 范围

适配 demo-mnist、arietta、preludio2、notturno2、richiamo、serenata。Ricercare 与三个 meetnote 决策/主训练仓库不在本次修改范围内。框架仓库使用 `feature/ninna-agent-integration`，Ninna 使用 `feature/multi-framework-training`。

实际镜像版本、十类任务的训练/导出/推理 Run，以及验证边界见 [验收记录](framework-verification.md)；机器可读证据见 [framework-verification.json](framework-verification.json)。

## 镜像与宿主机共用入口

每个框架仓库根目录包含 `AGENTS.md`、`.agents/skills/<框架>-training/SKILL.md` 和 `ninna-framework.yaml`。镜像将根目录复制到 `/app` 并设为 WORKDIR，进入容器即可发现 Agent 入口。宿主机在同一仓库目录使用相同说明和原生命令。

依赖位于 `/opt/venv`，代码快照只读挂载到 `/app`，不会遮蔽依赖。模型、数据、缓存不进入镜像。构建使用显式文件白名单，兼容旧 Docker builder：

```bash
poetry run python scripts/build-framework-image.py /workspace/opus/demo-mnist --tag ninna/demo-mnist:ninna-v1
poetry run python scripts/register-framework.py /workspace/opus/demo-mnist --image ninna/demo-mnist:ninna-v1 --api http://127.0.0.1:8011
```

其他框架替换仓库名即可。注册不会覆盖已有版本；源码或契约发生变化后使用新版本。镜像 label 同时记录 Git HEAD 和构建上下文 SHA-256，因此未提交源码不会被误认为等同于 HEAD。

注册到常用平台时显式设置 `--api http://127.0.0.1:8000`、`--version <新版本>`，可用 `--workspace-name <名称>` 区分验证与日常使用的可编辑工作区。同一 API/状态目录只能有一个执行器。

仅修改源码时可增加 `--dependency-image <已构建镜像>`，工具会先逐项核对 Poetry lock、运行依赖与 Dockerfile，且仅允许 pyproject 的根包包含声明变化；依赖不同会拒绝复用。复用镜像固定为 image ID，替换源码后重新安装根包并运行 pip check，避免反复下载和安装相同的 CUDA 依赖。

## 资产与任务

Framework 描述任务、支持的操作、命令参数数组、输入种类、必需产物和指标方向。Image 固定 Docker image ID；Runtime 校验实际镜像依赖并绑定 Framework 版本；Workspace 保存独立代码快照。Recipe 保存原生 LightningCLI YAML 对象，以及 framework/task/operation。文档可供 Agent 阅读，但平台只执行声明的命令参数数组。

`POST /api/v2/frameworks/import` 从未启动的镜像提取说明和源码。注册的 Image、Framework、Workspace 和 Recipe 继续作为高级执行定义保留。日常使用先创建 Environment、准备依赖并发布不可变版本，再从这个版本创建 WorkItem。

旧的 `POST /api/tasks`、`POST /api/tasks/preflight` 和 `POST /api/runs` 已返回 410。新创建流程为：

1. 获取模型和数据的本地资产版本，必要时补充加载信息。
2. `POST /api/v2/run-plans` 指定 `work_item_id`、`task`、`operation`、`inputs`（输入名到资产版本 ID）、`recipe` 和 `resources`。
3. 等待检查完成；READY 的方案已固定代码、依赖镜像、输入和配方。检查不执行训练 CLI，数据语义仍由实际训练验证。
4. `POST /api/v2/runs` 提交 `plan_id` 与稳定 `request_id`，等待 Job 返回 Run ID。同一请求重试不重复创建 Run。

来源产物使用 `source_run_id`、`source_path`，重训使用 `parent_run_id`；项目归属从 WorkItem 获取。完整 Codex 调用入口见 [Agent 接入](agent-integration.md)。`scripts/framework-smoke.py` 已采用以上流程，参数仍可选择既有框架与训练定义。

CPU 使用零 GPU；CUDA 必须显式选取一个 `GPU-...` UUID。`GET /api/resources/gpus` 返回当前显存和利用率，执行前再次拒绝已占用设备。当前是串行单卡执行器，不提供多机调度。宿主机需提供 `nvidia-smi`，Docker 需有 NVIDIA Container Toolkit。

## 配方与挂载

框架原生 CLI 用 `class_path/init_args` 创建训练对象，桥接层只绑定路径、执行资源、日志和证据 Callback。字符串占位符：`{dataset}`、`{model}` 或其他命名输入、`{config}`、`{output}`、`{source}`、`{task}`、`{device}`。

输入只读位于 `/inputs/<名字>`，源 checkpoint 位于 `/source/artifact`，输出和缓存位于 `/output`。训练容器禁用网络；模型与数据须预先注册。框架源码可在独立 Workspace 中改动，新的 Run 固定新的快照。

恢复训练填写 `source:{run_id,path}`；来源必须是同项目、同框架任务的终态运行中已封存产物。恢复必须保持输入身份和 model/data/optimizer/lr_scheduler/seed 配置。允许新配方延长步数，实际 Lightning checkpoint 恢复优化器等状态。导出与评估也校验底座身份，不能静默替换 LoRA 底座。

## 结果与判定

容器输出 `result.json`，包含 protocol_version、operation、metrics、artifacts（相对路径、kind、sha256）、evidence、quality。训练成功要求真实优化步数大于零、初始与最终可训练参数 SHA-256 不同，并满足框架声明的必需产物。resolved.yaml 保存实际 CLI 解析结果，checkpoint 保留框架及输入身份。

执行成功与模型质量分开记录。短跑能证明真实参数更新，不能证明模型可上线。质量默认为 not_evaluated；任务可提供独立的质量判定。指标名称由任务决定，不强制分类准确率。所有终态 Run 保持不可修改；嵌套产物可下载。

`promote_model` 或 `promote_dataset` 将成功操作的已封存导出目录注册为新资产，校验全部文件且保留来源 Run/Framework/输入身份。训练 checkpoint 不是可直接交付的 HF 模型，先 export，再晋升，再 infer 验证重载。

## 验证与状态隔离

验收状态位于 `outputs/framework-integration/platform`，构建及测试日志位于 `outputs/framework-integration/`。`NINNA_STATE` 可指定独立状态目录；仍只运行一个执行器，不在 stdio MCP 中创建第二个 Platform。

代码声明、镜像构建、依赖校验、真实训练、导出和重载推理分别记录验证状态。默认单元测试不作为 Docker 端到端证据；真实运行记录以容器 ID、退出码、指标、参数 hash 与封存产物为准。示例训练配方是短跑配置，实际训练需注册合适的新配方。
