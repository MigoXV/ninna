from torch import nn
from transformers import PreTrainedModel
from transformers.modeling_outputs import ImageClassifierOutput

from .configuration_mnist import MnistConfig


class MnistForImageClassification(PreTrainedModel):
    config_class = MnistConfig
    main_input_name = "pixel_values"

    def __init__(self, config):
        super().__init__(config)
        self.features = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(), nn.Linear(64 * 7 * 7, 128), nn.ReLU(), nn.Linear(128, 10)
        )
        self.post_init()

    def _init_weights(self, module):
        # Keep PyTorch initialization identical to the certified v1 architecture.
        pass

    def forward(self, pixel_values, **kwargs):
        return ImageClassifierOutput(logits=self.classifier(self.features(pixel_values)))
