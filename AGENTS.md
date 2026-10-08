# Ninna 开发与 Agent 入口

项目说明见中文 README；运行平台的 Agent 通过 MCP 接入，连接方法见 `docs/agent-integration.md`。

- Python 使用 Poetry：`poetry run pytest`、`poetry run ninna ...`。前端使用 `pnpm --dir src/web ...`。
- 修改前阅读入口和调用链。API：`src/ninna/web/app.py`；领域：`domain/schemas.py`；执行：`services/platform.py`；数据：`storage/repository.py`。
- MCP：`agent/server.py`。两种传输共用工具，调用现有 API；不能在 stdio 进程创建第二个 Platform 执行器。
- Run 必须属于 Project；创建和 MCP 查询显式传 project_id，重训保留父运行的项目。指标位于 Run 详情，系统验收仅存在于开发测试。
- Dataset/Model/Recipe 与 Runtime/Workspace 独立。真实训练只在平台创建的 Docker 容器执行。
- 终态 Run 和注册资产版本不可修改；重训创建新 Run。Workspace 修改生成新快照。
- 维护 `agent/guide.md`、Skill、工具描述和资产说明，让 Agent 能找到前提、输入、执行副作用和结果证据。
- 开发仓库只维护当前训练入口与契约，不保留废弃流程或实验专用验收材料。Agent 从 MCP 读取平台资产、框架 Skill 和配方，不依赖客户端检出 Ninna 或训练框架仓库。
- README 使用中文。新版本分批提交并打 annotated tag；不移动已有 tag。
- UI 遵循 MANAS 与苍渊·白垣锁定 Token；默认白垣 `#F8F7F2`，可切换苍渊 `#080A0D`。Figma 按主题分开、按业务合并 Page，相关界面以命名 Section 排列；设计规范与公共组件分别维护，不保留历史 Page。当前目录见 `docs/design/figma-page-order.json`。
- UI 修改应及时同步 Figma 的界面和组件；发布 tag 前更新页面索引、PNG 与打印稿。
- Figma 本地材料只保留当前界面索引、页面目录、统一组件映射和最新双主题打印稿；脚本默认读取当前索引，不保留旧 PDF、已删除节点清单或历史设计说明。
- Figma Section 只作组织，填充与描边均为空；Page 画布背景匹配所属主题的 `bgPrimary`，不要留下默认白色外框。
- 真 Docker 测试需显式 `NINNA_INTEGRATION=1`；禁止用 mock 训练证明端到端通过。
