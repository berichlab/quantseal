# syntax=docker/dockerfile:1

# --- Stage 1: Build static React + Vite Research Console ---
FROM node:22-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Lean Python 3.12 runtime (no Node, no browser bloat) ---
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="QuantSeal by BeRichLab" \
      org.opencontainers.image.description="Self-hosted anti-overfitting autonomous quant research lab" \
      org.opencontainers.image.vendor="BeRichLab" \
      org.opencontainers.image.source="https://github.com/berichlab/quantseal" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    QUANTSEAL_DATA_DIR=/data \
    QUANTSEAL_HOST=0.0.0.0 \
    QUANTSEAL_PORT=8000

WORKDIR /app

RUN useradd --create-home --shell /bin/bash quantseal \
    && mkdir -p /data \
    && chown -R quantseal:quantseal /data /app

COPY pyproject.toml README.md LICENSE ./
COPY quantseal/ ./quantseal/
COPY --from=frontend-builder /build/quantseal/static ./quantseal/static

RUN pip install --upgrade pip \
    && pip install --no-cache-dir . \
    && chown -R quantseal:quantseal /app /data

USER quantseal
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["python", "-m", "quantseal", "serve", "--host", "0.0.0.0", "--port", "8000"]
