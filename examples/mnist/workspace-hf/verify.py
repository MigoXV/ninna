import json
from pathlib import Path

import torch
from datasets import load_from_disk
from transformers import AutoModel
from checkpoint import load_model, state_hash
from data import loaders
from inference import Classifier
from loss import build_loss
from trainer import evaluate

config = json.loads(Path("/config/run.json").read_text())
torch.set_num_threads(config["execution_spec"]["resources"]["cpu_threads"])
model = load_model(config["assets"]["model"])
checkpoint = torch.load("/output/checkpoint.pt", map_location="cpu", weights_only=True)
model.load_state_dict(checkpoint["state_dict"], strict=True)
model.eval()
classifier = Classifier("/output/model")
assert state_hash(classifier.model) == state_hash(model)
auto_model = AutoModel.from_pretrained(
    "/output/model", local_files_only=True, trust_remote_code=True
)
assert state_hash(auto_model) == state_hash(model)
images = load_from_disk("/dataset")["test"][:32]["image"]
with torch.inference_mode():
    pixels = classifier.processor(images, return_tensors="pt")["pixel_values"]
    expected = model(pixels).logits
    actual = classifier.predict(images)
    individual = torch.cat([classifier.predict([image]) for image in images])
assert torch.equal(expected, actual)
assert torch.allclose(actual, individual, atol=1e-5, rtol=1e-5)
_, test_loader, _ = loaders("/dataset", 128, 42)
loss, accuracy = evaluate(classifier.model, test_loader, build_loss("CrossEntropyLoss"))
print(
    json.dumps(
        {
            "checkpoint_reload": True,
            "hf_reload": True,
            "hf_auto_model_reload": True,
            "hf_logits_exact": True,
            "single_batch_max_error": (actual - individual).abs().max().item(),
            "trained_model_hash": state_hash(classifier.model),
            "test_loss": loss,
            "test_accuracy": accuracy,
        }
    )
)
