# --- Étape 1 : dépendances ------------------------------------------------- #
FROM python:3.11-slim AS deps
ENV PIP_NO_CACHE_DIR=1
COPY api/requirements.txt /tmp/requirements.txt
RUN pip install --prefix=/install -r /tmp/requirements.txt

# --- Étape 2 : image d'exécution (sans PyTorch, utilisateur non-root) ----- #
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app
COPY --from=deps /install /usr/local
WORKDIR /srv
COPY api/app ./app
RUN mkdir -p /tmp/model-cache && chown -R app /tmp/model-cache
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s CMD curl -fs http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
