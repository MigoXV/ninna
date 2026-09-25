# 实际验收记录

2026-09-25，在 CPU Docker Runtime v1 上完成，所有训练均由平台创建的容器执行。

- 单元测试：14 项通过。
- `NINNA_INTEGRATION=1 poetry run pytest tests/integration -v`：16 项通过，252.63 秒；覆盖真实训练、挂载、checkpoint 重载、失败日志、停止、模型再注册、平台重启恢复。
- Playwright：5 项通过，含真实创建训练与下载产物、无障碍检查、320/768/1280/1440 像素布局、键盘和失败重试。
- `./scripts/mnist-certify.sh`：`OVERALL PASS`。
- Certification：`cert-36c1c1fdcda2`。
- Adam：`run-e18ca8695882`，测试准确率 98.94%。
- SGD：`run-9bfe4f714f9f`，测试准确率 98.70%。
- 两次 Run 的 Dataset、Model、Runtime 和 Workspace snapshot 相同，只有 Recipe 不同。

完整报告位于 `outputs/platform/certifications/`，Run 的不可变输入、日志、容器检查结果、指标和 checkpoint 位于 `outputs/platform/runs/`。这些本地大文件不提交 Git；新环境需执行验收命令生成自己的证据。

## Hugging Face 迁移验收

Runtime v2：PyTorch 2.8.0 CPU、Transformers 4.57.1、Datasets 4.4.1、Safetensors 0.6.2。

- 离线转换在 Docker 容器内执行；70,000 张图片的每个像素与标签全部一致，split 顺序保持一致。
- torchvision 预处理与 HF ImageProcessor 输出逐元素完全一致。
- v1 与 HF v2 初始模型的 state_dict hash、logits 完全一致。
- 完整 HF Certification：`cert-95d6dd1929aa`，`OVERALL PASS`。
- Adam：`run-0bcd3f9b137d`，3 epochs，准确率 **98.94%**。
- SGD：`run-1c87d58d9179`，5 epochs，准确率 **98.70%**。
- 两个模型均由独立验证容器使用 AutoModel / AutoModelForImageClassification 从本地 HF 目录重新加载；与 checkpoint.pt 的 state_dict hash 和批量 logits 完全一致。
- CPU FP32 eager 单张与 batch=32 的最大 logits 误差：Adam `2.86e-6`、SGD `3.81e-6`，在 `atol=1e-5, rtol=1e-5` 容差内。
- Dataset 使用 Image / ClassLabel + Arrow；模型使用 config、Safetensors、processor 与可自动加载的自定义代码。训练与重载容器均无网络。

这些结果用于正确性验证，没有做加速或性能收益声明。

迁移回归测试：`NINNA_INTEGRATION=1 poetry run pytest tests/integration -v`，**18 项通过，296.59 秒**；包含真实 HF 训练、失败注入、取消、外部停止、平台重启恢复、完整 HF 模型晋升与继续训练，以及 v1 资产再次训练。单元测试 **14 项通过**，Ruff 与前端 TypeScript 检查通过。

最终 Compose 生产镜像 `6cf55c611292` 的 Playwright 测试：**5 项通过，1.5 分钟**。包括 320/768/1280/1440 像素布局、WCAG 检查、键盘焦点与 `/` 搜索快捷键，以及从页面创建实际 HF Run、确认提交的 Recipe 为 quick-v1、等待训练完成和下载 checkpoint。实际页面 Run：`run-9cc08c7cabdc`。

最终部署后再次执行 `./scripts/mnist-certify.sh`：**OVERALL PASS**。

- 报告：`cert-dd586674d67e`。
- Adam：`run-bb5f7f039b24`，98.94%。
- SGD：`run-b6c351f56c4a`，98.70%。
- Runtime image ID：`sha256:9d22dda739a603346f0a467fe8e94948ed323e54ceac3728bce4aecfe18198b8`。
- 两次 Run 使用相同 Dataset、Model、Runtime 和 Workspace snapshot；只替换 Recipe。
- 全部检查 PASS，CLI 退出码为 0。模型晋升后的初始化 hash 也已通过生产 API 单独核验。
