from torchvision.datasets import MNIST
from torchvision.transforms import Compose, Normalize, ToTensor
from torch.utils.data import DataLoader


def loaders(root, batch_size, seed):
    import torch

    transform = Compose([ToTensor(), Normalize((0.1307,), (0.3081,))])
    train = MNIST(root, train=True, transform=transform, download=False)
    test = MNIST(root, train=False, transform=transform, download=False)
    if len(train) != 60000 or len(test) != 10000:
        raise ValueError("Dataset split counts do not match the registered MNIST asset")
    generator = torch.Generator().manual_seed(seed)
    return (
        DataLoader(train, batch_size=batch_size, shuffle=True, generator=generator, num_workers=0),
        DataLoader(test, batch_size=512, shuffle=False, num_workers=0),
        DataLoader(torch.utils.data.Subset(train, range(2048)), batch_size=512, shuffle=False),
    )
