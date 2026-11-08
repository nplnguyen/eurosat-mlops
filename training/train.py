"""Entraînement d'un classifieur d'occupation des sols sur EuroSAT (Sentinel-2 RGB).

Pipeline :
  1. Téléchargement d'EuroSAT et découpage stratifié train / val / test (70/15/15).
  2. Transfer learning d'un backbone pré-entraîné ImageNet (ResNet / EfficientNet).
  3. Suivi complet de l'expérience dans MLflow (paramètres, métriques, artefacts).
  4. Export ONNX (FP32) puis quantization statique INT8 (onnxruntime).
  5. Évaluation comparée FP32 vs INT8 (précision, latence, taille).
  6. Calcul de la distribution de référence des embeddings (détection de drift).
  7. Enregistrement dans le Model Registry MLflow avec une "quality gate"
     et attribution de l'alias `challenger` (et `champion` s'il n'existe pas).

Exemple :
    python -m training.train --arch resnet18 --epochs 10
"""
from __future__ import annotations

import argparse
import json
import os
import random
import tempfile
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mlflow  # noqa: E402
import numpy as np  # noqa: E402
import onnx  # noqa: E402
import onnxruntime as ort  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from mlflow.tracking import MlflowClient  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import train_test_split  # noqa: E402
from torch.utils.data import DataLoader, Subset  # noqa: E402
from torchvision import datasets, models, transforms  # noqa: E402

from training.config import CLASSES, IMG_SIZE, MEAN, REGISTERED_MODEL_NAME, SEED, STD  # noqa: E402
from training.quantize import quantize_int8  # noqa: E402
from training.data_download import ensure_eurosat  # noqa: E402


# --------------------------------------------------------------------------- #
# Reproductibilité
# --------------------------------------------------------------------------- #
def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


# --------------------------------------------------------------------------- #
# Données
# --------------------------------------------------------------------------- #
def build_transforms():
    # Les images satellites n'ont pas d'orientation canonique : les symétries
    # et rotations de 90° sont des augmentations "physiquement valides".
    train_tf = transforms.Compose(
        [
            transforms.Resize((IMG_SIZE, IMG_SIZE)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomVerticalFlip(),
            transforms.RandomApply([transforms.RandomRotation((90, 90))], p=0.5),
            transforms.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ]
    )
    eval_tf = transforms.Compose(
        [
            transforms.Resize((IMG_SIZE, IMG_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ]
    )
    return train_tf, eval_tf


def build_splits(data_dir: str, subset_fraction: float):
    train_tf, eval_tf = build_transforms()
    ensure_eurosat(data_dir)
    ds_train = datasets.EuroSAT(root=data_dir, download=False, transform=train_tf)
    ds_eval = datasets.EuroSAT(root=data_dir, download=False, transform=eval_tf)
    assert ds_train.classes == CLASSES, f"Ordre des classes inattendu : {ds_train.classes}"

    targets = np.array(ds_train.targets)
    indices = np.arange(len(targets))
    if subset_fraction < 1.0:  # utile pour le bootstrap rapide sur CPU
        indices, _ = train_test_split(
            indices, train_size=subset_fraction, stratify=targets, random_state=SEED
        )
    idx_train, idx_tmp = train_test_split(
        indices, test_size=0.30, stratify=targets[indices], random_state=SEED
    )
    idx_val, idx_test = train_test_split(
        idx_tmp, test_size=0.50, stratify=targets[idx_tmp], random_state=SEED
    )
    return (
        Subset(ds_train, idx_train),
        Subset(ds_eval, idx_val),
        Subset(ds_eval, idx_test),
    )


# --------------------------------------------------------------------------- #
# Modèle
# --------------------------------------------------------------------------- #
class EuroSATNet(nn.Module):
    """Backbone + tête de classification.

    `forward` renvoie (logits, embedding) : l'embedding (avant-dernière couche)
    est exporté dans le graphe ONNX pour alimenter la détection de drift
    côté production sans second passage dans le réseau.
    """

    def __init__(self, arch: str, num_classes: int, dropout: float = 0.2):
        super().__init__()
        if arch == "resnet18":
            backbone = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
            dim = backbone.fc.in_features
            backbone.fc = nn.Identity()
        elif arch == "resnet50":
            backbone = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V2)
            dim = backbone.fc.in_features
            backbone.fc = nn.Identity()
        elif arch == "efficientnet_b0":
            backbone = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1)
            dim = backbone.classifier[1].in_features
            backbone.classifier = nn.Identity()
        else:
            raise ValueError(f"Architecture inconnue : {arch}")
        self.backbone = backbone
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(dim, num_classes))
        self.embedding_dim = dim

    def forward(self, x):
        emb = self.backbone(x)
        return self.head(emb), emb


