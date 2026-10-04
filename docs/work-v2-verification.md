# 工作任务 v2 验收记录

2026-10-04，分支 `feature/ninna-codex-workspaces`。本次验证使用独立实例 `http://127.0.0.1:8021`，状态目录 `outputs/work-v2-validation/platform`。原平台数据库只用于读取已有注册定义，没有在原状态目录执行迁移。

## 已实现的行为

- 多个独立的 HF 兼容托管平台；HTTP 文件、本地目录和流式上传。资产来源、固定版本、本地可用性与训练适配分别记录。
- 环境草稿准备依赖和代码，发布不可变版本；每个工作任务从基线创建独立工作区。停止、训练失败和会话结束均不会删除工作区。
- Codex 通过 MCP 读写远端文件、执行受管命令、检查日志、生成运行方案和提交真实训练。工作目标、公开进度摘要与执行证据可跨会话恢复。
- 方案固定代码快照、依赖镜像、输入与配方；摘要更新不会误使方案失效。修改文件或执行命令后需要重新检查。相同请求重试不会重复提交。
- 网页围绕“项目 → 工作任务 → 数据、模型、训练方案”组织。旧运行继续可读，旧创建接口返回 410，重训创建带父运行关系的新记录。

## 验证结果

| 检查 | 结果与证据 |
|---|---|
| Python 默认测试 | 69 通过；26 项集成用例默认跳过 |
| 当前 MCP 集成测试 | 1 通过，官方 HTTP 创建与 stdio 重连；真实 Docker，不模拟训练 |
| 浏览器完整回归 | 29 通过；2 项需要私有镜像目录配置的检查显式跳过 |
| 生产构建、类型与静态检查 | pnpm build、TypeScript、Ruff、git diff --check 通过 |
| 六框架训练 | 10 类任务全部 SUCCESS，覆盖 CPU 与单卡 GPU；每次均有实际参数更新和封存产物 |
| 失败修复 | 注入真实训练错误，保留 FAILED Run，修改工作区后新 Run SUCCESS，记录 parent_run_id |
| 准备命令 | 成功、失败、超时、取消；读取新下载资产成功，向只读资产写入返回 EROFS |
| 恢复与隔离 | 工作区停止/重启文件保持；新任务不继承另一任务的私有文件；平台重启后恢复原目标及 3 个运行记录 |
| Hugging Face | 实际下载 `hf-internal-testing/tiny-random-bert`，固定 commit，无 Ninna 专用清单要求 |
| 模型交付 | MNIST 真实导出、晋升进入新资产目录、重新加载推理全部成功 |
| Figma | 9 个新页面、23 个新增组件；一页一个原点主画板，复用锁定变量；双主题 PNG 和打印稿已导出 |

逐次 Run 的容器 ID、退出码、参数 hash、指标和产物数量见 [机器可读证据](work-v2-verification.json)。本地完整日志位于 `outputs/work-v2-validation`。默认测试跳过集成检查不代表集成通过；上表的实际训练与 MCP 结果来自分别显式开启的验收命令。

旧 v1 创建接口的历史集成用例保留并标记 `legacy_api`。只有针对旧版本服务器且设置 `NINNA_LEGACY_API=1` 时才运行。当前创建流程由 `tests/integration/test_work_v2.py` 与框架矩阵脚本验证。

## 复现入口

先注册真实框架与验证资产，在独立状态目录启动平台；脚本不以 mock 补齐缺失资源。既有环境可用 `scripts/validate-work-v2.py --seed` 从原平台只读复制注册定义，并在独立数据库建立索引。容器部署需正确设置 `NINNA_HOST_ROOT`。

```bash
poetry run pytest -q
NINNA_INTEGRATION=1 NINNA_API_URL=http://127.0.0.1:8021 \
  poetry run pytest tests/integration/test_work_v2.py -q
NINNA_INTEGRATION=1 NINNA_API_URL=http://127.0.0.1:8021 \
  NINNA_TEST_GPU=实际空闲GPU的UUID \
  poetry run python scripts/validate-work-frameworks.py
NINNA_INTEGRATION=1 NINNA_WEB_URL=http://127.0.0.1:8021 \
  pnpm --dir src/web test
```

框架矩阵还需已有 `outputs/framework-integration/platform` 中的历史验证定义；脚本只读取它们，在新实例中创建新工作任务与 Run。生产启用方法见 [迁移和 Agent 接入](agent-integration.md)。

## 设计交付

[Figma 工作任务页面](https://www.figma.com/design/ab3EG1a9aEHNyNZRJCzmD4?node-id=189-3959)、[页面索引](figma-work-v2.json)、[组件映射](figma-work-v2-components.json)。旧索引保留历史页面，本次新工作流使用独立索引。

[白垣打印稿](design/work-v2-vallum-review.pdf)、[苍渊打印稿](design/work-v2-abyssus-review.pdf)，各 19 页。逐页 Figma PNG 分别位于 `outputs/work-v2-validation/figma-png` 和 `figma-abyssus`，各 9 张；浏览器双主题截图位于 `outputs/work-v2-validation/ui`。

## 验证边界

本次十类任务矩阵验证了训练；新的完整导出、晋升、重载链路验证了 MNIST，其余框架的历史导出/推理证据仍保留，未宣称重新完成全部交付链路。短跑成功证明执行和参数更新，不代表模型质量达标。

私有托管平台的外部发布未在本次重新执行。首版仍为可信单机部署、串行单卡训练；准备命令使用 CPU，环境与快照不自动清理。Ninna 持续执行已提交工作，不自动唤醒已退出的 Codex，也不托管聊天 Agent。
