"""Tests d'intégration de l'API avec un mini-modèle ONNX factice.

Le modèle factice respecte le même contrat que le vrai (entrée `input`,
sorties `logits` et `embedding`) : on teste toute la chaîne HTTP -> auth ->
prétraitement -> onnxruntime -> drift -> traçage d'usage, sans PyTorch.
"""
import io
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("fastapi")
onnx = pytest.importorskip("onnx")
from onnx import TensorProto, helper  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

ADMIN_KEY = "eus_test-admin-key"
LABELS = ["AnnualCrop", "Forest", "HerbaceousVegetation", "Highway", "Industrial",
          "Pasture", "PermanentCrop", "Residential", "River", "SeaLake"]


def build_dummy_model(model_dir: Path, size: int = 32):
    """input (N,3,H,W) -> GlobalAveragePool -> Flatten = embedding (N,3) -> MatMul -> logits (N,10)."""
    w = np.random.default_rng(0).normal(size=(3, 10)).astype(np.float32)
    nodes = [
        helper.make_node("GlobalAveragePool", ["input"], ["pooled"]),
        helper.make_node("Flatten", ["pooled"], ["embedding"]),
        helper.make_node("MatMul", ["embedding", "W"], ["logits"]),
    ]
    graph = helper.make_graph(
        nodes, "dummy",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, ["N", 3, size, size])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["N", 10]),
         helper.make_tensor_value_info("embedding", TensorProto.FLOAT, ["N", 3])],
        [helper.make_tensor("W", TensorProto.FLOAT, w.shape, w.flatten())],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8
    model_dir.mkdir(parents=True, exist_ok=True)
    onnx.save(model, model_dir / "model_int8.onnx")
    (model_dir / "labels.json").write_text(json.dumps(LABELS))
    (model_dir / "preprocessing.json").write_text(json.dumps({
        "img_size": size, "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225],
        "reference_prediction_distribution": [0.1] * 10,
    }))
    np.save(model_dir / "reference_embeddings.npy", np.random.default_rng(1).normal(size=(300, 3)).astype(np.float32))
    (model_dir / "VERSION").write_text("test-1")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("api")
    build_dummy_model(tmp / "model")
    os.environ.update({
        "MODEL_SOURCE": "local", "LOCAL_MODEL_DIR": str(tmp / "model"),
        "DATABASE_URL": f"sqlite:///{tmp / 'test.db'}", "REDIS_URL": "",
        "ADMIN_API_KEY": ADMIN_KEY, "API_KEY_PEPPER": "test-pepper",
        "DRIFT_MIN_SAMPLES": "20", "DRIFT_CHECK_SECONDS": "3600",
    })
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def img(color=(30, 140, 60)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, "PNG")
    return ("tile.png", buf.getvalue(), "image/png")


def test_health_is_public(client):
    assert client.get("/health").status_code == 200
    assert client.get("/health/ready").json()["model_version"] == "test-1"


def test_predict_requires_api_key(client):
    r = client.post("/v1/predict", files={"file": img()})
    assert r.status_code == 401
    assert client.post("/v1/predict", files={"file": img()}, headers={"X-API-Key": "eus_fausse"}).status_code == 401


def test_admin_creates_user_and_user_predicts(client):
    r = client.post("/admin/users", json={"name": "alice", "quota_per_minute": 1000},
                    headers={"X-API-Key": ADMIN_KEY})
    assert r.status_code == 201, r.text
    key = r.json()["api_key"]
    assert key.startswith("eus_")

    r = client.post("/v1/predict", files={"file": img()}, headers={"X-API-Key": key})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"] in LABELS
    assert abs(sum(body["probabilities"].values()) - 1) < 1e-3
    assert r.headers["X-Model-Version"] == "test-1"

    # Authorization: Bearer est aussi accepté
    assert client.post("/v1/predict", files={"file": img()},
                       headers={"Authorization": f"Bearer {key}"}).status_code == 200


def test_non_admin_cannot_use_admin_routes(client):
    r = client.post("/admin/users", json={"name": "bob"}, headers={"X-API-Key": ADMIN_KEY})
    key = r.json()["api_key"]
    assert client.get("/admin/users", headers={"X-API-Key": key}).status_code == 403


def test_rate_limit(client):
    r = client.post("/admin/users", json={"name": "limited", "quota_per_minute": 2},
                    headers={"X-API-Key": ADMIN_KEY})
    h = {"X-API-Key": r.json()["api_key"]}
    codes = [client.get("/v1/model", headers=h).status_code for _ in range(4)]
    assert codes[:2] == [200, 200] and 429 in codes[2:]


def test_batch_and_usage_tracking(client):
    r = client.post("/admin/users", json={"name": "carol"}, headers={"X-API-Key": ADMIN_KEY})
    h = {"X-API-Key": r.json()["api_key"]}
    r = client.post("/v1/predict/batch", files=[("files", img()), ("files", img((200, 200, 200)))], headers=h)
    assert r.status_code == 200 and len(r.json()["predictions"]) == 2

    from app.usage import recorder

    time.sleep(0.1)
    recorder.flush()
    usage = client.get("/v1/me/usage", headers=h).json()
    assert usage["total_images"] >= 2


def test_invalid_image_returns_422(client):
    r = client.post("/v1/predict", files={"file": ("x.png", b"not an image", "image/png")},
                    headers={"X-API-Key": ADMIN_KEY})
    assert r.status_code == 422


def test_drift_endpoint(client):
    h = {"X-API-Key": ADMIN_KEY}
    for i in range(25):
        client.post("/v1/predict", files={"file": img((i * 10 % 255, 50, 50))}, headers=h)
    report = client.get("/v1/drift", headers=h).json()
    assert report["ready"] and "drift_detected" in report
