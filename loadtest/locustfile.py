"""Test de charge du service en production (Locust).

    export EUROSAT_API_KEY=eus_...
    locust -f loadtest/locustfile.py --host http://<IP_VM>/api \
           --headless -u 100 -r 10 -t 5m --csv results/prod_100u --html results/prod_100u.html

Profil simulé :
  - 85 % : prédiction d'une image
  - 8 %  : prédiction par lot (8 images)
  - 5 %  : consultation de son usage
  - 2 %  : requête sans clé (doit renvoyer 401 : vérifie la sécurité sous charge)

Les images proviennent de `loadtest/images/` (échantillon EuroSAT déposé par
`make sample-images`) ; à défaut, des images synthétiques 64x64 sont générées.
"""
from __future__ import annotations

import io
import os
import random
from pathlib import Path

from locust import HttpUser, between, events, task

API_KEYS = [k for k in os.getenv("EUROSAT_API_KEYS", os.getenv("EUROSAT_API_KEY", "")).split(",") if k]
IMAGES: list[tuple[str, bytes]] = []


@events.init.add_listener
def load_images(environment, **_):
    folder = Path(__file__).parent / "images"
    for p in sorted(folder.glob("**/*"))[:500]:
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif"}:
            IMAGES.append((p.name, p.read_bytes()))
    if not IMAGES:
        from PIL import Image
        import numpy as np

        rng = np.random.default_rng(0)
        for i in range(50):
            buf = io.BytesIO()
            Image.fromarray(rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)).save(buf, "PNG")
            IMAGES.append((f"synthetic_{i}.png", buf.getvalue()))
    if not API_KEYS:
        raise SystemExit("Définir EUROSAT_API_KEY (ou EUROSAT_API_KEYS=k1,k2,...)")
    print(f"{len(IMAGES)} images chargées, {len(API_KEYS)} clé(s) d'API")


class EuroSATUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        # Chaque utilisateur virtuel prend une clé : l'usage est tracé par clé
        self.client.headers["X-API-Key"] = random.choice(API_KEYS)

    @task(85)
    def predict(self):
        name, data = random.choice(IMAGES)
        with self.client.post("/v1/predict", files={"file": (name, data, "image/png")},
                              name="/v1/predict", catch_response=True) as r:
            if r.status_code == 200:
                track = r.headers.get("X-Deployment-Track", "?")
                r.request_meta["name"] = f"/v1/predict [{track}]"
                r.success()
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(8)
    def predict_batch(self):
        files = [("files", (n, d, "image/png")) for n, d in random.sample(IMAGES, k=min(8, len(IMAGES)))]
        self.client.post("/v1/predict/batch", files=files, name="/v1/predict/batch")

    @task(5)
    def my_usage(self):
        self.client.get("/v1/me/usage")

    @task(2)
    def unauthorized(self):
        name, data = random.choice(IMAGES)
        with self.client.post("/v1/predict", files={"file": (name, data, "image/png")},
                              headers={"X-API-Key": ""}, name="/v1/predict [sans clé]",
                              catch_response=True) as r:
            if r.status_code == 401:
                r.success()
            else:
                r.failure(f"Attendu 401, reçu {r.status_code}")
