from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import case, func, select

from app.config import get_settings
from app.db import SessionLocal, UsageLog, User
from app.routers.predict import get_bundle, model_info
from app.schemas import ModelInfo, UsageStats
from app.security import AuthUser, get_current_user

router = APIRouter(tags=["monitoring"])
settings = get_settings()


@router.get("/health", include_in_schema=False)
def liveness():
    return {"status": "ok"}


@router.get("/health/ready", include_in_schema=False)
def readiness(request: Request):
    mm = request.app.state.models
    if not mm.ready:
        return JSONResponse({"status": "loading", "error": mm.last_error}, status_code=503)
    return {"status": "ready", "model_version": mm.bundle.version, "track": settings.deployment_track}


@router.get("/v1/model", response_model=ModelInfo, summary="Modèle actuellement servi")
def current_model(_: AuthUser = Depends(get_current_user), b=Depends(get_bundle)):
    return model_info(b)


@router.get("/v1/drift", summary="Rapport de data drift (fenêtre glissante)")
def drift_report(_: AuthUser = Depends(get_current_user), b=Depends(get_bundle)):
    report = b.drift.compute().to_dict()
    report["model_version"] = b.version
    report["track"] = settings.deployment_track
    return report


def usage_stats(user_id: int | None = None) -> list[UsageStats]:
    q = (
        select(
            User.name,
            func.count(UsageLog.id),
            func.coalesce(func.sum(UsageLog.n_images), 0),
            func.coalesce(func.sum(case((UsageLog.status_code >= 400, 1), else_=0)), 0),
            func.avg(UsageLog.latency_ms),
            func.max(UsageLog.created_at),
        )
        .join(UsageLog, UsageLog.user_id == User.id, isouter=True)
        .group_by(User.name)
        .order_by(User.name)
    )
    if user_id is not None:
        q = q.where(User.id == user_id)
    with SessionLocal() as db:
        rows = db.execute(q).all()
    return [
        UsageStats(user=r[0], total_requests=r[1], total_images=int(r[2]), errors=int(r[3]),
                   avg_latency_ms=float(r[4]) if r[4] is not None else None, last_request_at=r[5])
        for r in rows
    ]


@router.get("/v1/me/usage", response_model=UsageStats, summary="Ma consommation")
def my_usage(user: AuthUser = Depends(get_current_user)):
    stats = usage_stats(user.id)
    return stats[0] if stats else UsageStats(user=user.name, total_requests=0, total_images=0,
                                              errors=0, avg_latency_ms=None, last_request_at=None)
