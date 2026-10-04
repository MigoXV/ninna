"""Check the actual immutable image before allowing a training container."""

from __future__ import annotations

import json
import threading


class HFRuntimeValidator:
    def __init__(self, docker):
        self.docker = docker
        self.cache = {}
        self.lock = threading.Lock()

    def validate(self, asset, framework=None):
        image_id = asset["image_id"]
        cache_key = (image_id, json.dumps(framework, sort_keys=True))
        with self.lock:
            image = self.docker().images.get(image_id)
            if cache_key in self.cache:
                return self.cache[cache_key]
            probe = (
                "import json,platform,torch,torchvision,transformers,datasets,huggingface_hub,safetensors; "
                "from transformers import AutoModel,AutoConfig,AutoImageProcessor; "
                "from datasets import DatasetDict,load_from_disk; "
                "print(json.dumps(dict(python=platform.python_version(), **{m.__name__:m.__version__ for m in [torch,torchvision,transformers,datasets,huggingface_hub,safetensors]})))"
            )
            if framework:
                probe = (
                    "import json,platform,importlib,importlib.util,yaml; from pathlib import Path; "
                    "s=yaml.safe_load(Path('/app/ninna-framework.yaml').read_text()); "
                    f"assert {{'name':s['name'],'version':s['version']}} == {framework!r}; "
                    "modules=[importlib.import_module(n) for n in s['imports']]; "
                    "importlib.import_module('torchcodec') if importlib.util.find_spec('torchcodec') else None; "
                    "print(json.dumps(dict(python=platform.python_version(), **{m.__name__:getattr(m,'__version__','available') for m in modules})))"
                )
            container = self.docker().containers.create(
                image.id,
                ["python", "-c", probe],
                entrypoint=[],
                working_dir="/app" if framework else None,
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
                        "训练 Runtime 必须支持 HF 生态：torch、transformers、datasets、huggingface_hub、safetensors；请选用包含这些依赖的镜像"
                    )
                versions = json.loads(
                    container.logs(stdout=True, stderr=False).decode().strip().splitlines()[-1]
                )
                evidence = {
                    "image_id": image.id,
                    "versions": versions,
                    "container_id": container.id,
                }
                self.cache[cache_key] = evidence
                return evidence
            except Exception:
                container.reload()
                if container.status == "running":
                    container.stop(timeout=1)
                raise
