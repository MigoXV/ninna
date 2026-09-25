import numpy as np
import torch
from transformers.image_processing_utils import BaseImageProcessor, BatchFeature


class MnistImageProcessor(BaseImageProcessor):
    model_input_names = ["pixel_values"]

    def __init__(self, image_mean=0.1307, image_std=0.3081, **kwargs):
        super().__init__(**kwargs)
        self.image_mean = image_mean
        self.image_std = image_std

    def preprocess(self, images, return_tensors="pt", **kwargs):
        if not isinstance(images, (list, tuple)):
            images = [images]
        arrays = [np.array(image.convert("L"), dtype=np.uint8, copy=True) for image in images]
        if not arrays or any(array.shape != (28, 28) for array in arrays):
            raise ValueError("Expected a non-empty batch of 28 x 28 PIL images")
        pixels = torch.from_numpy(np.stack(arrays)).unsqueeze(1).float().div(255)
        pixels.sub_(self.image_mean).div_(self.image_std)
        return BatchFeature({"pixel_values": pixels}, tensor_type=return_tensors)
