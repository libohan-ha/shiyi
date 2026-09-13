FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    SHIYI_DATABASE_URL=sqlite:////app/backend/data/shiyi.db \
    SHIYI_DATA_DIR=/app/backend/data \
    SHIYI_FRONTEND_DIR=/app/frontend/dist
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
COPY --from=frontend /build/dist /app/frontend/dist
COPY deploy/entrypoint.sh /app/entrypoint.sh
RUN groupadd --gid 10001 shiyi && useradd --uid 10001 --gid shiyi --no-create-home shiyi \
    && mkdir -p /app/backend/data/media \
    && chown -R shiyi:shiyi /app/backend/data \
    && chmod +x /app/entrypoint.sh
USER 10001:10001
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["/app/backend/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=4)"]
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["/app/backend/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765", "--proxy-headers", "--forwarded-allow-ips", "*"]
