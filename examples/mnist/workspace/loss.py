from torch import nn


def build_loss(name):
    if name != "CrossEntropyLoss":
        raise ValueError(f"Unsupported recipe loss: {name}")
    return nn.CrossEntropyLoss()