# --------------------------------------------------------------------------- #
# Boucles d'entraînement / évaluation
# --------------------------------------------------------------------------- #
def run_epoch(model, loader, criterion, device, optimizer=None):
    training = optimizer is not None
    model.train(training)
    total_loss, y_true, y_pred = 0.0, [], []
    with torch.set_grad_enabled(training):
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            logits, _ = model(x)
            loss = criterion(logits, y)
            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()
            total_loss += loss.item() * x.size(0)
            y_true.extend(y.cpu().numpy())
            y_pred.extend(logits.argmax(1).cpu().numpy())
    n = len(loader.dataset)
    return (
        total_loss / n,
        accuracy_score(y_true, y_pred),
        f1_score(y_true, y_pred, average="macro"),
    )


def loader_to_numpy(loader):
    xs, ys = [], []
    for x, y in loader:
        xs.append(x.numpy())
        ys.append(y.numpy())
    return np.concatenate(xs).astype(np.float32), np.concatenate(ys)


def evaluate_onnx(path: str, x: np.ndarray, y: np.ndarray, n_latency: int = 200):
    """Précision + latence (batch=1) d'un modèle ONNX sur CPU."""
    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    preds, embs = [], []
    for i in range(0, len(x), 64):
        logits, emb = sess.run(None, {"input": x[i : i + 64]})
        preds.append(logits.argmax(1))
        embs.append(emb)
    preds = np.concatenate(preds)

    lat = []
    for i in range(min(n_latency, len(x))):
        t0 = time.perf_counter()
        sess.run(None, {"input": x[i : i + 1]})
        lat.append((time.perf_counter() - t0) * 1000)
    return {
        "accuracy": float(accuracy_score(y, preds)),
        "f1_macro": float(f1_score(y, preds, average="macro")),
        "latency_p50_ms": float(np.percentile(lat, 50)),
        "latency_p95_ms": float(np.percentile(lat, 95)),
        "size_mb": os.path.getsize(path) / 1e6,
    }, preds, np.concatenate(embs)


