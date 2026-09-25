"""Offline CPU FP32 eager baseline; preprocessing and model lifecycle are separate."""

from pathlib import Path

import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForImageClassification


class Classifier:
    def __init__(self, model_path: str | Path):
        self.processor = AutoImageProcessor.from_pretrained(
            model_path, local_files_only=True, trust_remote_code=True, use_fast=False
        )
        self.model = (
            AutoModelForImageClassification.from_pretrained(
                model_path, local_files_only=True, trust_remote_code=True
            )
            .to(device="cpu", dtype=torch.float32)
            .eval()
        )

    @torch.inference_mode()
    def predict(self, images: list[Image.Image]) -> torch.Tensor:
        inputs = self.processor(images, return_tensors="pt")
        return self.model(**inputs).logits
