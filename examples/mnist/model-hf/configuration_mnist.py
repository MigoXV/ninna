from transformers import PretrainedConfig


class MnistConfig(PretrainedConfig):
    model_type = "ninna_mnist_cnn"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.num_channels = 1
        self.image_size = 28
        self.num_labels = 10
