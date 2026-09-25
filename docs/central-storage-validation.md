# 中心存储与实验观察验收

2026-09-25，开发分支 `feature/kohakuhub-aim`。本轮使用真实 KohakuHub、Docker CPU 训练容器和 Aim SDK，未 mock 训练或远端文件操作。

## 部署与边界

- Ninna：Compose 服务 `ninna-platform-1`，本机 `http://127.0.0.1:8000`。
- KohakuHub：`http://192.168.0.222:28080`，专用账号/命名空间 `ninna-platform`；测试仓库为私有仓库。
- 训练 Runtime：`mnist-pytorch-runtime/v3`，实际镜像 ID `sha256:99fd1b34cc50af3273a6f830adda128162538f32fb6e6d3cf30b20f5a0a3c47d`。
- Aim 3.29.1：只使用 SDK 和本地存储，曲线由 Ninna React 页面绘制；不运行 Aim UI 服务。
- Hub 为可选集成，初始关闭；部署实例已配置。自动导入只接受包含 `ninna-asset.json` 的 HF 资产仓库，其他仓库可浏览，但不猜测其模型架构或数据 split。
- 访问令牌只存于忽略提交的后端配置中，API 不回显；测试及本文件均不包含凭据。

## 完整训练验收

`./scripts/mnist-certify.sh` 返回 **OVERALL PASS**，退出码 0。

| 项目 | 实际结果 |
| --- | --- |
| Certification | `cert-fd834f99c42a` |
| Adam Run | `run-9eac0c09bd14`，3 epochs，98.94% |
| SGD Run | `run-7de206c8bb84`，5 epochs，98.70% |
| Recipe 解耦 | Dataset、Model、Runtime、Workspace snapshot 相同，只替换 Recipe |
| 容器与挂载 | 真实容器 ID、只读 Dataset / Model / Workspace 和可写输出目录，检查通过 |
| 模型更新 | 两个 Run 的初始/训练后 hash 不同，loss 下降 |
| 模型加载 | 独立 Docker 验证容器重载 checkpoint 和 HF AutoModel，hash / logits 对齐 |

报告位于 `outputs/platform/certifications/`，Run 文件与日志位于 `outputs/platform/runs/`。大文件和本机运行证据不提交 Git，新部署需重新执行验收。

## 自动化回归

- 单元测试：17 项通过，包含真实 Aim SDK 写入、读取、重复同步和取消状态。
- 核心 Docker 集成测试：18 项通过，266.96 秒，覆盖完整训练、失败注入、取消、外部停止、平台重启恢复、HF 推理对齐和旧资产在 HF Runtime 中重用。
- 生产页面 Playwright：7 项通过，1.5 分钟。覆盖真实创建训练、下载产物、Hub 发布/导入、Aim 数据读取、键盘操作、无障碍检查和 320 / 768 / 1440 像素布局。
- `poetry check --lock`、Ruff、前端 TypeScript 检查通过。

## KohakuHub 与 Aim 联合验收

`test_central_storage.py`：**3 项通过，73.45 秒**。

1. HF Dataset 和 Model 发布到 Hub，按 commit 下载，SHA-256 清单一致；使用下载资产创建 `run-43bd7d452c9b`，容器训练成功，准确率 98.21%。产物晋升、上传、再次下载的 checksum 一致。远端 main 更新后，再次下载旧 commit 仍得到原始输入模型。
2. 旧非 HF Runtime 无法创建 Run；给旧镜像伪造 HF metadata 后注册也失败，验证来自实际容器导入检查。
3. 关闭 Hub 和 Aim，`run-cdde12b0b3a9` 本地训练成功，准确率 98.21%；重新启用后 Aim 成功补录，曲线由 SDK 读回。

最终生产镜像 `e37cdacf27a1` 上，新页面的两项浏览器测试再次通过（14.3 秒），覆盖 Hub 真实发布/导入和 Aim 曲线、Recipe 参数展示。完整实验页显示实际 optimizer、lr、batch size 与 epochs。

完整 Certification 的 Adam 模型已单独发布，避免与原始模型混淆：

- 仓库：`ninna-platform/mnist-cnn-trained`。
- 发布 commit：`2ac492b30e879a73f2722fc077ff0cf1e5022b1262290e895242e1df676155b4`。
- 本地模型：`mnist-cnn/cert-hf-v3`；重新导入版本：`mnist-cnn/cert-hf-v3-hub`。
- 两者 checksum 均为 `d2772ff38b25e57e9c0a3b617c6179bb476275577d68c8fb5a2178b71c696de9`。
- 来源 Run：`run-9eac0c09bd14`，准确率 98.94%；对应 Aim hash：`8abedc5b9bbd48268be818a8`。

KohakuHub 当前 API 的 repo info 返回 commit 的 40 字符前缀，上传返回 64 字符 commit；导入记录保存服务端实际解析结果，本轮已验证两种 revision 均可定位同一内容。完整发布/导入回执、Runtime 检查及 Aim 参数来源保存于本机 `outputs/platform/central-validation.json`。

## 复现命令

```bash
./scripts/platform.sh up
./scripts/mnist-certify.sh
poetry run pytest tests/unit -q
NINNA_INTEGRATION=1 poetry run pytest tests/integration/test_mnist.py -v
# 先在中心存储页面配置自己的 Hub 地址、命名空间及令牌。
NINNA_INTEGRATION=1 NINNA_HUB_INTEGRATION=1 \
  poetry run pytest tests/integration/test_central_storage.py -v
pnpm --dir src/web exec playwright test
```
