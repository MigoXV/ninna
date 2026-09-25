# Ninna · 深度学习训练工作空间

Ninna 是一个单机 Docker 训练平台。使用 MNIST 跑通真实训练、模型产物、失败诊断和系统验收。前端采用接近白色的极淡金色 MANAS 工作空间。

```text
训练定义：Dataset × Model × Recipe
执行环境：Runtime + Workspace snapshot + CPU resources
                         ↓
                    Training Run
                         ↓
                 独立 Docker Container
                         ↓
             checkpoint / metrics / logs / evidence
                         ↓
                 Model Artifact → Model Asset
```

## 快速启动

需要 Linux Docker Engine、Docker CLI、Python 3（仅用于启动时解析路径）和网络。无需 GPU，无需在宿主机安装 PyTorch。

```bash
git clone https://github.com/MigoXV/ninna.git
cd ninna
./scripts/install-compose.sh
./scripts/platform.sh up
./scripts/mnist-certify.sh
```

浏览器打开 `http://localhost:8000`。第一次启动会构建平台与 CPU Runtime，并下载、校验和注册 MNIST。随后启动不会重复下载数据。

初始化同时完成离线 HF 格式转换：逐条核对全部图片和标签，验证预处理、初始权重和 logits 一致。v1 资产和历史 Run 保留，默认使用 v2 HF 资产。

完整验收分别运行 Adam 和 SGD，验证容器、挂载、进程、日志、checkpoint 独立重载、权重变化、loss 下降以及 >98% 的测试准确率。最后输出：

```text
MNIST Platform Certification
...
OVERALL PASS
```

任何关键检查失败返回非零退出码。快速验收使用独立的 `quick-v1` Recipe（各 1 epoch、准确率 >95%）：

```bash
./scripts/mnist-certify.sh --quick
```

页面中的“系统验收”调用同一个验收服务。切换页面不会停止训练。

## 容器内操作 Docker：挂载路径

Docker bind mount 的 `source` 必须是 **Docker daemon 宿主机上的路径**。如果从开发容器启动本平台，设置外层容器实际名称：

```bash
export NINNA_OUTER_CONTAINER=wcw_test02
./scripts/platform.sh up
```

脚本读取 `docker inspect`，按最长匹配挂载前缀计算路径。当前开发环境的映射为：

```text
wcw_test02 内： /workspace/apps/ninna
Docker 宿主机：/mnt/zkyx-asr/home/wcw/repositories/apps/ninna
```

也可以显式指定：

```bash
export NINNA_HOST_ROOT=/mnt/zkyx-asr/home/wcw/repositories/apps/ninna
./scripts/platform.sh up
```

启动会在共享目录写入随机探针，再用真实容器只读挂载并验证内容。目录不共享、映射错误会明确失败。所有训练挂载复用同一转换规则，Compose 使用 `create_host_path: false` 防止静默创建空目录。

平台容器通过宿主机 Docker socket 创建训练容器。此 MVP 面向可信用户的单机环境，默认没有认证；配置远程访问时由部署者限制访问范围。

常用操作：

```bash
./scripts/platform.sh ps
./scripts/platform.sh logs -f platform
./scripts/platform.sh restart platform
./scripts/platform.sh down
```

`NINNA_PORT=8000` 可修改暴露端口。平台使用单个执行进程，同一存储通过文件锁防止重复执行器。

## 五类资产

| 对象 | 默认资产 | 作用 |
| --- | --- | --- |
| Dataset | `mnist/v2` | HF DatasetDict，60,000 train / 10,000 test，SHA-256 清单 |
| Model | `mnist-cnn/v2` | HF PreTrainedModel，421,642 参数，配置与 Safetensors 权重 |
| Recipe | `mnist-adam/v1` | CrossEntropy、Adam、lr 0.001、3 epochs |
| Recipe | `mnist-sgd/v1` | CrossEntropy、SGD、lr 0.05、momentum 0.9、5 epochs |
| Runtime | `mnist-pytorch-runtime/v2` | Python 3.10、PyTorch 2.8.0 CPU、Transformers 4.57.1、Datasets 4.4.1 |
| Workspace | `mnist-hf/v1` | 可编辑本地代码目录，Run 使用内容寻址快照 |

Runtime Dockerfile 不包含训练业务代码。Dataset、Model、Workspace、解析配置以只读方式挂载，output 可写。训练容器关闭网络且不接触 Docker socket。实际训练入口是容器中的 Python 进程。

Workspace 默认路径为 `examples/mnist/workspace-hf`。修改代码后新建 Run 就会生成新快照，无需重建 Runtime。快照包含普通 tracked/untracked 文件，排除 `.git`、`.env*`、虚拟环境、依赖、缓存和输出目录，并拒绝符号链接。

