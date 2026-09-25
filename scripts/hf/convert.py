"""Offline conversion executed by the platform in a versioned Docker runtime."""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import torch
from datasets import ClassLabel, Dataset, DatasetDict, Features, Image, load_from_disk
from torchvision.datasets import MNIST
from torchvision.transforms import Compose, Normalize, ToTensor

sys.path.insert(0, "/legacy_workspace")
from checkpoint import load_model, state_hash

spec = importlib.util.spec_from_file_location(
    "mnist_hf", "/code/__init__.py", submodule_search_locations=["/code"]
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
torch.set_num_threads(4)
legacy_asset = {"initialization": {"seed": 42}, "architecture": {"class": "MnistCNN"}}
legacy = load_model(legacy_asset, "/legacy_model").eval()
model = module.MnistForImageClassification(module.MnistConfig()).eval()
model.load_state_dict(legacy.state_dict(), strict=True)
processor = module.MnistImageProcessor()
model.save_pretrained("/result/model")
processor.save_pretrained("/result/model")
# Both AutoModel entry points support loading the same platform-owned local code.
config_path = Path("/result/model/config.json")
config = json.loads(config_path.read_text())
config["auto_map"]["AutoModel"] = config["auto_map"]["AutoModelForImageClassification"]
config_path.write_text(json.dumps(config, indent=2))
features = Features({"image": Image(), "label": ClassLabel(names=[str(i) for i in range(10)])})
splits = {}
for name, train in [("train", True), ("test", False)]:
    original = MNIST("/source", train=train, download=False)
    splits[name] = Dataset.from_dict(
        {"image": [np.array(image) for image, _ in original], "label": original.targets.tolist()},
        features=features,
    )
DatasetDict(splits).save_to_disk("/result/dataset")
loaded = load_from_disk("/result/dataset")
for name, train in [("train", True), ("test", False)]:
    original = MNIST("/source", train=train, download=False)
    assert len(loaded[name]) == len(original)
    # Check every image byte and label, preserving split membership and order.
    for start in range(0, len(original), 512):
        batch = loaded[name][start : start + 512]
        assert np.array_equal(
            np.stack([np.array(x) for x in batch["image"]]),
            original.data[start : start + 512].numpy(),
        )
        assert batch["label"] == original.targets[start : start + 512].tolist()
images = loaded["test"][:32]["image"]
reference = torch.stack([Compose([ToTensor(), Normalize((0.1307,), (0.3081,))])(i) for i in images])
pixels = processor(images)["pixel_values"]
assert torch.equal(reference, pixels)
with torch.inference_mode():
    assert torch.equal(legacy(reference), model(pixels).logits)
assert state_hash(legacy) == state_hash(model)
report = {
    "all_images_and_labels_equal": True,
    "preprocessing_exact": True,
    "logits_exact": True,
    "initial_model_hash": state_hash(model),
    "train_count": 60000,
    "test_count": 10000,
    "fingerprints": {key: value._fingerprint for key, value in loaded.items()},
}
Path("/result/conversion.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report), flush=True)
