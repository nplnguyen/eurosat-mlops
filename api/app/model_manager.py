"""Chargement du modèle depuis le Model Registry MLflow + rechargement à chaud.

Le service ne connaît qu'un *alias* (`champion` ou `challenger`). Un thread
interroge périodiquement le registre ; si l'alias pointe vers une nouvelle
version, les artefacts sont téléchargés puis le modèle est remplacé de façon
atomique (aucune requête n'est perdue pendant la bascule).
"""
from __future__ import annotations

import json
import logging
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort

from app.config import Settings
from app.drift import EmbeddingDriftDetector

log = logging.getLogger(__name__)


@dataclass
class ModelBundle:
    session: ort.InferenceSession
    labels: list[str]
    img_size: int
    mean: np.ndarray
    std: np.ndarray
    version: str
    alias: str
    variant: str
    drift: EmbeddingDriftDetector

    def predict(self, batch: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        logits, emb = self.session.run(["logits", "embedding"], {"input": batch})
        z = logits - logits.max(axis=1, keepdims=True)
        probs = np.exp(z) / np.exp(z).sum(axis=1, keepdims=True)
        return probs, emb


class ModelManager:
    def __init__(self, settings: Settings, redis_client=None):
        self.s = settings
        self.redis = redis_client
        self._bundle: ModelBundle | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.last_error: str | None = None

    # ------------------------------------------------------------------ #
    @property
    def bundle(self) -> ModelBundle | None:
        return self._bundle

    @property
    def ready(self) -> bool:
        return self._bundle is not None

    # ------------------------------------------------------------------ #
    def _resolve_mlflow(self) -> tuple[str, str, str]:
        """Retourne (version, run_id, alias effectivement utilisé)."""
        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(self.s.mlflow_tracking_uri)
        client = MlflowClient()
        for alias in dict.fromkeys([self.s.model_alias, self.s.model_fallback_alias]):
            try:
                mv = client.get_model_version_by_alias(self.s.model_name, alias)
                return str(mv.version), mv.run_id, alias
            except Exception:  # alias absent
                continue
        raise RuntimeError(f"Aucun alias {self.s.model_alias}/{self.s.model_fallback_alias} dans le registre")

    def _download(self, run_id: str, version: str) -> Path:
        import mlflow

        dst = Path(self.s.model_cache_dir) / f"v{version}"
        if not (dst / "deploy" / "labels.json").exists():
            shutil.rmtree(dst, ignore_errors=True)
            dst.mkdir(parents=True, exist_ok=True)
            mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path="deploy", dst_path=str(dst))
        return dst / "deploy"

    def _build(self, model_dir: Path, version: str, alias: str) -> ModelBundle:
        variant = self.s.model_variant
        onnx_path = model_dir / f"model_{variant}.onnx"
        if not onnx_path.exists():
            variant, onnx_path = "fp32", model_dir / "model_fp32.onnx"
        so = ort.SessionOptions()
        so.intra_op_num_threads = self.s.ort_threads
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        session = ort.InferenceSession(str(onnx_path), so, providers=["CPUExecutionProvider"])

        labels = json.loads((model_dir / "labels.json").read_text())
        pre = json.loads((model_dir / "preprocessing.json").read_text())
        reference = np.load(model_dir / "reference_embeddings.npy")
        drift = EmbeddingDriftDetector(
            reference,
            reference_pred_dist=pre.get("reference_prediction_distribution"),
            n_components=self.s.drift_n_components,
            alpha=self.s.drift_alpha,
            window_size=self.s.drift_window_size,
            min_samples=self.s.drift_min_samples,
            redis_client=self.redis,
            redis_key=f"drift:{self.s.model_name}:v{version}",
        )
        return ModelBundle(
            session=session, labels=labels, img_size=int(pre["img_size"]),
            mean=np.array(pre["mean"], np.float32), std=np.array(pre["std"], np.float32),
            version=version, alias=alias, variant=variant, drift=drift,
        )

    # ------------------------------------------------------------------ #
    def refresh(self) -> bool:
        """Charge / recharge le modèle si nécessaire. Retourne True si changement."""
        try:
            if self.s.model_source == "local":
                if self._bundle is not None:
                    return False
                d = Path(self.s.local_model_dir)
                version = (d / "VERSION").read_text().strip() if (d / "VERSION").exists() else "local"
                bundle = self._build(d, version, "local")
            else:
                version, run_id, alias = self._resolve_mlflow()
                current = self._bundle
                if current and current.version == version and current.alias == alias:
                    return False
                bundle = self._build(self._download(run_id, version), version, alias)
            with self._lock:
                old = self._bundle
                self._bundle = bundle
            self.last_error = None
            log.info("Modèle chargé : v%s (%s, %s) — précédent : %s",
                     bundle.version, bundle.alias, bundle.variant, old.version if old else None)
            return True
        except Exception as exc:  # le service reste up avec l'ancien modèle
            self.last_error = str(exc)
            log.warning("Échec du chargement du modèle : %s", exc)
            return False

    def start_background_refresh(self) -> None:
        def loop():
            while not self._stop.wait(self.s.model_refresh_seconds if self.ready else 5):
                self.refresh()

        threading.Thread(target=loop, name="model-refresh", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
