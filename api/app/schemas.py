from datetime import datetime

from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    name: str
    version: str
    alias: str
    variant: str
    track: str


class Prediction(BaseModel):
    label: str
    confidence: float
    probabilities: dict[str, float]


class PredictResponse(Prediction):
    model: ModelInfo
    latency_ms: float


class BatchItem(Prediction):
    filename: str | None


class BatchResponse(BaseModel):
    predictions: list[BatchItem]
    model: ModelInfo
    latency_ms: float


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: str | None = None
    is_admin: bool = False
    quota_per_minute: int | None = Field(default=None, ge=1, le=100_000)


class UserOut(BaseModel):
    id: int
    name: str
    email: str | None
    key_prefix: str
    is_admin: bool
    is_active: bool
    quota_per_minute: int
    created_at: datetime


class UserCreated(UserOut):
    api_key: str = Field(description="Affichée une seule fois")


class UsageStats(BaseModel):
    user: str
    total_requests: int
    total_images: int
    errors: int
    avg_latency_ms: float | None
    last_request_at: datetime | None
