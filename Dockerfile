# BidDrop backend (FastAPI). Build from the repo root:
#   docker build -t biddrop-api .
#   docker run -p 8000:8000 --env-file .env biddrop-api
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# libgomp is needed by xgboost / catboost at import time
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY Backend/requirements.txt Backend/requirements.txt
RUN pip install -r Backend/requirements.txt

COPY Backend/ Backend/

EXPOSE 8000

# Hosts like Render/Railway inject PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn Backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
