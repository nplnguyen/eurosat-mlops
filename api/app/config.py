from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", protected_namespaces=())

    # --- Service ---------------------------------------------------------- #
    service_name: str = "eurosat-api"
    deployment_track: str = "stable"  # "stable" | "canary" (pour les métriques)
    root_path: str = ""  # "/api" derrière la passerelle (Swagger fonctionnel)

    # --- Modèle ----------------------------------------------------------- #
    model_source: str = "mlflow"  # "mlflow" | "local"
    model_name: str = "eurosat-classifier"
    model_alias: str = "champion"
    model_fallback_alias: str = "champion"  # si l'alias demandé n'existe pas
    model_variant: str = "int8"  # "int8" | "fp32"
    local_model_dir: str = "/models"
    model_cache_dir: str = "/tmp/model-cache"
    model_refresh_seconds: int = 60
    ort_threads: int = 2
    mlflow_tracking_uri: str = "http://mlflow:5000"

    # --- Sécurité --------------------------------------------------------- #
    database_url: str = "postgresql+psycopg://app:app@postgres:5432/app"
    api_key_pepper: str = "change-me"
    admin_api_key: str | None = None  # clé admin créée au démarrage si absente
    default_quota_per_minute: int = 600
    auth_cache_ttl_seconds: int = 30
    max_upload_bytes: int = 5 * 1024 * 1024
    max_batch_size: int = 32

    # --- Redis (rate-limit + fenêtre de drift partagées entre réplicas) --- #
    redis_url: str | None = "redis://redis:6379/0"

    # --- Drift ------------------------------------------------------------ #
    drift_window_size: int = 1000
    drift_min_samples: int = 100
    drift_n_components: int = 10
    drift_alpha: float = 0.05
    drift_check_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
