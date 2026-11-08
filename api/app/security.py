"""Authentification par clé d'API + rate limiting par utilisateur.

La clé est envoyée dans le header `X-API-Key` (ou `Authorization: Bearer`).
Elle est comparée à son empreinte HMAC-SHA256 stockée en base : une fuite de
la base ne divulgue pas les clés.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, User

settings = get_settings()
KEY_PREFIX = "eus_"

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="Clé d'API personnelle")
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthUser:
    id: int
    name: str
    is_admin: bool
    quota_per_minute: int


def generate_api_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    return hmac.new(settings.api_key_pepper.encode(), key.encode(), hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------- #
# Cache court des utilisateurs authentifiés (évite une requête SQL par appel
# lors des tests de charge). Une révocation prend effet en <= TTL secondes.
# --------------------------------------------------------------------------- #
class _AuthCache:
    def __init__(self, ttl: int):
        self.ttl, self._data, self._lock = ttl, {}, threading.Lock()

    def get(self, h: str) -> AuthUser | None:
        with self._lock:
            item = self._data.get(h)
            if item and item[1] > time.monotonic():
                return item[0]
            self._data.pop(h, None)
            return None

    def set(self, h: str, user: AuthUser) -> None:
        with self._lock:
            self._data[h] = (user, time.monotonic() + self.ttl)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


auth_cache = _AuthCache(settings.auth_cache_ttl_seconds)


def _lookup(key_hash: str) -> AuthUser | None:
    cached = auth_cache.get(key_hash)
    if cached:
        return cached
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.key_hash == key_hash, User.is_active.is_(True)))
        if u is None:
            return None
        au = AuthUser(u.id, u.name, u.is_admin, u.quota_per_minute)
    auth_cache.set(key_hash, au)
    return au


# --------------------------------------------------------------------------- #
# Rate limiting : fenêtre fixe d'une minute, partagée via Redis entre les
# réplicas (repli en mémoire si Redis est indisponible).
# --------------------------------------------------------------------------- #
class RateLimiter:
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._local: dict[str, int] = {}
        self._lock = threading.Lock()

    def hit(self, user: AuthUser) -> tuple[bool, int]:
        window = int(time.time() // 60)
        key = f"rl:{user.id}:{window}"
        if self.redis is not None:
            try:
                pipe = self.redis.pipeline()
                pipe.incr(key)
                pipe.expire(key, 70)
                count = pipe.execute()[0]
                return count <= user.quota_per_minute, int(count)
            except Exception:
                pass  # dégradation gracieuse
        with self._lock:
            # purge des anciennes fenêtres
            for k in [k for k in self._local if not k.endswith(f":{window}")]:
                del self._local[k]
            self._local[key] = self._local.get(key, 0) + 1
            count = self._local[key]
        return count <= user.quota_per_minute, count


rate_limiter = RateLimiter()


def get_current_user(
    request: Request,
    api_key: str | None = Security(api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> AuthUser:
    token = api_key or (bearer.credentials if bearer else None)
    if not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Clé d'API manquante (header X-API-Key)",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    user = _lookup(hash_api_key(token))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Clé d'API invalide ou révoquée",
                            headers={"WWW-Authenticate": "ApiKey"})
    allowed, count = rate_limiter.hit(user)
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Quota dépassé ({user.quota_per_minute} requêtes/minute)",
            headers={"Retry-After": str(60 - int(time.time()) % 60)},
        )
    request.state.user = user
    return user


def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits administrateur requis")
    return user
