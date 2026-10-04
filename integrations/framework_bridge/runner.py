"""Framework bridge v1. Invoke declared native commands; never assemble Trainer objects."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import yaml


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bind(value, variables):
    if isinstance(value, dict):
        return {k: bind(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [bind(v, variables) for v in value]
    if isinstance(value, str):
        for key, replacement in variables.items():
            value = value.replace("{" + key + "}", replacement)
    return value


def artifact_kind(path):
    if path.suffix == ".ckpt":
        return "checkpoint"
    if path.suffix == ".safetensors":
        return "adapter" if "adapter" in path.name else "model"
    if path.suffix in {".wav", ".flac"}:
        return "audio"
    if path.suffix in {".parquet", ".arrow"}:
        return "dataset"
    if path.name == "resolved.yaml":
        return "config"
    return "report"


def main():
    run_path = Path(sys.argv[1])
    run = json.loads(run_path.read_text())
    output = Path(os.environ.get("NINNA_OUTPUT", "/output"))
    output.mkdir(parents=True, exist_ok=True)
    spec = run["task_spec"]
    operation = spec["operation"]
    variables = {
        "output": str(output),
        "config": str(output / "invocation.yaml"),
        "source": "/source/artifact",
        "task": spec["task"],
        "device": "cuda:0" if run["execution_spec"]["resources"]["device"] == "cuda" else "cpu",
        **{k: "/inputs/" + k for k in run["inputs"]},
    }
    config = bind(run["assets"]["recipe"]["config"], variables)
    if operation in {"train", "evaluate"}:
        trainer = config.setdefault("trainer", {})
        resources = run["execution_spec"]["resources"]
        trainer["accelerator"] = "gpu" if resources["device"] == "cuda" else "cpu"
        trainer["devices"] = 1
        if operation == "train":
            trainer["enable_checkpointing"] = True
        trainer["default_root_dir"] = str(output / "training")
        trainer.setdefault("enable_progress_bar", False)
        trainer["logger"] = {
            "class_path": "lightning.pytorch.loggers.CSVLogger",
            "init_args": {"save_dir": str(output), "name": "training", "version": "run"},
        }
        callbacks = trainer.setdefault("callbacks", [])
        checkpoint_callbacks = [
            callback for callback in callbacks if callback["class_path"].endswith("ModelCheckpoint")
        ]
        if operation == "train" and not checkpoint_callbacks:
            checkpoint = {
                "class_path": "lightning.pytorch.callbacks.ModelCheckpoint",
                "init_args": {},
            }
            callbacks.append(checkpoint)
            checkpoint_callbacks.append(checkpoint)
        # Framework callbacks remain native class_path/init_args declarations.
        for callback in callbacks:
            if callback["class_path"].endswith("ModelCheckpoint"):
                callback.setdefault("init_args", {})["dirpath"] = str(output / "checkpoints")
        for callback in checkpoint_callbacks:
            callback["init_args"]["save_last"] = True
        callbacks.append(
            {
                "class_path": "integrations.ninna.callbacks.RunEvidence",
                "init_args": {"output_dir": str(output)},
            }
        )
        if spec.get("source"):
            config["ckpt_path"] = variables["source"]
    Path(variables["config"]).write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    )
    command = bind(run["operation_contract"]["argv"], variables)
    if any("{" in arg or "}" in arg for arg in command):
        raise ValueError("Unresolved operation argument")
    env = dict(os.environ, NINNA_RUN_CONFIG=str(run_path), NINNA_OUTPUT=str(output))
    start = time.monotonic()
    process = subprocess.Popen(command, env=env, start_new_session=True)

    def stop(signum, frame):
        os.killpg(process.pid, signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    code = process.wait()
    if code:
        raise SystemExit(code)
    metrics_file = output / "metrics.json"
    metrics = json.loads(metrics_file.read_text()) if metrics_file.exists() else {}
    metrics["elapsed_time"] = time.monotonic() - start
    evidence_file = output / "evidence.json"
    evidence = json.loads(evidence_file.read_text()) if evidence_file.exists() else {}
    artifacts = []
    for path in sorted(output.rglob("*")):
        relative = path.relative_to(output)
        if (
            not path.is_file()
            or path.is_symlink()
            or "cache" in relative.parts
            or relative.parts[0] == "config"
        ):
            continue
        if (
            path.name
            in {
                "stdout.log",
                "stderr.log",
                "run.json",
                "container.json",
                "process-observation.json",
                "result.json",
            }
            or path.suffix == ".tmp"
        ):
            continue
        artifacts.append(
            {"path": str(relative), "kind": artifact_kind(path), "sha256": sha256(path)}
        )
    result = {
        "protocol_version": 1,
        "operation": operation,
        "metrics": metrics,
        "evidence": evidence,
        "artifacts": artifacts,
        "quality": {"status": "not_evaluated"},
    }
    temporary = output / "result.tmp"
    temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    temporary.replace(output / "result.json")


if __name__ == "__main__":
    main()
