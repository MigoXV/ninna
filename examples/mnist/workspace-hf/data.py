import torch
from datasets import load_from_disk
from torch.utils.data import DataLoader, Subset
from transformers import AutoImageProcessor


def loaders(root, batch_size, seed):
    dataset = load_from_disk(root)
    if len(dataset["train"]) != 60000 or len(dataset["test"]) != 10000:
        raise ValueError("Dataset split counts do not match the registered MNIST asset")
    processor = AutoImageProcessor.from_pretrained(
        "/model", trust_remote_code=True, local_files_only=True, use_fast=False
    )

    def collate(rows):
        return (
            processor([row["image"] for row in rows], return_tensors="pt")["pixel_values"],
            torch.tensor([row["label"] for row in rows], dtype=torch.long),
        )

    return (
        DataLoader(
            dataset["train"],
            batch_size=batch_size,
            shuffle=True,
            generator=torch.Generator().manual_seed(seed),
            collate_fn=collate,
        ),
        DataLoader(dataset["test"], batch_size=512, collate_fn=collate),
        DataLoader(Subset(dataset["train"], range(2048)), batch_size=512, collate_fn=collate),
    )
