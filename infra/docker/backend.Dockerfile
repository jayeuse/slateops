# Keep the Node major equal to the root .node-version pin.
FROM node:26-alpine@sha256:6bd9ab43c0ec0190ca7b2d193906cb8b7edf6e7f4afa43ddeccd6452710bffb5 AS frontend-builder

WORKDIR /workspace/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
COPY contracts/ /workspace/contracts/
RUN npm run build


FROM python:3.14-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f AS backend-builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.12.13@sha256:b485bd65cc2cf1c9a93b3554012c9c3778cf7b1b5fd3d3096ce9e1226c97e1e6 /uv /uvx /bin/

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/ ./

FROM python:3.14-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    SLATEOPS_ENV_SOURCE=process \
    WEB_ASSETS_ROOT=/app/web

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser
COPY --from=backend-builder --chown=appuser:appuser /app /app
COPY --from=frontend-builder --chown=appuser:appuser /workspace/frontend/out /app/web
COPY --chown=appuser:appuser infra/supabase/templates/ /infra/supabase/templates/

# The release workflow passes the tag without "v" (scripts/check_release_version.py).
# Declared after the copies so a new version reuses the cached layers above.
ARG SLATEOPS_VERSION=0.0.0+dev
LABEL org.opencontainers.image.version=$SLATEOPS_VERSION
ENV SLATEOPS_VERSION=$SLATEOPS_VERSION

USER appuser

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['BACKEND_PORT'] + '/api/health', timeout=2).read()"]
CMD ["python", "-m", "app"]
