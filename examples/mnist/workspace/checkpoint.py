import hashlib
import importlib.util
import json
import os
from pathlib import Path

import torch


def load_model(asset, root="/model"):
    spec = importlib.util.spec_from_file_location("asset_model", str(Path(root) / "model.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    torch.manual_seed(asset["initialization"]["seed"])
    model = getattr(module, asset["architecture"]["class"])()
    if asset.get("initial_checkpoint"):
        checkpoint = torch.load(
            Path(root) / asset["initial_checkpoint"], map_location="cpu", weights_only=True
        )
        model.load_state_dict(checkpoint["state_dict"], strict=True)
    return model


def state_hash(model):
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        tensor = tensor.detach().cpu().contiguous()
        digest.update(name.encode())
        digest.update(str(tensor.dtype).encode())
        digest.update(str(tuple(tensor.shape)).encode())
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def atomic_json(path, value):
    temp = Path(str(path) + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False))
    os.replace(temp, path)
