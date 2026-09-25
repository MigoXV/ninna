from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import struct
import urllib.request

import yaml
from pathlib import Path

from ninna.storage.repository import now


def checksum(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest(root: Path):
    return {str(p.relative_to(root)): checksum(p) for p in sorted(root.rglob("*")) if p.is_file()}


def manifest_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


EXCLUDED = {".git", ".env", ".venv", "__pycache__", "node_modules", "outputs", ".pytest_cache"}


def snapshot(source: Path, destination: Path):
    files = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if any(part in EXCLUDED or part.startswith(".env.") for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"Workspace symlinks are not supported: {relative}")
        if path.is_file():
            files.append((path, relative))
    if not files:
        raise ValueError("Workspace is empty")
    contents = {str(relative): checksum(path) for path, relative in files}
    key = manifest_hash(contents)
    target = destination / key
    if not target.exists():
        temporary = destination / (key + ".tmp")
        temporary.mkdir(parents=True, exist_ok=True)
        for path, relative in files:
            output = temporary / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, output)
        if manifest(temporary) != contents:
            shutil.rmtree(temporary)
            raise ValueError("Workspace changed while creating snapshot; retry")
        temporary.rename(target)
    elif manifest(target) != contents:
        raise ValueError("Stored workspace snapshot has been modified")
    return key, target, contents


MNIST_FILES = {
    "train-images-idx3-ubyte.gz": "f68b3c2dcbeaaa9fbdd348bbdeb94873",
    "train-labels-idx1-ubyte.gz": "d53e105ee54ea40749a09fcbcd1e9432",
    "t10k-images-idx3-ubyte.gz": "9fb629c4189551a2d022fa330f9573f3",
    "t10k-labels-idx1-ubyte.gz": "ec29112dd5afa0611ce80d1b7f02629c",
}


def initialize(platform):
    settings, repo = platform.settings, platform.repo
    runtime = platform.docker.images.get(settings.runtime_image)
    repo.register(
        "runtime",
        {
            "name": "mnist-pytorch-runtime",
            "version": "v1",
            "image": settings.runtime_image,
            "image_id": runtime.id,
            "metadata": {
                "python": "3.10",
                "torch": "2.8.0",
                "torchvision": "0.23.0",
                "device": "cpu",
            },
        },
    )
    dataset = settings.root / "data-bin" / "mnist" / "v1"
    raw = dataset / "MNIST" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for filename, expected in MNIST_FILES.items():
        compressed = raw / filename
        if not compressed.exists():
            request = urllib.request.Request(
                "https://ossci-datasets.s3.amazonaws.com/mnist/" + filename
            )
            temporary = compressed.with_suffix(".download")
            with (
                urllib.request.urlopen(request, timeout=120) as response,
                temporary.open("wb") as out,
            ):
                shutil.copyfileobj(response, out)
            temporary.rename(compressed)
        if hashlib.md5(compressed.read_bytes()).hexdigest() != expected:
            raise ValueError(f"MNIST source checksum failed: {filename}")
        payload = gzip.decompress(compressed.read_bytes())
        magic, count = struct.unpack(">II", payload[:8])
        expected_count = 60000 if filename.startswith("train") else 10000
        if count != expected_count:
            raise ValueError(f"Invalid sample count: {filename}")
        if "images" in filename:
            if (
                magic != 2051
                or struct.unpack(">II", payload[8:16]) != (28, 28)
                or len(payload) != 16 + count * 784
            ):
                raise ValueError(f"Invalid MNIST image data: {filename}")
        elif magic != 2049 or len(payload) != 8 + count or max(payload[8:]) > 9:
            raise ValueError(f"Invalid MNIST labels: {filename}")
        extracted = raw / filename.removesuffix(".gz")
        if not extracted.exists():
            extracted.write_bytes(payload)
    files = manifest(dataset)
    repo.register(
        "dataset",
        {
            "name": "mnist",
            "version": "v1",
            "path": str(dataset),
            "checksum": manifest_hash(files),
            "files": files,
            "train_split": {"name": "train", "count": 60000},
            "test_split": {"name": "test", "count": 10000},
            "metadata": {
                "shape": [1, 28, 28],
                "classes": 10,
                "format": "torchvision.MNIST",
                "source": "MNIST",
            },
        },
    )
    model_path = settings.root / "model-bin" / "mnist-cnn" / "v1"
    source = settings.root / "examples" / "mnist" / "model"
    if not model_path.exists():
        shutil.copytree(source, model_path)
    repo.register(
        "model",
        {
            "name": "mnist-cnn",
            "version": "v1",
            "path": str(model_path),
            "architecture": {
                "class": "MnistCNN",
                "entrypoint": "model.py",
                "description": "Conv 32 → ReLU → Pool → Conv 64 → ReLU → Pool → Linear 128 → Linear 10",
            },
            "initialization": {"seed": 42, "method": "pytorch_default"},
            "initial_checkpoint": None,
            "parameter_count": 421642,
            "files": manifest(model_path),
            "checksum": manifest_hash(manifest(model_path)),
            "metadata": {"input": [1, 28, 28], "output": 10},
        },
    )
    for recipe_path in sorted((settings.root / "examples" / "mnist" / "recipes").glob("*.yaml")):
        recipe = yaml.safe_load(recipe_path.read_text())
        repo.register("recipe", recipe)
        repo.register(
            "recipe",
            {**recipe, "version": "quick-v1", "epochs": 1, "metadata": {"profile": "quick"}},
        )
    repo.register(
        "workspace",
        {
            "name": "mnist",
            "version": "v1",
            "path": str(settings.root / "examples" / "mnist" / "workspace"),
            "entrypoint": "train.py",
            "metadata": {"description": "MNIST training workspace"},
        },
    )
    return {"status": "ready", "initialized_at": now()}
