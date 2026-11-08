"""Démonstration de la détection de data drift.

Envoie au service des images EuroSAT altérées pour simuler un changement de
conditions d'acquisition (nuages, capteur dégradé, saison…), puis affiche le
rapport de drift renvoyé par l'API.

    python scripts/simulate_drift.py --url http://localhost/api --key eus_... \
        --images loadtest/images --perturbation clouds --n 300

Perturbations : none (contrôle), clouds, blur, noise, dark, saturate.
"""
from __future__ import annotations

import argparse
import io
import json
import random
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageEnhance, ImageFilter


def perturb(img: Image.Image, kind: str, rng: np.random.Generator) -> Image.Image:
    if kind == "none":
        return img
    if kind == "blur":
        return img.filter(ImageFilter.GaussianBlur(radius=2.0))
    if kind == "dark":
        return ImageEnhance.Brightness(img).enhance(0.45)
    if kind == "saturate":
        return ImageEnhance.Color(img).enhance(2.5)
    a = np.asarray(img, dtype=np.float32)
    if kind == "noise":
        a = a + rng.normal(0, 35, a.shape)
    elif kind == "clouds":
        # masque nuageux basse fréquence
        h, w = a.shape[:2]
        small = rng.random((h // 8 + 1, w // 8 + 1))
        mask = np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)) / 255
        mask = np.clip((mask - 0.4) * 2.5, 0, 1)[..., None]
        a = a * (1 - mask) + 245 * mask
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost/api")
    ap.add_argument("--key", required=True)
    ap.add_argument("--images", default="loadtest/images")
    ap.add_argument("--perturbation", default="clouds",
                    choices=["none", "clouds", "blur", "noise", "dark", "saturate"])
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--track", default="never", help="X-Canary : never=stable, always=canary")
    a = ap.parse_args()

    paths = [p for p in Path(a.images).glob("**/*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif"}]
    if not paths:
        raise SystemExit(f"Aucune image dans {a.images} (lancer `make sample-images`)")
    rng = np.random.default_rng(0)
    headers = {"X-API-Key": a.key, "X-Canary": a.track}
    ok = 0
    for i in range(a.n):
        img = perturb(Image.open(random.choice(paths)).convert("RGB"), a.perturbation, rng)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        r = requests.post(f"{a.url}/v1/predict", headers=headers,
                          files={"file": ("x.png", buf.getvalue(), "image/png")}, timeout=30)
        ok += r.ok
        if (i + 1) % 50 == 0:
            print(f"{i + 1}/{a.n} envoyées ({ok} OK)")

    if ok == 0:
        raise SystemExit(
            f"Aucune requête acceptée (dernier code HTTP {r.status_code} : {r.text[:120]}). Vérifiez la clé d'API."
        )
    report = requests.get(f"{a.url}/v1/drift", headers=headers, timeout=30).json()
    if not report.get("ready"):
        print(json.dumps(report, indent=2))
        raise SystemExit("Rapport de drift indisponible (fenêtre trop petite ou erreur).")
    print(json.dumps({k: v for k, v in report.items() if k != "p_values"}, indent=2))
    print("=> DRIFT DÉTECTÉ" if report.get("drift_detected") else "=> pas de drift détecté")


if __name__ == "__main__":
    main()
