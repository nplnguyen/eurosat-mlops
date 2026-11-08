"""Métriques Prometheus exposées sur /metrics (non accessible depuis l'extérieur)."""
from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "api_http_requests_total", "Requêtes HTTP", ["method", "route", "status", "track"]
)
HTTP_LATENCY = Histogram(
    "api_http_request_duration_seconds", "Durée des requêtes HTTP", ["route", "track"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
USER_REQUESTS = Counter(
    "api_user_predictions_total", "Prédictions par utilisateur", ["user", "track"]
)
INFERENCE_LATENCY = Histogram(
    "model_inference_seconds", "Temps d'inférence ONNX (batch)", ["track", "model_version"],
    buckets=(0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1),
)
PREDICTIONS = Counter(
    "model_predictions_total", "Classes prédites", ["label", "track", "model_version"]
)
CONFIDENCE = Histogram(
    "model_prediction_confidence", "Probabilité de la classe prédite", ["track"],
    buckets=(0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0),
)
MODEL_INFO = Gauge("model_info", "Modèle servi", ["track", "model_version", "alias", "variant"])
DRIFT_DETECTED = Gauge("data_drift_detected", "1 si drift détecté", ["track", "model_version"])
DRIFT_SHARE = Gauge("data_drift_share_components", "Part des composantes PCA en drift", ["track", "model_version"])
DRIFT_MIN_P = Gauge("data_drift_min_p_value", "p-value KS minimale", ["track", "model_version"])
DRIFT_PSI = Gauge("prediction_drift_psi", "PSI sur les classes prédites", ["track", "model_version"])
DRIFT_WINDOW = Gauge("data_drift_window_size", "Taille de la fenêtre courante", ["track", "model_version"])
