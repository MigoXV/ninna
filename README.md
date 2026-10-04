# Ninna · 在 Codex 中完成模型训练

Ninna 提供多来源模型与数据、可复用训练环境、独立工作区和真实 Docker 执行。用户在 Codex 中表达：**用什么数据，训练什么模型，怎么训练**。Codex 调用 Ninna 完成准备、训练、诊断与迭代；网页展示相同的资产、工作进度、指标和成果。

## 产品结构

| 对象 | 作用 |
|---|---|
| 项目 | 组织工作任务、运行记录和成果 |
| 托管平台 | 同时连接 Hugging Face 和多个 HF 兼容内网站点 |
| 模型与数据 | 固定来源版本、本地文件及校验状态 |
| 环境版本 | 已准备并验证的依赖镜像和初始代码快照 |
| 工作任务 | 用户目标、约束、独立可编辑工作区、进度摘要和下一步 |
| Run | 一次准备、训练、评估、导出或推理的不可变执行记录 |
| Job | 下载、环境准备、远端命令和运行提交等后台操作 |

环境发布后可用于多个工作任务；每个任务拥有独立状态。一次训练结束不删除工作区。正式 Run 固定输入、代码和实际依赖镜像，在独立离线容器中执行，避免后续编辑改变已提交训练。

下载与训练适配分开：没有 `ninna-asset.json` 的外部仓库也能下载；“已下载”只表示文件在 Ninna 机器上，是否适合训练由具体方案检查。

## 启动

需要 Linux Docker Engine、Docker CLI 和网络。平台为单机可信部署，使用 SQLite 和一个训练执行器；不包含多租户或多机调度。

```bash
git clone https://github.com/MigoXV/ninna.git
cd ninna
./scripts/install-compose.sh
./scripts/platform.sh up
```

打开 `http://localhost:8000`。部署脚本保留现有 MNIST 初始化；首次升级后建立 v2 索引并发布所需环境：

```bash
poetry run ninna migrate
poetry run ninna migrate --apply
```

网页“Codex 接入”也提供迁移检查。迁移只增加索引，不改写旧资产和 Run。环境草稿必须准备、验证并发布，才可用于新工作任务。

## 从 Codex 使用

```bash
codex mcp add ninna --url http://你的平台地址:8000/mcp/
```

安装本仓库 `.agents/skills/ninna`，在 Codex 中使用：

> 使用 $ninna，在客服语音项目中，用内网的数据集微调这个模型。先复用已有环境做小规模验证，报告真实指标与产物。

首次连接读取 `ninna://guide` 和 `get_capabilities`。完整工具分组、stdio 接入和工作流见 [Agent 接入说明](docs/agent-integration.md)。MCP 不要求共享文件系统，也不启动第二个平台执行器。

Ninna 持续执行已提交的工作；Codex 断开后回来，可以凭工作任务 ID 恢复目标、进度和证据。Ninna 不自动唤醒已退出的 Codex，也不托管聊天模型。

## 资产来源与本地文件

在“托管平台”添加多个来源，每个来源有独立名称、地址、启用状态和部署侧凭据变量。公开仓库不需要令牌；私有仓库填写环境变量名，例如 `NINNA_HF_TOKEN`，变量值由部署者设置，不能写进源码或对话。

支持：

- HF 兼容平台：浏览、搜索、固定 commit 下载和显式发布。
- HTTP(S)：指定稳定文件地址下载，以内容摘要标识本地版本。
- Ninna 主机目录：复制、校验后登记资产。
- Codex 机器文件：通过流式上传传输，无需共享目录。

```bash
poetry run ninna upload --path ./dataset --kind dataset --name 我的数据 \
  --request-id upload-dataset-001 --url http://你的平台地址:8000
```

资产有独立的本地状态和训练适配状态。缺少 split 或模型加载描述时，Codex 可以补充元数据、准备数据或调整训练代码。不会强制外部仓库采用 Ninna 专用清单。

模型和数据不进入训练环境镜像。下载先于训练；正式训练关闭网络。训练成果先保存在本地，仅在用户要求时选择目标平台发布。

## 环境和训练

环境草稿从固定镜像及已有代码空间或 Git 代码准备。Codex 可以读写任务文件、安装依赖、执行 CPU 检查，再验证并发布环境版本。发布固定依赖镜像与代码；修改依赖或代码后需要新的执行快照。

准备环境与正式运行分离：

- 准备命令在受管 CPU 容器中执行，有网络，不挂载 Docker socket。新获取的资产通过 `inspect_asset_revision.command_path` 在 `/assets` 下只读访问；历史索引未复制文件时，该字段为空。
- 任务可以停止、重启，保留文件和依赖。
- 每个正式 Run 使用只读输入和代码，输出单独保存，关闭网络。
- GPU 运行显式指定单个 UUID，仍按单机串行执行器调度。
- 终态 Run、已登记资产和已发布环境版本不可覆盖。
- 取消一个 Run 不删除任务工作区；重训创建新 Run 并保留来源关系。

