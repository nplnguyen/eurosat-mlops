"""Prétraitement identique à celui de l'entraînement (torchvision) mais en
numpy/PIL pur : l'image de production n'embarque pas PyTorch (~1 Go en moins)."""
from __future__ import annotations

import io

import numpy as np
from PIL import Image, UnidentifiedImageError


class InvalidImage(ValueError):
    pass


def load_image(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImage("Fichier image illisible") from exc
    return img.convert("RGB")


def preprocess(img: Image.Image, size: int, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    """PIL -> tableau (3, H, W) float32 normalisé."""
    img = img.resize((size, size), Image.BILINEAR)
    x = np.asarray(img, dtype=np.float32) / 255.0
    x = (x - mean) / std
    return x.transpose(2, 0, 1).astype(np.float32)
