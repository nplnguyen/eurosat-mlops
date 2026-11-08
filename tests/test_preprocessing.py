import io
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from app.preprocessing import InvalidImage, load_image, preprocess  # noqa: E402

MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def png_bytes(color=(10, 120, 200), size=(64, 64), mode="RGB"):
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, "PNG")
    return buf.getvalue()


def test_shape_and_dtype():
    x = preprocess(load_image(png_bytes()), 128, MEAN, STD)
    assert x.shape == (3, 128, 128) and x.dtype == np.float32


def test_normalisation_matches_torchvision_formula():
    x = preprocess(load_image(png_bytes((255, 0, 128))), 32, MEAN, STD)
    expected = (np.array([255, 0, 128]) / 255.0 - MEAN) / STD
    np.testing.assert_allclose(x[:, 0, 0], expected, rtol=1e-5)


def test_grayscale_and_rgba_are_converted():
    assert preprocess(load_image(png_bytes(128, mode="L")), 64, MEAN, STD).shape[0] == 3
    assert preprocess(load_image(png_bytes((1, 2, 3, 4), mode="RGBA")), 64, MEAN, STD).shape[0] == 3


def test_invalid_file_raises():
    with pytest.raises(InvalidImage):
        load_image(b"ceci n'est pas une image")
