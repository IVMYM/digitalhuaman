# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend
WORKDIR /src
ARG NPM_REGISTRY=
COPY frontend/package.json frontend/package-lock.json ./
RUN if [ -n "$NPM_REGISTRY" ]; then npm config set registry "$NPM_REGISTRY"; fi \
    && npm ci
COPY frontend/ ./
ENV NODE_OPTIONS=--max-old-space-size=768
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/data \
    STATIC_DIR=/app/static \
    UVICORN_WORKERS=1
WORKDIR /app
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" -r /app/requirements.txt
COPY backend/app /app/app
COPY --from=frontend /src/dist /app/static
RUN mkdir -p /data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1} --proxy-headers --forwarded-allow-ips '*'"]