def plot_confusion(y_true, y_pred, path):
    cm = confusion_matrix(y_true, y_pred, normalize="true")
    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(cm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(CLASSES)), CLASSES, rotation=45, ha="right")
    ax.set_yticks(range(len(CLASSES)), CLASSES)
    for i in range(len(CLASSES)):
        for j in range(len(CLASSES)):
            ax.text(j, i, f"{cm[i, j]:.2f}", ha="center", va="center",
                    color="white" if cm[i, j] > 0.5 else "black", fontsize=7)
    ax.set_xlabel("Prédit")
    ax.set_ylabel("Réel")
    ax.set_title("Matrice de confusion normalisée (test, ONNX INT8)")
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Registre MLflow
# --------------------------------------------------------------------------- #
def register(run_id: str, test_f1: float, min_f1: float) -> str | None:
    client = MlflowClient()
    if test_f1 < min_f1:
        print(f"[quality gate] F1 test {test_f1:.4f} < {min_f1} : modèle NON enregistré.")
        return None
    mv = mlflow.register_model(f"runs:/{run_id}/model", REGISTERED_MODEL_NAME)
    # Attendre que la version soit prête
    for _ in range(60):
        if client.get_model_version(REGISTERED_MODEL_NAME, mv.version).status == "READY":
            break
        time.sleep(1)
    client.set_model_version_tag(REGISTERED_MODEL_NAME, mv.version, "test_f1_macro", f"{test_f1:.4f}")

    # Une nouvelle version part toujours en canary (challenger).
    client.set_registered_model_alias(REGISTERED_MODEL_NAME, "challenger", mv.version)
    try:
        client.get_model_version_by_alias(REGISTERED_MODEL_NAME, "champion")
    except Exception:
        # Premier modèle : il devient directement champion.
        client.set_registered_model_alias(REGISTERED_MODEL_NAME, "champion", mv.version)
        print(f"Version {mv.version} -> alias 'champion' (premier modèle)")
    print(f"Version {mv.version} -> alias 'challenger'")
    return mv.version


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arch", default="resnet18", choices=["resnet18", "resnet50", "efficientnet_b0"])
    p.add_argument("--epochs", type=int, default=10)
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--label-smoothing", type=float, default=0.1)
    p.add_argument("--patience", type=int, default=3)
    p.add_argument("--subset-fraction", type=float, default=1.0)
    p.add_argument("--data-dir", default=os.getenv("DATA_DIR", "./data"))
    p.add_argument("--num-workers", type=int, default=4)
    p.add_argument("--min-f1", type=float, default=float(os.getenv("MIN_TEST_F1", "0.85")))
    p.add_argument("--experiment", default="eurosat-landcover")
    p.add_argument("--no-register", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    set_seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    mlflow.set_experiment(args.experiment)

    train_set, val_set, test_set = build_splits(args.data_dir, args.subset_fraction)
    mk = lambda ds, sh: DataLoader(ds, batch_size=args.batch_size, shuffle=sh,  # noqa: E731
                                   num_workers=args.num_workers, pin_memory=device.type == "cuda")
    train_dl, val_dl, test_dl = mk(train_set, True), mk(val_set, False), mk(test_set, False)

    model = EuroSATNet(args.arch, len(CLASSES)).to(device)
    criterion = nn.CrossEntropyLoss(label_smoothing=args.label_smoothing)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    with mlflow.start_run(run_name=f"{args.arch}-e{args.epochs}") as run:
        mlflow.log_params(vars(args) | {
            "img_size": IMG_SIZE, "device": str(device),
            "n_train": len(train_set), "n_val": len(val_set), "n_test": len(test_set),
        })
        mlflow.set_tag("dataset", "EuroSAT-RGB")

        best_f1, best_state, bad_epochs = -1.0, None, 0
        for epoch in range(1, args.epochs + 1):
            t0 = time.time()
            tr_loss, tr_acc, tr_f1 = run_epoch(model, train_dl, criterion, device, optimizer)
            va_loss, va_acc, va_f1 = run_epoch(model, val_dl, criterion, device)
            scheduler.step()
            mlflow.log_metrics({
                "train_loss": tr_loss, "train_acc": tr_acc, "train_f1": tr_f1,
                "val_loss": va_loss, "val_acc": va_acc, "val_f1": va_f1,
                "lr": scheduler.get_last_lr()[0], "epoch_time_s": time.time() - t0,
            }, step=epoch)
            print(f"[{epoch:02d}] train loss={tr_loss:.4f} f1={tr_f1:.4f} | val loss={va_loss:.4f} f1={va_f1:.4f}")

            if va_f1 > best_f1:
                best_f1, bad_epochs = va_f1, 0
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            else:
                bad_epochs += 1
                if bad_epochs >= args.patience:
                    print(f"Early stopping à l'époque {epoch}")
                    break

        model.load_state_dict(best_state)
        model.eval().cpu()
        mlflow.log_metric("best_val_f1", best_f1)

        with tempfile.TemporaryDirectory() as tmp:
            deploy = Path(tmp) / "deploy"
            deploy.mkdir()
            fp32_path, int8_path = deploy / "model_fp32.onnx", deploy / "model_int8.onnx"

            # --- Export ONNX ------------------------------------------------ #
            dummy = torch.randn(1, 3, IMG_SIZE, IMG_SIZE)
            torch.onnx.export(
                model, dummy, str(fp32_path), opset_version=17,
                input_names=["input"], output_names=["logits", "embedding"],
                dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}, "embedding": {0: "batch"}},
            )
            onnx.checker.check_model(str(fp32_path))

            # --- Quantization statique INT8 (calibration sur la validation) -- #
            x_val, _ = loader_to_numpy(val_dl)
            quantize_int8(str(fp32_path), str(int8_path), calibration_data=x_val[:512])

            # --- Évaluation comparée --------------------------------------- #
            x_test, y_test = loader_to_numpy(test_dl)
            m_fp32, _, _ = evaluate_onnx(str(fp32_path), x_test, y_test)
            m_int8, preds_int8, _ = evaluate_onnx(str(int8_path), x_test, y_test)
            mlflow.log_metrics({f"test_fp32_{k}": v for k, v in m_fp32.items()})
            mlflow.log_metrics({f"test_int8_{k}": v for k, v in m_int8.items()})
            mlflow.log_metric("int8_speedup", m_fp32["latency_p50_ms"] / m_int8["latency_p50_ms"])
            print("FP32 :", m_fp32)
            print("INT8 :", m_int8)

            # --- Référence pour la détection de drift ---------------------- #
            # On utilise le jeu de validation (non vu pendant l'apprentissage
            # des poids) passé dans le modèle servi (INT8).
            _, preds_val, emb_val = evaluate_onnx(str(int8_path), x_val, np.zeros(len(x_val)), n_latency=1)
            np.save(deploy / "reference_embeddings.npy", emb_val.astype(np.float32))
            ref_pred_dist = np.bincount(preds_val, minlength=len(CLASSES)) / len(preds_val)

            (deploy / "labels.json").write_text(json.dumps(CLASSES, indent=2))
            (deploy / "preprocessing.json").write_text(json.dumps({
                "img_size": IMG_SIZE, "mean": MEAN, "std": STD,
                "resize": "bilinear", "input_name": "input",
                "reference_prediction_distribution": ref_pred_dist.tolist(),
            }, indent=2))
            (deploy / "metrics.json").write_text(json.dumps({"fp32": m_fp32, "int8": m_int8}, indent=2))

            # --- Rapports -------------------------------------------------- #
            report = classification_report(y_test, preds_int8, target_names=CLASSES, digits=4)
            (Path(tmp) / "classification_report.txt").write_text(report)
            plot_confusion(y_test, preds_int8, Path(tmp) / "confusion_matrix.png")
            print(report)

            mlflow.log_artifact(str(Path(tmp) / "classification_report.txt"), "reports")
            mlflow.log_artifact(str(Path(tmp) / "confusion_matrix.png"), "reports")
            mlflow.log_artifacts(str(deploy), "deploy")
            # Modèle "officiel" MLflow (flavor ONNX) -> entrée du Model Registry
            mlflow.onnx.log_model(onnx.load(str(fp32_path)), artifact_path="model")

        if not args.no_register:
            register(run.info.run_id, m_int8["f1_macro"], args.min_f1)


if __name__ == "__main__":
    main()
