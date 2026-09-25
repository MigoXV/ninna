"""从已注册的资产生成说明；不改写历史资产或其文件清单。"""

from __future__ import annotations

import json
from pathlib import Path


def asset_card(kind: str, asset: dict) -> str:
    identity = f"{asset['name']} / {asset['version']}"
    metadata = asset.get("metadata", {})
    sections = [f"# {identity}", f"Ninna {kind} 资产。使用精确的 name/version 引用。"]
    if kind == "dataset":
        sections += [
            "## 数据与加载",
            "这是已沉淀的数据资产；训练时由平台只读挂载到 `/dataset`，训练代码不下载数据。",
            f"训练 split：`{asset.get('train_split')}`；测试 split：`{asset.get('test_split')}`。",
        ]
        if metadata.get("format") == "huggingface.DatasetDict":
            sections += [
                "```python\nfrom datasets import load_from_disk\n"
                'dataset = load_from_disk("/dataset")\n```',
                "磁盘格式为 DatasetDict（Arrow），从 Hub 下载仓库后使用 load_from_disk。",
            ]
    elif kind == "model":
        sections += [
            "## 模型与加载",
            f"架构：`{asset.get('architecture')}`；参数量：`{asset.get('parameter_count')}`。",
            f"初始化：`{asset.get('initialization')}`；初始权重：`{asset.get('initial_checkpoint')}`。",
            "模型定义不包含优化器、loss 或训练循环；这些由 Recipe 和 Workspace 提供。",
        ]
        if metadata.get("format") == "huggingface.PreTrainedModel":
            sections += [
                "```python\nfrom transformers import AutoModelForImageClassification\n"
                "model = AutoModelForImageClassification.from_pretrained(\n"
                '    "/model", trust_remote_code=True, local_files_only=True\n)\n```',
                "先审阅仓库中的自定义 Python 模型代码，再允许加载。权重为 Safetensors。",
            ]
        sections += [
            "训练结果来自具体 Run；初始模型资产不能据此宣称已训练。"
            "输入预处理与标签语义应和 Dataset/Workspace 的说明一致。"
        ]
    elif kind == "recipe":
        sections += [
            "## 训练策略",
            "由 Workspace 解释 loss、optimizer、scheduler、epochs、"
            "batch_size、gradient_accumulation、freeze 等配置。修改策略应注册新版本。",
        ]
    elif kind == "runtime":
        sections += [
            "## 执行环境",
            "对应 Docker image_id；创建 Run 前检查镜像和依赖。"
            "业务代码来自 Workspace 挂载；修改 Workspace 无需重建镜像。",
        ]
    else:
        sections += [
            "## 代码空间",
            "本地目录可编辑；执行前生成内容寻址快照，包含未跟踪文件。"
            "当前平台使用注册版本 v1；运行时引用 name + snapshot。"
            "对比 Recipe 时复用同一个 snapshot。",
        ]
    portable = {key: value for key, value in asset.items() if key not in {"path", "files", "id"}}
    sections += [
        "## 资产描述",
        "```json\n" + json.dumps(portable, ensure_ascii=False, indent=2) + "\n```",
        "## 校验与来源",
        f"SHA-256 清单标识：`{asset.get('checksum', '未提供')}`。",
        "`ninna-asset.json`（发布后）保存完整文件清单和导入描述。"
        "导入固定到 Hub commit；同名同版本不覆盖。"
        "历史 Run 保存实际训练定义、执行环境、容器、日志及产物。",
    ]
    return "\n\n".join(sections) + "\n"


def describe_asset(kind: str, asset: dict, platform_root: Path) -> dict:
    result = {"asset": asset, "documentation": asset_card(kind, asset), "readme": None}
    if asset.get("path"):
        root = Path(asset["path"]).resolve()
        readme = root / "README.md"
        if (
            root.is_relative_to(platform_root.resolve())
            and readme.is_file()
            and not readme.is_symlink()
        ):
            with readme.open("rb") as source:
                data = source.read(100001)
            result["readme"] = data[:100000].decode(errors="replace")
            result["readme_truncated"] = len(data) > 100000
    return result
