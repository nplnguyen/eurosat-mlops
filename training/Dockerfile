FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /workspace

COPY training/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY training/ /workspace/training/

# Le dataset est mis en cache dans un volume monté sur /data
ENV DATA_DIR=/data GIT_PYTHON_REFRESH=quiet
CMD ["python", "-m", "training.bootstrap"]
