import json
import time
from pathlib import Path

import torch

from checkpoint import atomic_json, load_model, save_checkpoint, state_hash
from exporting import export_model
from data import loaders
from loss import build_loss


@torch.no_grad()
def evaluate(model, loader, criterion):
    model.eval()
    total_loss, correct, count = 0.0, 0, 0
    for images, labels in loader:
        logits = model(images).logits
        total_loss += criterion(logits, labels).item() * len(labels)
        correct += (logits.argmax(1) == labels).sum().item()
        count += len(labels)
    return total_loss / count, correct / count


def train(config):
    started = time.monotonic()
    recipe = config["assets"]["recipe"]
    if recipe["training_loop"] != "supervised_classification":
        raise ValueError("Unsupported recipe.training_loop")
    for field in ("epochs", "batch_size", "gradient_accumulation"):
        if not isinstance(recipe[field], int) or recipe[field] < 1:
            raise ValueError(f"recipe.{field} must be a positive integer")
    model_asset = config["assets"]["model"]
    resources = config["execution_spec"]["resources"]
    torch.set_num_threads(resources["cpu_threads"])
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(model_asset["initialization"]["seed"])
    model = load_model(model_asset)
    if sum(parameter.numel() for parameter in model.parameters()) != model_asset["parameter_count"]:
        raise ValueError("Model parameter count does not match registered asset")
    initial_hash = state_hash(model)
    train_loader, test_loader, probe_loader = loaders(
        "/dataset", recipe["batch_size"], recipe["seed"]
    )
    criterion = build_loss(recipe["loss"])
    initial_loss, _ = evaluate(model, probe_loader, criterion)
    freeze = recipe.get("freeze", {})
    prefixes = freeze.get("prefixes", [])
    for name, parameter in model.named_parameters():
        if any(name.startswith(prefix) for prefix in prefixes):
            parameter.requires_grad_(False)
    optimizer_class = {"Adam": torch.optim.Adam, "SGD": torch.optim.SGD}[
        recipe["optimizer"]["name"]
    ]
    optimizer = optimizer_class(model.parameters(), **recipe["optimizer"]["params"])
    scheduler_config = recipe.get("scheduler")
    scheduler = None
    if scheduler_config:
        if scheduler_config["name"] != "StepLR":
            raise ValueError("Only StepLR is supported")
        scheduler = torch.optim.lr_scheduler.StepLR(optimizer, **scheduler_config["params"])
    output = Path("/output")
    events = output / "events.jsonl"
    print(
        json.dumps(
            {
                "event": "training_started",
                "initial_model_hash": initial_hash,
                "initial_loss": initial_loss,
                "optimizer": recipe["optimizer"],
            }
        ),
        flush=True,
    )
    history = []
    accumulation = recipe["gradient_accumulation"]
    for epoch in range(1, recipe["epochs"] + 1):
        if freeze.get("unfreeze_epoch") == epoch:
            for parameter in model.parameters():
                parameter.requires_grad_(True)
        model.train()
        total_loss, count = 0.0, 0
        optimizer.zero_grad(set_to_none=True)
        for step, (images, labels) in enumerate(train_loader):
            loss = criterion(model(images).logits, labels)
            # The last accumulation group can contain fewer batches.
            group_size = min(
                accumulation, len(train_loader) - (step // accumulation) * accumulation
            )
            (loss / group_size).backward()
            if (step + 1) % accumulation == 0 or step + 1 == len(train_loader):
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
            total_loss += loss.item() * len(labels)
            count += len(labels)
        test_loss, accuracy = evaluate(model, test_loader, criterion)
        event = {
            "epoch": epoch,
            "train_loss": total_loss / count,
            "test_loss": test_loss,
            "test_accuracy": accuracy,
            "lr": optimizer.param_groups[0]["lr"],
            "elapsed_time": time.monotonic() - started,
        }
        history.append(event)
        with events.open("a") as stream:
            stream.write(json.dumps(event) + "\n")
        print(json.dumps(event), flush=True)
        if scheduler:
            scheduler.step()
    final_loss, _ = evaluate(model, probe_loader, criterion)
    trained_hash = state_hash(model)
    save_checkpoint(model, model_asset["architecture"], config["run_id"], output / "checkpoint.pt")
    export_model(model, output)
    metrics = {
        "train_loss": [e["train_loss"] for e in history],
        "final_train_loss": history[-1]["train_loss"],
        "test_loss": history[-1]["test_loss"],
        "test_accuracy": history[-1]["test_accuracy"],
        "epochs": recipe["epochs"],
        "elapsed_time": time.monotonic() - started,
        "initial_loss": initial_loss,
        "final_loss": final_loss,
        "initial_model_hash": initial_hash,
        "trained_model_hash": trained_hash,
        "history": history,
    }
    atomic_json(output / "metrics.json", metrics)
    if initial_hash == trained_hash or final_loss >= initial_loss:
        raise RuntimeError("Training validation failed: unchanged weights or loss did not decrease")
    print("Training complete. Checkpoint and metrics saved.", flush=True)
