"""Portable HF export, independent from the training loop and inference loader."""

import tarfile
from pathlib import Path

from transformers import AutoImageProcessor, PreTrainedModel


def export_model(model: PreTrainedModel, output: Path) -> None:
    model.save_pretrained(output / "model", safe_serialization=True)
    processor = AutoImageProcessor.from_pretrained(
        "/model", local_files_only=True, trust_remote_code=True, use_fast=False
    )
    processor.save_pretrained(output / "model")
    with tarfile.open(output / "model.tar.gz", "w:gz") as archive:
        archive.add(output / "model", arcname="model")
