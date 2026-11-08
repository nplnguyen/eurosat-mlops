"""Point d'entrée FastAPI du service d'inférence EuroSAT."""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from prometheus_client import make_asgi_app
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import metrics as M
from app import security
from app.config import get_settings
from app.db import SessionLocal, User, init_db
from app.model_manager import ModelManager
from app.routers import admin, monitoring, predict
from app.usage import recorder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("eurosat-api")
settings = get_settings()
TRACK = settings.deployment_track


def _redis():
    if not settings.redis_url:
        return None
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_timeout=0.5)
        client.ping()
        return client
    except Exception as exc:
        log.warning("Redis indisponible (%s) : repli en mémoire", exc)
        return None


def _seed_admin() -> None:
    if not settings.admin_api_key:
        return
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.name == "admin")):
            return
    try:
        admin.create_user("admin", is_admin=True, quota=100_000, api_key=settings.admin_api_key)
        log.info("Utilisateur admin créé")
    except IntegrityError:  # créé en parallèle par un autre réplica
        pass


def _drift_loop(app: FastAPI, stop: threading.Event) -> None:
    """Calcule périodiquement le drift et met à jour les jauges Prometheus."""
    last_version = None
    while not stop.wait(settings.drift_check_seconds):
        b = app.state.models.bundle
        if b is None:
            continue
        if b.version != last_version:
            M.MODEL_INFO.clear()
            M.MODEL_INFO.labels(TRACK, b.version, b.alias, b.variant).set(1)
            last_version = b.version
        try:
            r = b.drift.compute()
        except Exception as exc:
            log.warning("Calcul du drift impossible : %s", exc)
            continue
        M.DRIFT_WINDOW.labels(TRACK, b.version).set(r.n_current)
        if r.ready:
            M.DRIFT_DETECTED.labels(TRACK, b.version).set(int(r.drift_detected))
            M.DRIFT_SHARE.labels(TRACK, b.version).set(r.share_drifted_components)
            M.DRIFT_MIN_P.labels(TRACK, b.version).set(r.min_p_value)
            M.DRIFT_PSI.labels(TRACK, b.version).set(r.prediction_psi)
            if r.drift_detected:
                log.warning("DATA DRIFT détecté (v%s) : %.0f%% des composantes, PSI=%.3f",
                            b.version, 100 * r.share_drifted_components, r.prediction_psi)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception as exc:  # course entre réplicas au tout premier démarrage
        log.warning("init_db : %s (nouvel essai)", exc)
        time.sleep(2)
        init_db()
    _seed_admin()
    redis_client = _redis()
    security.rate_limiter.redis = redis_client

    mm = ModelManager(settings, redis_client)
    mm.refresh()  # premier chargement (non bloquant en cas d'échec)
    mm.start_background_refresh()
    app.state.models = mm

    recorder.start()
    stop = threading.Event()
    threading.Thread(target=_drift_loop, args=(app, stop), daemon=True, name="drift").start()
    log.info("Service démarré (track=%s, alias=%s)", TRACK, settings.model_alias)
    yield
    stop.set()
    mm.stop()
    recorder.stop()


app = FastAPI(
    title="EuroSAT Land-Cover API",
    description=(
        "Classification d'occupation des sols à partir d'images Sentinel-2.\n\n"
        "Toutes les routes `/v1` et `/admin` exigent le header **`X-API-Key`**."
    ),
    version="1.0.0",
    root_path=settings.root_path,
    lifespan=lifespan,
)
app.include_router(monitoring.router)
app.include_router(predict.router)
app.include_router(admin.router)
app.mount("/metrics", make_asgi_app())


@app.middleware("http")
async def observe(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - t0
    route = request.scope.get("route")
    path = getattr(route, "path", "unmatched")
    if path not in ("/metrics", "/health", "/health/ready"):
        M.HTTP_REQUESTS.labels(request.method, path, response.status_code, TRACK).inc()
        M.HTTP_LATENCY.labels(path, TRACK).observe(elapsed)
    user = getattr(request.state, "user", None)
    if user is not None:
        recorder.record(
            user_id=user.id, endpoint=path, status_code=response.status_code,
            n_images=getattr(request.state, "n_images", 0), latency_ms=elapsed * 1000,
            model_version=getattr(request.state, "model_version", None), track=TRACK,
        )
    return response
