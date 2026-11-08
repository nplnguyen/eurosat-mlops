"""Quantization statique post-entraînement (PTQ) INT8 avec onnxruntime.

On utilise le format QDQ (QuantizeLinear / DequantizeLinear), recommandé par
onnxruntime pour les CNN, avec des poids quantifiés par canal. Les plages
d'activation sont calibrées sur un échantillon du jeu de validation
(méthode MinMax).

Utilisable seul :
    python -m training.quantize model_fp32.onnx model_int8.onnx --calib calib.npy
"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import numpy as np
from onnxruntime.quantization import (
    CalibrationDataReader,
    CalibrationMethod,
    QuantFormat,
    QuantType,
    quantize_static,
)
from onnxruntime.quantization.shape_inference import quant_pre_process


class NumpyCalibrationReader(CalibrationDataReader):
    def __init__(self, data: np.ndarray, input_name: str = "input", batch_size: int = 16):
        self._batches = iter(
            [{input_name: data[i : i + batch_size]} for i in range(0, len(data), batch_size)]
        )

    def get_next(self):
        return next(self._batches, None)


def quantize_int8(fp32_path: str, int8_path: str, calibration_data: np.ndarray) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        prep = str(Path(tmp) / "prep.onnx")
        # Fusion BN/Conv + inférence de formes : améliore la qualité de la PTQ
        quant_pre_process(fp32_path, prep, skip_symbolic_shape=True)
        quantize_static(
            model_input=prep,
            model_output=int8_path,
            calibration_data_reader=NumpyCalibrationReader(calibration_data),
            quant_format=QuantFormat.QDQ,
            per_channel=True,
            weight_type=QuantType.QInt8,
            activation_type=QuantType.QUInt8,
            calibrate_method=CalibrationMethod.MinMax,
        )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("fp32")
    ap.add_argument("int8")
    ap.add_argument("--calib", required=True, help="Fichier .npy (N,3,H,W) prétraité")
    a = ap.parse_args()
    quantize_int8(a.fp32, a.int8, np.load(a.calib).astype(np.float32))
    print(f"Modèle quantifié écrit dans {a.int8}")
