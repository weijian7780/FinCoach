# Same Python patch release as the tested image; see constraints.txt.
FROM python:3.12.15-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TOKENIZERS_PARALLELISM=false

WORKDIR /app

# Runtime libraries required by PaddlePaddle, PaddleOCR, and OpenCV.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libsm6 \
        libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt constraints.txt /tmp/

# Install torch from the CPU wheel index BEFORE the rest of the requirements.
# The default PyPI torch wheel for x86_64 Linux drags in ~2.5 GB of unused
# nvidia-* CUDA libraries, which does not fit a small VPS boot disk. Installing
# it first means the requirements file finds torch already satisfied.
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1+cpu \
    && python -m pip install -r /tmp/requirements.txt -c /tmp/constraints.txt

# Keep website settings below dependency installation so frontend rebuilds can
# reuse the existing Torch/PaddleOCR dependency layers on Docker Desktop.
ENV ADMIN_STATIC_DIR=/app/admin-static

COPY app ./app
COPY corpus ./corpus
COPY sql ./sql
COPY ingest.py ./
COPY admin_setup.py ./
COPY admin-static ./admin-static
COPY deploy/provider-smoke-test.py ./deploy/provider-smoke-test.py

EXPOSE 8000

# A single worker prevents every model from being duplicated in memory.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
