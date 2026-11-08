from __future__ import annotations

import time

import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status

from app import metrics as M
from app.config import get_settings
from app.model_manager import ModelBundle
from app.preprocessing import InvalidImage, load_image, preprocess
from app.schemas import BatchItem, BatchResponse, ModelInfo, PredictResponse
from app.security import AuthUser, get_current_user

router = APIRouter(prefix="/v1", tags=["prédiction"])
settings = get_settings()


def get_bundle(request: Request) -> ModelBundle:
    bundle = request.app.state.models.bundle
    if bundle is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Modèle pas encore chargé")
    return bundle


def model_info(b: ModelBundle) -> ModelInfo:
    return ModelInfo(name=settings.model_name, version=b.version, alias=b.alias,
                     variant=b.variant, track=settings.deployment_track)


def _read(file: UploadFile) -> np.ndarray:
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image trop volumineuse")
    try:
        return load_image(data)
    except InvalidImage as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


def _infer(b: ModelBundle, batch: np.ndarray, user: AuthUser):
    t0 = time.perf_counter()
    probs, emb = b.predict(batch)
    M.INFERENCE_LATENCY.labels(settings.deployment_track, b.version).observe(time.perf_counter() - t0)

    preds, confs = probs.argmax(1), probs.max(1)
    for p, c in zip(preds, confs):
        M.PREDICTIONS.labels(b.labels[p], settings.deployment_track, b.version).inc()
        M.CONFIDENCE.labels(settings.deployment_track).observe(float(c))
    M.USER_REQUESTS.labels(user.name, settings.deployment_track).inc(len(preds))
    try:
        b.drift.add(emb, preds, confs)
    except Exception:  # le monitoring ne doit jamais casser la prédiction
        pass
    return probs, preds, confs


def _headers(response: Response, b: ModelBundle, n: int, request: Request) -> None:
    response.headers["X-Model-Version"] = b.version
    response.headers["X-Model-Alias"] = b.alias
    response.headers["X-Deployment-Track"] = settings.deployment_track
    request.state.model_version = b.version
    request.state.n_images = n


@router.post("/predict", response_model=PredictResponse, summary="Classifier une image satellite")
def predict(
    request: Request,
    response: Response,
    file: UploadFile = File(..., description="Image RGB (PNG/JPEG/TIFF)"),
    user: AuthUser = Depends(get_current_user),
    b: ModelBundle = Depends(get_bundle),
):
    t0 = time.perf_counter()
    x = preprocess(_read(file), b.img_size, b.mean, b.std)[None]
    probs, preds, confs = _infer(b, x, user)
    _headers(response, b, 1, request)
    return PredictResponse(
        label=b.labels[preds[0]],
        confidence=float(confs[0]),
        probabilities={lbl: round(float(p), 6) for lbl, p in zip(b.labels, probs[0])},
        model=model_info(b),
        latency_ms=(time.perf_counter() - t0) * 1000,
    )


@router.post("/predict/batch", response_model=BatchResponse, summary="Classifier plusieurs images")
def predict_batch(
    request: Request,
    response: Response,
    files: list[UploadFile] = File(...),
    user: AuthUser = Depends(get_current_user),
    b: ModelBundle = Depends(get_bundle),
):
    if len(files) > settings.max_batch_size:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"Maximum {settings.max_batch_size} images par requête")
    t0 = time.perf_counter()
    x = np.stack([preprocess(_read(f), b.img_size, b.mean, b.std) for f in files])
    probs, preds, confs = _infer(b, x, user)
    _headers(response, b, len(files), request)
    return BatchResponse(
        predictions=[
            BatchItem(
                filename=f.filename,
                label=b.labels[p],
                confidence=float(c),
                probabilities={lbl: round(float(v), 6) for lbl, v in zip(b.labels, pr)},
            )
            for f, p, c, pr in zip(files, preds, confs, probs)
        ],
        model=model_info(b),
        latency_ms=(time.perf_counter() - t0) * 1000,
    )
