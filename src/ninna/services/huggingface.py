"""Versioned, offline HF migration; torch and datasets execute only inside Docker."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from docker.types import Mount

from ninna.services.assets import manifest, manifest_hash


def initialize_hf(platform):
    settings, repo = platform.settings, platform.repo
    image = platform.docker.images.get("ninna/pytorch-runtime:v2")
    repo.register(
        "runtime",
        {
            "name": "mnist-pytorch-runtime",
            "version": "v2",
            "image": "ninna/pytorch-runtime:v2",
            "image_id": image.id,
            "metadata": {
                "python": "3.10",
                "torch": "2.8.0",
                "torchvision": "0.23.0",
                "transformers": "4.57.1",
                "datasets": "4.4.1",
                "safetensors": "0.6.2",
                "device": "cpu",
            },
        },
    )
    dataset = settings.root / "data-bin/mnist/v2"
    model = settings.root / "model-bin/mnist-cnn/v2"
    result = settings.state / "hf-conversion"
    report_path = result / "conversion.json"
    if not report_path.exists():
        if result.exists():
            shutil.rmtree(result)
        result.mkdir(parents=True)
        mounts = [
            Mount(dest, settings.host_path(settings.root / source), type="bind", read_only=True)
            for dest, source in [
                ("/source", "data-bin/mnist/v1"),
                ("/legacy_model", "model-bin/mnist-cnn/v1"),
                ("/legacy_workspace", "examples/mnist/workspace"),
                ("/code", "examples/mnist/model-hf"),
                ("/tools", "scripts/hf"),
            ]
        ]
        mounts.append(Mount("/result", settings.host_path(result), type="bind"))
        container = platform.docker.containers.create(
            image.id,
            ["python", "-u", "/tools/convert.py"],
            mounts=mounts,
            network_mode="none",
            network_disabled=True,
            mem_limit="4g",
            nano_cpus=4 * 10**9,
            environment={"PYTHONDONTWRITEBYTECODE": "1"},
            labels={"ninna.role": "hf-conversion"},
        )
        container.start()
        status = container.wait(timeout=600)["StatusCode"]
        (result / "stdout.log").write_bytes(container.logs(stdout=True, stderr=False))
        (result / "stderr.log").write_bytes(container.logs(stdout=False, stderr=True))
        (result / "container.json").write_text(
            json.dumps({"container_id": container.id, "exit_code": status})
        )
        if status != 0:
            report_path.unlink(missing_ok=True)
            raise ValueError(
                f"HF conversion failed in {container.id}: {container.logs().decode(errors='replace')[-4000:]}"
            )
    report = json.loads(report_path.read_text())
    for source, target in [(result / "dataset", dataset), (result / "model", model)]:
        if not target.exists():
            temporary = Path(str(target) + ".tmp")
            if temporary.exists():
                shutil.rmtree(temporary)
            shutil.copytree(source, temporary)
            temporary.rename(target)
    for kind, target, extra in [
        (
            "dataset",
            dataset,
            {
                "train_split": {"name": "train", "count": 60000},
                "test_split": {"name": "test", "count": 10000},
                "metadata": {
                    "shape": [1, 28, 28],
                    "classes": 10,
                    "format": "huggingface.DatasetDict",
                    "features": {"image": "Image", "label": "ClassLabel"},
                    "conversion": report,
                },
            },
        ),
        (
            "model",
            model,
            {
                "architecture": {
                    "class": "MnistForImageClassification",
                    "entrypoint": "modeling_mnist.py",
                    "description": "Conv 32 → ReLU → Pool → Conv 64 → ReLU → Pool → Linear 128 → Linear 10",
                },
                "initialization": {"seed": 42, "method": "from_pretrained"},
                "initial_checkpoint": "model.safetensors",
                "parameter_count": 421642,
                "metadata": {
                    "input": [1, 28, 28],
                    "output": 10,
                    "format": "huggingface.PreTrainedModel",
                    "initial_model_hash": report["initial_model_hash"],
                },
            },
        ),
    ]:
        files = manifest(target)
        repo.register(
            kind,
            {
                "name": "mnist" if kind == "dataset" else "mnist-cnn",
                "version": "v2",
                "path": str(target),
                "files": files,
                "checksum": manifest_hash(files),
                **extra,
            },
        )
    repo.register(
        "workspace",
        {
            "name": "mnist-hf",
            "version": "v1",
            "path": str(settings.root / "examples/mnist/workspace-hf"),
            "entrypoint": "train.py",
            "metadata": {
                "description": "HF DatasetDict + PreTrainedModel; offline CPU training and inference"
            },
        },
    )
    return {"status": "ready", "format": "huggingface", "conversion": report}
