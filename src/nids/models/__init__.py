"""Model registry: name-keyed factories for classifiers benchmarked by the
training pipeline."""

from nids.models.registry import MODEL_REGISTRY, build_model

__all__ = ["MODEL_REGISTRY", "build_model"]
