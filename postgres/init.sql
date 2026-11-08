-- Une instance PostgreSQL, deux bases isolées : métadonnées MLflow et données applicatives.
CREATE USER mlflow WITH PASSWORD 'mlflow';
CREATE DATABASE mlflow OWNER mlflow;
CREATE USER app WITH PASSWORD 'app';
CREATE DATABASE app OWNER app;
