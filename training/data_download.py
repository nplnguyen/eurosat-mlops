"""Téléchargement robuste d'EuroSAT (RGB).

torchvision <= 0.19 pointe vers l'ancien serveur madm.dfki.de, qui ne répond
plus. On essaie plusieurs miroirs officiels et on range les images là où
torchvision les attend : <data_dir>/eurosat/2750/<classe>/*.jpg
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import requests

SOURCES = [
    # Miroir Hugging Face (rehébergé avec l'accord de l'auteur, même MD5)
    "https://huggingface.co/datasets/torchgeo/eurosat/resolve/c877bcd43f099cd0196738f714544e355477f3fd/EuroSAT.zip",
    # Dépôt officiel Zenodo (DOI 10.5281/zenodo.7711810)
    "https://zenodo.org/records/7711810/files/EuroSAT_RGB.zip?download=1",
]


def _find_class_root(folder: Path) -> Path | None:
    """Dossier qui contient directement les 10 sous-dossiers de classes."""
    for forest in folder.rglob("Forest"):
        if forest.is_dir() and (forest.parent / "SeaLake").is_dir():
            return forest.parent
    return None


def ensure_eurosat(data_dir: str) -> Path:
    base = Path(data_dir) / "eurosat"
    target = base / "2750"
    if target.is_dir() and (target / "Forest").is_dir():
        return target
    base.mkdir(parents=True, exist_ok=True)
    archive = base / "download.zip"
    for url in SOURCES:
        try:
            print(f"Téléchargement d'EuroSAT depuis {url.split('/')[2]}…", flush=True)
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(archive, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
            tmp = base / "_extract"
            shutil.rmtree(tmp, ignore_errors=True)
            with zipfile.ZipFile(archive) as z:
                z.extractall(tmp)
            root = _find_class_root(tmp)
            if root is None:
                raise RuntimeError("structure d'archive inattendue")
            shutil.rmtree(target, ignore_errors=True)
            shutil.move(str(root), str(target))
            shutil.rmtree(tmp, ignore_errors=True)
            archive.unlink(missing_ok=True)
            n = sum(1 for _ in target.rglob("*.jpg"))
            print(f"EuroSAT prêt : {n} images dans {target}", flush=True)
            return target
        except Exception as exc:  # on passe au miroir suivant
            print(f"  échec ({exc}), essai du miroir suivant", flush=True)
            archive.unlink(missing_ok=True)
    raise SystemExit("Impossible de télécharger EuroSAT depuis les miroirs connus.")