Recipe 支持 loss、optimizer 参数、epoch、batch size、gradient accumulation、StepLR、按参数名前缀冻结和指定 epoch 解冻。Model 不包含 loss、optimizer 或训练循环。

所有资产按名称与版本引用，已有版本不能用不同内容覆盖。Runtime 记录并使用不可变 image ID；更新环境应注册新版本。

## Run、输出与生命周期

```text
CREATED → PREPARING → RUNNING → SUCCESS / FAILED / CANCELLED
```

平台主动取消是 `CANCELLED`；外部 `docker stop`、OOM、非零退出、缺少必要训练证据为 `FAILED`。平台重启会检查既有容器并恢复监控。Docker 暂时不可达时记录监控错误并重试，不猜测成功或退出码。

Run 定义与资产快照不可修改，生命周期字段可向前推进；终态封存。重新训练会产生新的 run_id。默认串行执行。

输出位于：

```text
outputs/platform/
├── ninna.sqlite3
├── snapshots/<snapshot-hash>/
├── certifications/<certification-id>.json
└── runs/<run-id>/
    ├── config/run.json
    ├── model/                 # HF config、Safetensors、processor、自定义模型代码
    ├── model.tar.gz           # 可下载的完整 HF 模型包
    ├── checkpoint.pt
    ├── metrics.json
    ├── events.jsonl
    ├── stdout.log
    ├── stderr.log
    ├── run.json
    ├── container.json
    ├── process.json
    └── process-observation.json
```

逐 epoch 记录训练与测试指标，前端准实时刷新。`metrics.json` 包含 `train_loss`、`final_train_loss`、`test_loss`、`test_accuracy`、`epochs`、`elapsed_time`、`initial_loss`、`final_loss` 和初始/最终 state_dict hash。

Loss 下降使用相同固定的 2,048 个训练样本、相同 eval 模式比较。模型 hash 按排序参数名、dtype、shape 与 tensor 字节计算。Certification 在另一个只读验证容器中重新加载 checkpoint 并评估完整测试集。

成功 Run 的“产物”页可以将 checkpoint 注册为新的 Model 版本。随后在创建训练页选择该版本，进行基于已训练权重的新训练；不恢复旧 Run 的优化器或 epoch 状态。

平台重启会将尚未完成的 Certification 编排标记为失败；其底层 Run 仍会恢复监控，可重新发起一次验收。

历史训练容器和验证容器默认保留，便于 `docker inspect <container_id>` 核验。此版本没有自动清理策略，请按需清理已完成的本项目容器；文件产物独立持久保存。

## API 与 Harness

OpenAPI：`http://localhost:8000/docs`。

主要接口：

| 接口 | 作用 |
| --- | --- |
| `GET/POST /api/assets/{kind}` | 查询/注册 Dataset、Model、Recipe、Runtime、Workspace |
| `POST /api/workspaces/{name}/snapshots` | 创建 Workspace 快照 |
| `GET /api/workspaces/{name}/files` | 文件清单与只读预览 |
| `GET/POST /api/runs` | 查询/创建 Run |
| `GET /api/runs/{id}` | 完整 Run |
| `POST /api/runs/{id}/cancel` | 请求取消 |
| `GET /api/runs/{id}/logs?stream=stdout&offset=0` | 按字节 offset 读取日志 |
| `GET /api/runs/{id}/metrics` | epoch 事件和最终指标 |
| `GET /api/runs/{id}/artifacts/{filename}` | 下载产物 |
| `POST /api/runs/{id}/promote` | 注册模型新版本，body 为 `{"version":"trained-001"}` |
| `GET /api/runs/{id}/diagnostics` | 完整诊断上下文 |
| `GET/POST /api/certifications` | 查询/发起验收 |
| `GET /api/certifications/{id}` | 验收结果与逐项证据 |

`Platform.get_run_diagnostic_context(run_id)` 是诊断服务实现；HTTP 接口返回 TrainingSpec、ExecutionSpec、资产信息、Workspace 快照、stdout/stderr、exit code、metrics、inspect、资源和状态事件。未来 Harness 可读取诊断、修改 Workspace 或创建 Recipe 新版本，然后新建 Run。历史 Run 无写入接口。

创建 Run 示例：

```bash
curl -sS http://localhost:8000/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"training_spec":{"dataset":{"name":"mnist","version":"v2"},"model":{"name":"mnist-cnn","version":"v2"},"recipe":{"name":"mnist-adam","version":"v1"}},"execution_spec":{"runtime":{"name":"mnist-pytorch-runtime","version":"v2"},"workspace":{"name":"mnist-hf","snapshot":"current"},"resources":{"device":"cpu","gpu_count":0,"cpu_threads":4,"memory_mb":4096}}}'
```

