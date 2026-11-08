"""Détection de data drift sur les embeddings du modèle.

Méthode (inspirée de Rabanser et al., 2019, "Failing Loudly") :
  1. Réduction de dimension : PCA ajustée sur les embeddings de référence
     (jeu de validation) -> k composantes.
  2. Test de Kolmogorov-Smirnov à deux échantillons sur chaque composante,
     entre la référence et la fenêtre glissante des requêtes de production.
  3. Correction de Bonferroni (alpha / k) : drift si au moins une
     composante rejette H0 (« même distribution »).

En complément on suit un drift de *prédiction* (PSI entre la distribution
des classes prédites en production et en référence) et la confiance
moyenne, qui chute souvent quand les entrées sortent du domaine.

Le module ne dépend que de numpy/scipy : il est testable sans modèle.
"""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import asdict, dataclass

import numpy as np
from scipy.stats import ks_2samp


@dataclass
class DriftReport:
    n_reference: int
    n_current: int
    ready: bool
    drift_detected: bool = False
    share_drifted_components: float = 0.0
    min_p_value: float = 1.0
    p_values: list[float] | None = None
    threshold: float = 0.0
    prediction_psi: float = 0.0
    mean_confidence: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def population_stability_index(expected: np.ndarray, actual: np.ndarray, eps: float = 1e-4) -> float:
    """PSI = sum((a - e) * ln(a / e)). Usage courant : < 0.1 stable, > 0.25 fort drift."""
    e = np.clip(np.asarray(expected, dtype=float), eps, None)
    a = np.clip(np.asarray(actual, dtype=float), eps, None)
    e, a = e / e.sum(), a / a.sum()
    return float(np.sum((a - e) * np.log(a / e)))


class _MemoryWindow:
    def __init__(self, size: int):
        self._emb: deque = deque(maxlen=size)
        self._meta: deque = deque(maxlen=size)
        self._lock = threading.Lock()

    def push(self, embs: np.ndarray, preds: np.ndarray, confs: np.ndarray) -> None:
        with self._lock:
            for e, p, c in zip(embs, preds, confs):
                self._emb.append(np.asarray(e, dtype=np.float32))
                self._meta.append((int(p), float(c)))

    def read(self):
        with self._lock:
            if not self._emb:
                return np.empty((0, 0), np.float32), np.empty(0, int), np.empty(0)
            emb = np.stack(self._emb)
            preds = np.array([m[0] for m in self._meta])
            confs = np.array([m[1] for m in self._meta])
        return emb, preds, confs


class _RedisWindow:
    """Fenêtre partagée entre réplicas : liste Redis de vecteurs float32."""

    def __init__(self, client, key: str, size: int, dim: int):
        self.r, self.key, self.size, self.dim = client, key, size, dim

    def push(self, embs, preds, confs) -> None:
        pipe = self.r.pipeline()
        for e, p, c in zip(embs, preds, confs):
            payload = np.concatenate([[p, c], np.asarray(e, np.float32)]).astype(np.float32).tobytes()
            pipe.lpush(self.key, payload)
        pipe.ltrim(self.key, 0, self.size - 1)
        pipe.execute()

    def read(self):
        raw = self.r.lrange(self.key, 0, self.size - 1)
        if not raw:
            return np.empty((0, self.dim), np.float32), np.empty(0, int), np.empty(0)
        arr = np.stack([np.frombuffer(b, dtype=np.float32) for b in raw])
        return arr[:, 2:], arr[:, 0].astype(int), arr[:, 1]


class EmbeddingDriftDetector:
    def __init__(
        self,
        reference: np.ndarray,
        reference_pred_dist: list[float] | None = None,
        n_components: int = 10,
        alpha: float = 0.05,
        window_size: int = 1000,
        min_samples: int = 100,
        redis_client=None,
        redis_key: str = "drift:window",
    ):
        reference = np.asarray(reference, dtype=np.float64)
        self.n_ref = len(reference)
        self.alpha = alpha
        self.min_samples = min_samples
        self.n_components = int(min(n_components, reference.shape[1], self.n_ref))

        # PCA par SVD sur la référence centrée
        self.mean_ = reference.mean(axis=0)
        _, _, vt = np.linalg.svd(reference - self.mean_, full_matrices=False)
        self.components_ = vt[: self.n_components]
        self.ref_proj = self.transform(reference)
        self.ref_pred_dist = (
            np.asarray(reference_pred_dist) if reference_pred_dist is not None else None
        )

        if redis_client is not None:
            self.window = _RedisWindow(redis_client, redis_key, window_size, reference.shape[1])
        else:
            self.window = _MemoryWindow(window_size)
        self.last_report = DriftReport(self.n_ref, 0, ready=False)

    def transform(self, x: np.ndarray) -> np.ndarray:
        return (np.asarray(x, dtype=np.float64) - self.mean_) @ self.components_.T

    def add(self, embeddings: np.ndarray, preds: np.ndarray, confidences: np.ndarray) -> None:
        self.window.push(embeddings, preds, confidences)

    def compute(self) -> DriftReport:
        emb, preds, confs = self.window.read()
        n = len(emb)
        if n < self.min_samples:
            self.last_report = DriftReport(self.n_ref, n, ready=False)
            return self.last_report

        cur = self.transform(emb)
        p_values = [float(ks_2samp(self.ref_proj[:, i], cur[:, i]).pvalue) for i in range(self.n_components)]
        threshold = self.alpha / self.n_components  # Bonferroni
        drifted = [p < threshold for p in p_values]

        psi = 0.0
        if self.ref_pred_dist is not None:
            k = len(self.ref_pred_dist)
            psi = population_stability_index(self.ref_pred_dist, np.bincount(preds, minlength=k)[:k])

        self.last_report = DriftReport(
            n_reference=self.n_ref,
            n_current=n,
            ready=True,
            drift_detected=any(drifted),
            share_drifted_components=float(np.mean(drifted)),
            min_p_value=float(min(p_values)),
            p_values=p_values,
            threshold=threshold,
            prediction_psi=psi,
            mean_confidence=float(np.mean(confs)),
        )
        return self.last_report
