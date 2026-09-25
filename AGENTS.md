# Ninna 开发与 Agent 入口

项目说明见中文 README；运行平台的 Agent 使用 `.agents/skills/ninna/SKILL.md`，连接方法见 `docs/agent-integration.md`。

- Python 使用 Poetry：`poetry run pytest`、`poetry run ninna ...`。前端使用 `pnpm --dir src/web ...`。
- 修改前阅读入口和调用链。API：`src/ninna/web/app.py`；领域：`domain/schemas.py`；执行：`services/platform.py`；数据：`storage/repository.py`。
- MCP：`agent/server.py`。两种传输共用工具，调用现有 API；不能在 stdio 进程创建第二个 Platform 执行器。
- Dataset/Model/Recipe 与 Runtime/Workspace 独立。真实训练只在平台创建的 Docker 容器执行。
- 终态 Run 和注册资产版本不可修改；重训创建新 Run。Workspace 修改生成新快照。
- 维护 `agent/guide.md`、Skill、工具描述和资产说明，让 Agent 能找到前提、输入、执行副作用和结果证据。
- README 使用中文。新版本分批提交并打 annotated tag；不移动已有 tag。
- UI 遵循 MANAS，画布 `#FFFEFB`。Figma 一界面一 Page，规范、组件分开，Page 内仅一个原点主画板。
- UI 修改应及时同步 Figma 的界面和组件；发布 tag 前更新页面索引、PNG 与打印稿。
- 真 Docker 测试需显式 `NINNA_INTEGRATION=1`；禁止用 mock 训练证明端到端通过。
