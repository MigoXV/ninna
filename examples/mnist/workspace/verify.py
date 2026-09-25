import json
from pathlib import Path

import torch
from checkpoint import load_model, state_hash
from data import loaders
from loss import build_loss
from trainer import evaluate

config = json.loads(Path("/config/run.json").read_text())
torch.set_num_threads(config["execution_spec"]["resources"]["cpu_threads"])
model = load_model(config["assets"]["model"])
checkpoint = torch.load("/output/checkpoint.pt", map_location="cpu", weights_only=True)
model.load_state_dict(checkpoint["state_dict"], strict=True)
_, test_loader, _ = loaders("/dataset", 128, 42)
loss, accuracy = evaluate(model, test_loader, build_loss("CrossEntropyLoss"))
print(
    json.dumps(
        {
            "checkpoint_reload": True,
            "trained_model_hash": state_hash(model),
            "test_loss": loss,
            "test_accuracy": accuracy,
        }
    )
)
