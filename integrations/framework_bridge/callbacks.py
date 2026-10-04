"""Ninna bridge v1: real Lightning events and optimizer/checkpoint evidence."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

from lightning.pytorch.callbacks import Callback
from lightning.pytorch.cli import SaveConfigCallback


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2))
    temporary.replace(path)


def trainable_hash(module):
    import torch

    digest = hashlib.sha256()
    for name, parameter in sorted(module.named_parameters()):
        if parameter.requires_grad:
            value = parameter.detach().cpu().contiguous()
            digest.update(f"{name}:{value.dtype}:{list(value.shape)}".encode())
            digest.update(value.reshape(-1).view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


class ResolvedConfig(SaveConfigCallback):
    def save_config(self, trainer, pl_module, stage):
        import yaml

        path = Path(trainer.log_dir) / "resolved.yaml"
        content = self.parser.dump(self.config, skip_none=False)
        if path.exists() and yaml.safe_load(path.read_text()) != yaml.safe_load(content):
            raise ValueError(f"Configuration drift: {path}; use a new run directory")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_suffix(".tmp")
            temporary.write_text(content)
            temporary.replace(path)

    def setup(self, trainer, pl_module, stage):
        # SaveConfigCallback's default overwrite check rejects legitimate identical invocations.
        if self.already_saved:
            return
        error = None
        if trainer.is_global_zero:
            try:
                self.save_config(trainer, pl_module, stage)
            except Exception as exc:
                error = str(exc)
        error = trainer.strategy.broadcast(error)
        if error:
            raise ValueError(error)
        self.already_saved = True


class RunEvidence(Callback):
    def __init__(self, output_dir: str):
        self.output = Path(output_dir)
        self.initial = None
        self.first_step = 0
        self.metrics = {}
        self.identity = None

    def setup(self, trainer, pl_module, stage):
        self.output.mkdir(parents=True, exist_ok=True)
        config = Path(os.environ.get("NINNA_RUN_CONFIG", "/config/run.json"))
        if config.is_file():
            run = json.loads(config.read_text())
            self.identity = {
                "framework": run["task_spec"]["framework"],
                "task": run["task_spec"]["task"],
                "inputs": {k: v.get("checksum", v["files"]) for k, v in run["inputs"].items()},
            }

    def on_train_start(self, trainer, pl_module):
        # Optimizer and loop state have been restored before this hook.
        self.first_step = trainer.global_step
        self.initial = trainable_hash(pl_module)

    def on_save_checkpoint(self, trainer, pl_module, checkpoint):
        checkpoint["ninna_identity"] = self.identity

    def on_load_checkpoint(self, trainer, pl_module, checkpoint):
        if self.identity is not None and checkpoint.get("ninna_identity") != self.identity:
            raise ValueError("Resume framework or input identity mismatch")

    def record(self, trainer, stage):
        if not trainer.is_global_zero or trainer.sanity_checking:
            return
        values = {}
        for name, value in trainer.callback_metrics.items():
            if hasattr(value, "numel") and value.numel() == 1:
                value = value.detach().cpu().item()
            if isinstance(value, (int, float)):
                if not math.isfinite(value):
                    raise ValueError(f"Non-finite metric: {name}")
                values[name] = float(value)
        self.metrics.update(values)
        with (self.output / "events.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "step": trainer.global_step,
                        "epoch": trainer.current_epoch,
                        "split": stage,
                        "metrics": values,
                    },
                    allow_nan=False,
                )
                + "\n"
            )
        atomic_json(self.output / "metrics.json", self.metrics)

    def on_train_batch_end(self, trainer, pl_module, outputs, batch, batch_idx):
        self.record(trainer, "train")

    def on_validation_end(self, trainer, pl_module):
        self.record(trainer, "validation")

    def on_test_end(self, trainer, pl_module):
        self.record(trainer, "test")

    def on_fit_end(self, trainer, pl_module):
        self.record(trainer, "train")
        if trainer.is_global_zero:
            final = trainable_hash(pl_module)
            atomic_json(
                self.output / "evidence.json",
                {
                    "optimizer_steps": trainer.global_step - self.first_step,
                    "global_step": trainer.global_step,
                    "initial_trainable_hash": self.initial,
                    "final_trainable_hash": final,
                },
            )
            if trainer.global_step <= self.first_step or final == self.initial:
                raise ValueError("Training did not update trainable parameters")
