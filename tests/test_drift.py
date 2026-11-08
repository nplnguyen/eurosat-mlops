import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from app.drift import EmbeddingDriftDetector, population_stability_index  # noqa: E402

DIM, K = 64, 10


@pytest.fixture
def reference():
    rng = np.random.default_rng(0)
    # embeddings structurés : quelques directions dominantes + bruit
    basis = rng.normal(size=(5, DIM))
    return (rng.normal(size=(2000, 5)) @ basis + 0.1 * rng.normal(size=(2000, DIM))).astype(np.float32), basis


def make_detector(ref, **kw):
    return EmbeddingDriftDetector(ref, reference_pred_dist=[0.1] * 10, n_components=K,
                                  window_size=500, min_samples=100, **kw)


def test_not_ready_below_min_samples(reference):
    ref, _ = reference
    det = make_detector(ref)
    det.add(ref[:50], np.zeros(50, int), np.ones(50))
    r = det.compute()
    assert not r.ready and r.n_current == 50


def test_no_drift_on_same_distribution(reference):
    ref, basis = reference
    rng = np.random.default_rng(1)
    cur = rng.normal(size=(500, 5)) @ basis + 0.1 * rng.normal(size=(500, DIM))
    det = make_detector(ref)
    det.add(cur, rng.integers(0, 10, 500), np.full(500, 0.9))
    r = det.compute()
    assert r.ready
    assert not r.drift_detected
    assert r.prediction_psi < 0.1


def test_drift_detected_on_shift(reference):
    ref, basis = reference
    rng = np.random.default_rng(2)
    cur = rng.normal(loc=1.0, size=(500, 5)) @ basis + 0.1 * rng.normal(size=(500, DIM))
    det = make_detector(ref)
    det.add(cur, np.zeros(500, int), np.full(500, 0.5))  # toutes prédites classe 0
    r = det.compute()
    assert r.drift_detected
    assert r.share_drifted_components > 0
    assert r.min_p_value < r.threshold
    assert r.prediction_psi > 0.25


def test_window_is_bounded(reference):
    ref, _ = reference
    det = make_detector(ref)
    for _ in range(4):
        det.add(ref[:200], np.zeros(200, int), np.ones(200))
    assert det.compute().n_current == 500


def test_psi_properties():
    p = np.array([0.2, 0.3, 0.5])
    assert population_stability_index(p, p) == pytest.approx(0.0, abs=1e-9)
    assert population_stability_index(p, [0.5, 0.3, 0.2]) > 0
