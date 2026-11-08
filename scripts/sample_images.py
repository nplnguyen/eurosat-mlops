"""Extrait un échantillon d'images EuroSAT (jeu de test) vers loadtest/images/.

    python scripts/sample_images.py --data-dir ./data --n-per-class 30
"""
from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="./data")
    ap.add_argument("--out", default="loadtest/images")
    ap.add_argument("--n-per-class", type=int, default=30)
    a = ap.parse_args()

    roots = list(Path(a.data_dir).glob("**/2750"))  # dossier d'extraction d'EuroSAT
    if not roots:
        raise SystemExit("EuroSAT introuvable : lancer d'abord un entraînement (téléchargement auto).")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    random.seed(0)
    for cls_dir in sorted(p for p in roots[0].iterdir() if p.is_dir()):
        files = sorted(cls_dir.glob("*.jpg"))
        for f in random.sample(files, min(a.n_per_class, len(files))):
            shutil.copy(f, out / f.name)
    print(f"{len(list(out.glob('*.jpg')))} images copiées dans {out}")


if __name__ == "__main__":
    main()
