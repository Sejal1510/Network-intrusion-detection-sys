# syntax=docker/dockerfile:1
FROM python:3.12-slim

# catboost's Linux wheel dynamically links libgomp (OpenMP) at import
# time -- python:3.12-slim (Debian) doesn't ship it by default.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copied separately from src/ so `pip install .` is only re-run when a
# dependency actually changes, not on every source edit.
COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .

# Trained runs (models/runs/<run_id>/, produced by `python -m
# nids.training` -- see docs/DATASET.md) are never baked into the image;
# docker-compose.yml bind-mounts them read-only at runtime instead, same
# as ServingConfig.artifact_root works locally. Persistence (when
# NIDS_DATABASE_URL is a sqlite:////data/... path) is a named volume
# mounted at /data -- see docker-compose.yml.
EXPOSE 8000

ENTRYPOINT ["python", "-m", "nids.api"]
