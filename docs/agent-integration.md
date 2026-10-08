# 在 Codex 中调用 Ninna

Ninna 是训练执行平台，Codex 是用户交互入口。v2 支持多个资产来源、可复用环境、独立工作区、命令执行、运行方案和工作进度恢复。网页与 MCP 共用领域服务和真实状态；平台不会托管 Codex 对话。

## 连接

先运行 Ninna，再在 Codex 所在机器连接实际可访问的地址：

```bash
codex mcp add ninna --url http://你的平台地址:8000/mcp/
```

本机运行时使用 `http://127.0.0.1:8000/mcp/`。远端部署设置 `NINNA_MCP_ALLOWED_HOSTS` 为对应 host:port。既有可信单机部署边界不变，不将没有额外访问控制的平台直接暴露到公网。

stdio 同样连接已运行的 API，不创建执行器：

```bash
codex mcp add ninna -- poetry --directory /安装路径/ninna run ninna mcp --url http://你的平台地址:8000
```

本仓库不包含 Ninna Skill。MCP 地址以实际客户端配置为准；连接后读取 `ninna://guide` 和 `get_capabilities`。

客户端无需检出 Ninna 或训练框架仓库。框架任务、操作、输入与 Skill 从 `list_assets(kind="framework")` / `describe_asset` 读取；模型、数据和 Recipe 使用平台上的精确版本。已发布 Environment 保存依赖与初始代码，WorkItem 保存远端工作区，客户端通过 MCP 完成发现、编辑、提交和恢复。

## 用户示例

> 通过 Ninna MCP，在我的语音项目中，用内网数据集微调这个模型，先做一次小规模验证。复用已准备的环境，报告实际指标和模型产物。

> 继续工作任务 work_item-…，看看上次训练的结果，诊断问题并创建新的训练尝试。

首次读取 `ninna://guide` 和 `get_capabilities`。工具 schema 是参数真源，不依赖固定工具数量。

## 能力分组

| 目的 | 主要工具 |
|---|---|
| 多来源 | list_sources、configure_source、check_source、search_source_assets |
| 本地资产 | list_asset_revisions、inspect_asset_revision、acquire_asset、bind_asset |
| 环境 | list_environments、create_environment、prepare_environment、publish_environment |
| 工作上下文 | list_work_items、create_work_item、get_work_context、update_work_item |
| 工作区 | read_task_files、edit_task_file、execute_task_command、set_workspace_state |
| 执行 | start_run（固定配方一次检查并提交）、prepare_run_plan、read_run_plan、submit_run、get_run、cancel_run |
| 后台操作 | list_jobs、get_job、read_job_logs、cancel_job、wait_for_events |
| 证据与成果 | get_run_metrics、get_run_diagnostic_context、list_run_artifacts、promote_model、promote_dataset、publish_asset_revision |

镜像、框架与配方的精确声明仍通过 list_assets / describe_asset / register_asset 管理。普通用户无需逐次手工组合 Image、Runtime 和 Workspace。

已有固定配方和就绪 WorkItem 时，最短执行序列是 `start_run` → `get_job` 获得 run_id → `get_run` 等待终态并核对证据。start_run 保留与手动方案完全相同的快照、输入校验和不可变 Run，检查失败不会提交训练；同请求重试返回同一个 Job。下载、成果发布仍为显式操作。

## 不共享文件系统

发现数据时先调用 `list_asset_revisions(kind="dataset")` 查看已有副本，再用 `list_sources` 找到 HF 兼容来源，逐个调用 `search_source_assets(source_id, kind="dataset", query, offset, limit)`，跟随 `next_offset` 读取分页。数据搜索必须显式指定 kind；工具默认搜索 model。搜索结果不证明数据可训练，需核对数据卡、字段、标签质量、划分、许可与框架加载契约。其他网站的公开资源可先查询官方说明，再用稳定 HTTP(S) 文件地址导入。

Codex 通过 MCP 编辑任务工作区并执行命令。传入的 local_path 指 **Ninna 主机** 路径；若文件在 Codex 机器上，使用 CLI：

```bash
poetry run ninna upload --path ./my-dataset --kind dataset --name 客服录音 \
  --request-id upload-callcenter-001 --url http://你的平台地址:8000
```

文件通过 PUT `/api/v2/uploads/{id}/files` 流式传输并验证 SHA-256，完成后登记本地资产。重试复用 request-id，不经过模型文本上下文。

## 长时间训练

提交返回 Job，成功结果中包含 run_id；必须继续检查 Run 到终态。HTTP 或 MCP 会话结束不取消训练。事件接口使用持久游标，最多等待 30 秒；重新连接从原游标继续。平台不会自动唤醒退出的 Codex。

工作流写操作的 request_id 是幂等身份：相同参数复用相同 ID，参数改变使用新 ID。文件编辑使用 expected_sha256，工作任务摘要更新使用 expected_version，冲突后重新读取。

正式训练使用固定的代码和依赖快照，关闭网络；准备命令默认在有网络的 CPU 工作区运行。GPU 训练必须明确 UUID，并由现有串行执行器检查设备可用性。

## 迁移

停止新提交并等待原运行结束，备份状态目录后：

```bash
poetry run ninna migrate --url http://平台地址:8000
poetry run ninna migrate --apply --url http://平台地址:8000
```

迁移只新增索引：原单一 Hub 变为一个来源，原模型和数据成为可查询资产，Runtime/Workspace 组合成为待验证环境草稿。原资产和历史 Run 不改写。发布草稿后再创建新工作。

旧 POST `/api/runs`、`/api/tasks`、`/api/tasks/preflight`、`/api/hub/import`、`/api/hub/publish` 返回 410。旧详情、日志与产物链接继续只读可用。旧 create_run/create_task 等创建工具不再出现在 MCP 目录。

## 验证

```bash
poetry run pytest tests/unit -q
NINNA_INTEGRATION=1 poetry run python scripts/validate-work-v2.py
```

真实验收脚本使用独立运行平台，默认 `http://127.0.0.1:8021`。它通过官方 MCP 客户端准备环境、修改远端文件、执行真实 CPU 训练、验证重复提交和工作区停止恢复，并通过新 MCP 会话读取同一上下文。只有实际产生的容器、指标和产物才作为训练证据。

本次实际验收、历史测试的运行方式与验证边界见 [工作任务 v2 验收记录](work-v2-verification.md)。

MCP 列表支持按 query 筛选资产和环境；选择环境建议 `list_environments(query="preludio2", published_only=true)`。列表省略文件哈希，详情通过 inspect_asset_revision 查询。get_work_context 默认省略执行快照源码清单和 Run 的大块 metadata；需要原始详情时传 compact=false，或按保存的 Run/Plan/Job ID 精确查询。网页和 HTTP API 保留完整信息。

客户端 `ninna upload` 的首次成功与重试都返回同一 Asset 结构；已封存上传与当前本地文件不一致时拒绝复用 request-id，避免 Agent 将旧数据误当新数据。