## Hugging Face 格式与离线推理

模型目录遵循 `save_pretrained`：`config.json`、`model.safetensors`、`preprocessor_config.json` 与三个自定义 Python 模块。配置包含 `auto_map`，支持 `AutoConfig`、`AutoModel`、`AutoModelForImageClassification`、`AutoImageProcessor` 从本地路径加载。`trust_remote_code=True` 用于执行随资产保存、经 manifest 校验的平台自定义 CNN 代码；加载时 `local_files_only=True`，训练容器关闭网络。

数据目录遵循 `DatasetDict.save_to_disk`：`train` / `test` 两个 Arrow split，字段 `image: Image` 和 `label: ClassLabel`。训练使用 `load_from_disk`，不依赖 Hub 账号，也不在训练时下载数据。

成功 Run 的 `model.tar.gz` 可在产物页下载。解压后，可在 HF Runtime 中使用标准接口：

```python
from datasets import load_from_disk
from transformers import AutoImageProcessor, AutoModelForImageClassification
import torch

# 路径为当前容器中的挂载路径。
dataset = load_from_disk("/dataset")
processor = AutoImageProcessor.from_pretrained(
    "/output/model", local_files_only=True, trust_remote_code=True, use_fast=False)
model = AutoModelForImageClassification.from_pretrained(
    "/output/model", local_files_only=True, trust_remote_code=True).float().cpu().eval()
with torch.inference_mode():
    batch = processor(dataset["test"][:8]["image"], return_tensors="pt")
    predictions = model(**batch).logits.argmax(-1)
```

独立的 `examples/mnist/workspace-hf/inference.py` 管理模型一次加载与 CPU / FP32 / eager 推理。Model 只返回 logits，Criterion、Optimizer 和训练循环仍在 Workspace。Certification 在新容器中加载 HF 模型，与 `checkpoint.pt` 对齐 logits 和 hash，并验证单张/批量推理误差与全部测试集准确率。

继续训练时，将完整 HF 模型目录注册为新的 Model 版本，创建新 Run。已有 v1 Run、资产和快照不被迁移覆盖。源格式兼容性也有真实 Docker 回归测试。

HF Runtime 的附加安装命令为：

```bash
pip install transformers==4.57.1 datasets==4.4.1 safetensors==0.6.2
```

## 开发与测试

开发依赖：Python 3.10、Poetry、Node.js 22+、pnpm。宿主机无需安装 torch；torch 生态仅通过 Runtime Dockerfile 的 pip 命令安装：

```bash
pip install torch==2.8.0+cpu torchvision==0.23.0+cpu \
  --extra-index-url https://download.pytorch.org/whl/cpu
```

开发启动：

```bash
poetry env use python3.10
poetry install
pnpm --dir src/web install
pnpm --dir src/web run build
# 与 Compose 二选一，避免两个平台进程同时打开相同存储。
# 容器内开发时同时设置 NINNA_HOST_ROOT。
poetry run ninna serve
poetry run ninna initialize
```

VS Code 的 Ninna web 调试会先执行 `web: build`，后端统一托管前端。Vite dev 仅用于前端开发。

```bash
poetry run ruff check src/ninna tests
poetry run pytest tests/unit -q
pnpm --dir src/web run lint
pnpm --dir src/web run build
pnpm --dir src/web exec playwright install chromium
pnpm --dir src/web run test
```

真实 Docker 集成测试必须先启动平台，执行：

```bash
NINNA_INTEGRATION=1 poetry run pytest tests/integration -v
```

包含两个 Recipe 的完整 Certification、真实容器与挂载、checkpoint 重载、模型 hash、失败日志、非法 optimizer、平台取消、外部停止，以及 Model Artifact 晋升和再次训练。没有 mock Docker Training。默认单元测试跳过集成测试，但 Certification 遇到 Docker 不可用必须失败。

故意失败场景可单独复现：

```bash
NINNA_INTEGRATION=1 poetry run pytest tests/integration \
  -k 'failed_run_logs_preserved or bad_recipe or interrupted_run' -v
```

它们会创建真实失败 Run，保留容器、日志与诊断上下文，可直接从 Web 查看。

## 当前边界

单机可信用户、CPU、串行执行、SQLite + 本地目录；不包含 Kubernetes、多租户、权限系统、分布式训练、DAG 或 Agent。数据资产和模型资产存储为绝对路径，移动整个存储根目录需要显式迁移路径。输入快照由平台校验并只读挂载；宿主机管理员仍可修改文件，后续运行会检测校验变化。

设计与页面状态约定位于 [docs/ui-design.md](docs/ui-design.md)。运行证据和验证结论见 [docs/validation.md](docs/validation.md)。
