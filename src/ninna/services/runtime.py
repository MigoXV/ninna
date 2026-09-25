"""Check the actual immutable image before allowing a training container."""

from __future__ import annotations

import json
import threading


class HFRuntimeValidator:
    def __init__(self, docker):
        self.docker = docker
        self.cache = {}
        self.lock = threading.Lock()

    def validate(self, asset):
        image_id = asset["image_id"]
        with self.lock:
            if image_id in self.cache:
                return self.cache[image_id]
            image = self.docker().images.get(image_id)
            container = self.docker().containers.create(
                image.id,
                [
                    "python",
                    "-c",
                    "import json,torch,transformers,datasets,huggingface_hub,safetensors; "
                    "from transformers import AutoModel,AutoConfig,AutoImageProcessor; "
                    "from datasets import DatasetDict,load_from_disk; "
                    "print(json.dumps({m.__name__:m.__version__ for m in [torch,transformers,datasets,huggingface_hub,safetensors]}))",
                ],
                network_mode="none",
                network_disabled=True,
                mem_limit="2g",
                nano_cpus=2 * 10**9,
                labels={"ninna.role": "hf-runtime-validation"},
            )
            try:
                container.start()
                result = container.wait(timeout=120)
                if result["StatusCode"] != 0:
                    raise ValueError(
                        "训练 Runtime 必须支持 HF 生态：torch、transformers、datasets、huggingface_hub、safetensors；请使用 HF Runtime v3"
                    )
                versions = json.loads(
                    container.logs(stdout=True, stderr=False).decode().strip().splitlines()[-1]
                )
                evidence = {
                    "image_id": image.id,
                    "versions": versions,
                    "container_id": container.id,
                }
                self.cache[image_id] = evidence
                return evidence
            except Exception:
                container.reload()
                if container.status == "running":
                    container.stop(timeout=1)
                raise
