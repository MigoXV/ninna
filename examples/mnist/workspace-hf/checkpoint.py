import hashlib
import json
import os
from pathlib import Path

import torch


def load_model(asset, root="/model"):
    from transformers import AutoModelForImageClassification

    return AutoModelForImageClassification.from_pretrained(
        root, local_files_only=True, trust_remote_code=True
    ).to(device="cpu", dtype=torch.float32)


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


def save_checkpoint(model, architecture, run_id, path):
    torch.save(
        {"state_dict": model.state_dict(), "architecture": architecture, "run_id": run_id}, path
    )
