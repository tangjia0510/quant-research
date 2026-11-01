"""Small CPU PyTorch model used to verify custom-model execution."""
from torch import nn


class TinyModel(nn.Module):
    def __init__(self, num_features):
        super().__init__()
        self.layers = nn.Sequential(nn.Linear(num_features, 8), nn.Tanh(), nn.Linear(8, 1))

    def forward(self, features):
        return self.layers(features).squeeze(-1)


def build_model(num_features):
    return TinyModel(num_features)
