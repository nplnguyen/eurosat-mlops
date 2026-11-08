from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import SessionLocal, User
from app.routers.monitoring import usage_stats
from app.schemas import UsageStats, UserCreate, UserCreated, UserOut
from app.security import AuthUser, auth_cache, generate_api_key, hash_api_key, require_admin

router = APIRouter(prefix="/admin", tags=["administration"])
settings = get_settings()


def _out(u: User, **extra) -> dict:
    return {c: getattr(u, c) for c in UserOut.model_fields} | extra


def create_user(name: str, email: str | None = None, is_admin: bool = False,
                quota: int | None = None, api_key: str | None = None) -> tuple[User, str]:
    key = api_key or generate_api_key()
    user = User(name=name, email=email, is_admin=is_admin, key_hash=hash_api_key(key),
                key_prefix=key[:12], quota_per_minute=quota or settings.default_quota_per_minute)
    with SessionLocal() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
    return user, key


@router.post("/users", response_model=UserCreated, status_code=201, summary="Créer un utilisateur et sa clé")
def admin_create_user(body: UserCreate, _: AuthUser = Depends(require_admin)):
    try:
        user, key = create_user(body.name, body.email, body.is_admin, body.quota_per_minute)
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nom d'utilisateur déjà pris") from None
    return _out(user, api_key=key)


@router.get("/users", response_model=list[UserOut])
def admin_list_users(_: AuthUser = Depends(require_admin)):
    with SessionLocal() as db:
        return [_out(u) for u in db.scalars(select(User).order_by(User.id))]


@router.post("/users/{user_id}/rotate-key", response_model=UserCreated, summary="Régénérer la clé")
def admin_rotate_key(user_id: int, _: AuthUser = Depends(require_admin)):
    key = generate_api_key()
    with SessionLocal() as db:
        u = db.get(User, user_id) or _404()
        u.key_hash, u.key_prefix = hash_api_key(key), key[:12]
        db.commit()
        db.refresh(u)
    auth_cache.clear()
    return _out(u, api_key=key)


@router.delete("/users/{user_id}", status_code=204, summary="Révoquer un utilisateur")
def admin_revoke(user_id: int, _: AuthUser = Depends(require_admin)):
    with SessionLocal() as db:
        u = db.get(User, user_id) or _404()
        u.is_active = False
        db.commit()
    auth_cache.clear()


@router.get("/usage", response_model=list[UsageStats], summary="Usage agrégé par utilisateur")
def admin_usage(_: AuthUser = Depends(require_admin)):
    return usage_stats()


@router.post("/model/reload", summary="Forcer la vérification du registre MLflow")
def admin_reload(request: Request, _: AuthUser = Depends(require_admin)):
    mm = request.app.state.models
    changed = mm.refresh()
    b = mm.bundle
    return {"changed": changed, "version": b.version if b else None, "error": mm.last_error}


def _404():
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable")
