# MCP 与 Agent Skill

Ninna 提供官方 MCP Python SDK 实现的 **Streamable HTTP** 和 **stdio**，共用 21 个工具、平台指南资源、资产资源模板及失败诊断 prompt。接口直接使用当前领域模型。

## 接入 Codex

先运行平台，再连接 HTTP MCP：

```bash
./scripts/platform.sh up
codex mcp add ninna --url http://127.0.0.1:8000/mcp/
```

本仓库的 `.agents/skills/ninna/` 提供 `$ninna`。重新打开仓库会话后可以使用：

```text
使用 $ninna，选择已注册的 MNIST HF 资产做一次快速训练。
先选择或创建 Project，创建训练时显式传 project_id。等待完成，报告容器 ID、准确率、模型 hash 变化和 checkpoint 下载地址。
```

在其他仓库使用时，将整个 `.agents/skills/ninna` 目录复制到目标仓库的 `.agents/skills/`，或放入个人 Skill 目录。Skill 的 `agents/openai.yaml` 声明本机 MCP 依赖；远程部署时同步修改其中的地址。

也可以通过 stdio 接入（平台需已运行）：

```bash
poetry install
codex mcp add ninna -- poetry --directory /绝对路径/ninna run ninna mcp --url http://127.0.0.1:8000
```

二选一即可。stdio 只连接 API，不启动训练 worker；Agent 退出后训练仍由平台继续执行。协议 stdout 只用于 JSON-RPC，日志写 stderr。

## 其他 Agent

使用客户端支持的 Streamable HTTP 配置，URL 为 `http://127.0.0.1:8000/mcp/`。通用 stdio 配置示例（不同客户端配置文件位置不同）：

```json
{
  "mcpServers": {
    "ninna": {
      "command": "poetry",
      "args": ["--directory", "/绝对路径/ninna", "run", "ninna", "mcp"],
      "env": {"NINNA_API_URL": "http://127.0.0.1:8000"}
    }
  }
}
```

Skill 内容为普通 Markdown，其他 Agent 可将其作为平台操作指南读取。连接后先 `resources/read ninna://guide`，再 `tools/list` 获取当前参数 schema。所有工具返回结构化 JSON；业务失败使用 MCP `isError`，不能把错误文本当成功结果。

HTTP 默认允许 localhost/127.0.0.1/IPv6 loopback。使用远端域名时，设置准确的 Host 白名单，例如 `NINNA_MCP_ALLOWED_HOSTS=training.example.internal:8000` 后重新启动平台。平台与 MCP 当前均面向可信单机环境，没有另加认证系统。

## 能力和副作用

| 工作 | 工具 | 行为 |
| --- | --- | --- |
| 发现 | platform_health、list_assets、describe_asset | 只读；资产列表分页，详情含说明与 README |
| 准备 | read_workspace、snapshot_workspace、register_asset | 读取代码；创建快照；注册新版本 |
| 执行 | create_run、list_runs、get_run、cancel_run | 创建真实训练；观察；显式取消 |
| 证据 | read_run_logs、get_run_metrics、get_run_diagnostic_context、list_run_artifacts | 只读；日志分段/诊断截断；模型使用下载路径 |
| 复用 | promote_model | 从成功 Run 创建新模型版本 |
| 项目 | list_projects、create_project | 选择或创建组织上下文；create_run / list_runs 必须传 project_id |
| 中心存储 | list_hub_repositories、publish_asset、import_asset、list_hub_transfers | 发现；远端发布；导入新版本；观察传输 |

`ninna://assets/{kind}/{name}/{version}` 提供资产详情资源。`diagnose_run` prompt 引导基于日志、容器状态和实际快照诊断。训练不会由于 MCP 会话结束而取消。

## 一次训练的定义

先发现当前资产，下例仅说明已初始化 MNIST 的组合方式：

```json
{
  "project_id": "mnist",
  "training_spec": {
    "dataset": {"name": "mnist", "version": "v2"},
    "model": {"name": "mnist-cnn", "version": "v2"},
    "recipe": {"name": "mnist-adam", "version": "quick-v1"}
  },
  "execution_spec": {
    "runtime": {"name": "mnist-pytorch-runtime", "version": "v3"},
    "workspace": {"name": "mnist-hf", "snapshot": "current"},
    "resources": {"device": "cpu", "gpu_count": 0, "cpu_threads": 4, "memory_mb": 4096}
  }
}
```

create_run 返回创建记录。保存 `id`，轮询至终态后核对容器、退出码、指标、hash 与产物。每次 create_run 都产生新 Run，提交超时时先查询近期记录，不盲目重试。修复失败时传 `parent_run_id` 关联原记录。

## 仓库说明与资产卡片

`GET /api/assets/{kind}/{name}/{version}` 和 describe_asset 返回完整资产、生成的加载/版本/来源说明，以及资产已有的 README（上限 100,000 字节）。文档作为数据读取，不执行其中代码。

发布到 HF 兼容仓库时，若资产没有 README，平台在发布暂存区生成中文 README，说明格式、加载入口、元数据和校验关系。已有 README 原样保留。生成的说明位于资产 payload 之外，不改变已注册资产的清单或 checksum；导入只取 `ninna-asset.json` 中声明的文件。已有远端仓库不会因升级自动改写，下次显式发布时才应用。

仓库层面由 `AGENTS.md` 说明代码入口和工程约定；平台层面由 MCP `ninna://guide` 说明工作流；资产层面由 describe_asset / README 说明训练输入。这三处随功能一起维护。

## 开发与验证

```bash
poetry run pytest tests/unit -q
NINNA_INTEGRATION=1 poetry run pytest tests/integration/test_mcp.py -q -s
```

集成测试使用官方 MCP 客户端：HTTP 创建 Run，断开创建者后通过独立 stdio 进程观察真实 Docker 训练；验证只读挂载、模型 hash、loss、准确率和 checkpoint 下载。第二条链路注册非法 Recipe，验证失败诊断，再创建带 parent_run_id 的成功 Run，确认历史失败记录不变。测试会增加真实 Run 和 Recipe 版本。

服务代码：`src/ninna/agent/server.py`。HTTP 子应用由 FastAPI 主 lifespan 启动 MCP session manager，内部以 ASGI 调用同一 API；stdio 通过 HTTP 连接运行平台。单一平台 worker 始终持有任务生命周期。

## agent-v0.1.0 验证记录

2026-09-25，分支 `feature/mcp-agent-skill`，生产镜像 `ea92ce05ba64` 健康运行。分三批提交工具实现、Skill/说明、验证测试，并使用 annotated tag `agent-v0.1.0` 标记本次版本。

- 单元测试：22 项通过；包括 MCP 协议、资源、结构化结果、参数校验、错误、文档边界及发布说明不改写资产清单。
- 真实 MCP 集成：2 项通过，65.62 秒。没有 mock Docker 训练。
- HTTP 创建 → stdio 观察：`run-4b1e02fe8b09` SUCCESS，准确率 98.21%；Docker ID `e1df95fcc9f43904e09c5765f10e62bf43c3609d1a507149f795ffe867dc72ce`。
- 非法学习率：`run-df17145d34ef` FAILED，保留退出码和 stderr；修复后新建 `run-b196f3593b05` SUCCESS，parent_run_id 指向失败 Run，旧记录保持不变。
- Ruff、Skill frontmatter 校验通过；构建 wheel 后确认平台指南随包交付。

Hub 发布说明的文件清单不变性使用暂存区测试验证；本轮没有重新发布远端模型仓库。UI 已先 squash 到 `dev` 并标记 `ui-v0.2.1`，MCP 工作保留在独立功能分支。
