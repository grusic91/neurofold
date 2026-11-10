# Test-only controlled children and locked checks. Never a model runtime image.
FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy \
    PATH="/app/backend/.venv/bin:$PATH" PYTHONPATH="/app/backend/tests:/app/smoke"
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-install-project
COPY backend/src ./src
COPY backend/tests ./tests
COPY infra/testing /app/smoke
COPY LICENSE /app/LICENSE
RUN uv sync --locked && groupadd --system neurofold \
    && useradd --system --gid neurofold --create-home neurofold \
    && mkdir -p /app/data/archive \
    && chown neurofold:neurofold /app/data/archive && chmod 700 /app/data/archive
USER neurofold
ENV NEUROFOLD_ARCHIVE_ROOT=/app/data/archive
