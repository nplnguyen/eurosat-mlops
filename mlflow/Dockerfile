FROM python:3.11-slim
ENV PIP_NO_CACHE_DIR=1
RUN pip install mlflow==2.17.2 psycopg2-binary==2.9.10 boto3==1.35.54 sqlalchemy==2.0.36 alembic==1.13.3 \
    && mkdir -p /mlartifacts
EXPOSE 5000
# --serve-artifacts : le serveur MLflow sert de proxy vers le stockage des
# artefacts (volume local ici, S3 en cloud) : les clients n'ont besoin que de
# l'URL MLflow, jamais d'identifiants de stockage.
CMD mlflow server \
    --host 0.0.0.0 --port 5000 \
    --backend-store-uri "${MLFLOW_BACKEND_STORE_URI}" \
    --artifacts-destination "${MLFLOW_ARTIFACTS_DESTINATION}" \
    --serve-artifacts