六个框架的任务与原生 LightningCLI 协议见 [框架接入说明](docs/framework-integration.md)。框架 API v1 的旧创建请求已退役，其加载、checkpoint、导出和证据协议继续由 v2 调用。本次训练回归与验证边界见 [工作任务 v2 验收](docs/work-v2-verification.md)；旧版导出、推理等记录保留在 [框架历史证据](docs/framework-verification.md)。

## v2 API

OpenAPI 位于 `/docs`。主要接口族：

| 接口 | 作用 |
|---|---|
| `/api/v2/sources` | 托管平台、连接检查和远端搜索 |
| `/api/v2/assets` | 本地资产、获取、加载描述与发布 |
| `/api/v2/uploads` | 文件流式上传与封存 |
| `/api/v2/environments` | 环境准备、版本发布 |
| `/api/v2/work-items` | 工作目标、上下文与关联运行 |
| `/api/v2/workspaces` | 文件操作、命令执行和启停 |
| `/api/v2/run-plans` | 固定并检查运行方案 |
| `/api/v2/runs` | 幂等提交正式运行 |
| `/api/v2/jobs`、`/api/v2/events` | 后台进度、日志、事件游标 |

工作流写操作使用 `request_id`；重试保持同一 ID 和参数。文件更新使用 SHA-256，工作摘要更新使用版本号。事件等待最长 30 秒，游标持久化。

旧 `POST /api/runs`、`/api/tasks`、`/api/tasks/preflight` 和单一 Hub 的导入、发布返回 410；旧详情、指标、日志与产物链接仍可读取。API、MCP、网页和 Skill 同步切换。

## Docker 挂载路径

容器内运行 Ninna 时，bind mount 必须使用 Docker daemon 主机路径：

```bash
export NINNA_OUTER_CONTAINER=你的外层容器名
./scripts/platform.sh up
```

也可显式指定 `NINNA_HOST_ROOT`。启动脚本通过 `docker inspect` 的最长挂载前缀解析映射，并使用真实只读挂载探针验证共享目录。不要通过创建不存在的宿主机目录掩盖映射错误。

平台容器使用 Docker socket 创建受管容器；任务及训练容器不接触该 socket。远端域名访问需设置准确的 `NINNA_MCP_ALLOWED_HOSTS`。

## 开发与验证

Python 使用 Poetry，前端使用 pnpm：

```bash
poetry install
pnpm --dir src/web install
pnpm --dir src/web run build
poetry run ninna serve
```

后端统一托管 `src/web/dist`；Vite 仅用于前端开发。VS Code 后端调试前执行前端构建。

```bash
poetry run ruff check src/ninna tests
poetry run pytest tests/unit -q
pnpm --dir src/web run lint
pnpm --dir src/web run build
pnpm --dir src/web run test
```

真实 Docker 验收必须显式开启，并使用独立状态目录：

```bash
NINNA_INTEGRATION=1 NINNA_API_URL=http://127.0.0.1:8021 \
  poetry run python scripts/validate-work-v2.py
```

真实容器 ID、退出码、参数更新、指标与产物才构成训练证据，mock 不能证明端到端通过。短跑成功不表示质量达到生产标准。

## 数据与迁移

原运行保存在 `outputs/platform/runs`，新工作状态位于状态目录下的 `work-v2`。SQLite 新增独立工作对象、请求去重和事件表，不改写历史执行 JSON。环境、工作区和 Run 首版不自动删除；磁盘清理由部署者显式处理，不删除仍被历史引用的内容。

升级前停止新提交、等待活动操作结束并备份整个状态目录。回退使用旧程序和升级前备份；保留升级后的独立副本，不让旧程序直接打开新数据库。

## 界面与设计

界面沿用 MANAS 和苍渊·白垣锁定 Token，默认白垣 `#F8F7F2`，可切换苍渊 `#080A0D`。主入口为项目、模型与数据、训练环境、托管平台和 Codex 接入。工程资产详情收在高级环境管理中。

设计同步流程见 [UI 与 Figma 同步](docs/design/sync.md)，版本记录见 [UI 发布记录](docs/ui-releases.md)。页面、组件、两主题 PNG 和打印稿须在发布 tag 前同步完成。

## 五分钟 VAD 数据与 preludio2 验证

[数据契约与操作说明](docs/vad-data-contract.md)固定了 AVA 来源版本、10h/2h 划分、每条严格 300 秒、能量粗标注及 AudioFolder/Parquet 双格式。通过 `poetry run python scripts/prepare-vad.py build` 生成数据；显式 `NINNA_INTEGRATION=1` 后使用 `scripts/run-vad.py` 在现有 Ninna v2 平台运行真实 preludio2 容器，持久保存运行证据。实际结果见 [VAD 验证记录](docs/vad-verification.md)。
