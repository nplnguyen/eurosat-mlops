"""Service one-shot lancé par docker compose.

Si aucun modèle `champion` n'existe dans le registre MLflow, on lance un
entraînement court (sous-échantillon, peu d'époques) afin que le système
soit fonctionnel dès le premier `make up`. Les entraînements "sérieux" se
font ensuite avec `make train`.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import requests
from mlflow.tracking import MlflowClient

from training.config import REGISTERED_MODEL_NAME


def wait_for_mlflow(uri: str, timeout: int = 180) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{uri}/health", timeout=3).ok:
                return
        except requests.RequestException:
            pass
        print("En attente de MLflow…")
        time.sleep(3)
    raise SystemExit("MLflow injoignable")


def main():
    uri = os.environ["MLFLOW_TRACKING_URI"]
    wait_for_mlflow(uri)
    try:
        v = MlflowClient().get_model_version_by_alias(REGISTERED_MODEL_NAME, "champion")
        print(f"Champion déjà présent (v{v.version}) : rien à faire.")
        return
    except Exception:
        print("Aucun champion : entraînement de bootstrap.")
    cmd = [
        sys.executable, "-m", "training.train",
        "--arch", os.getenv("BOOTSTRAP_ARCH", "resnet18"),
        "--epochs", os.getenv("BOOTSTRAP_EPOCHS", "3"),
        "--subset-fraction", os.getenv("BOOTSTRAP_SUBSET", "0.3"),
        "--min-f1", os.getenv("BOOTSTRAP_MIN_F1", "0.70"),
        "--num-workers", "2",
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
