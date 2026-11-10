FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/backend/.venv/bin:$PATH"

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/src ./src
COPY LICENSE /app/LICENSE
RUN uv sync --locked --no-dev \
    && groupadd --system neurofold \
    && useradd --system --gid neurofold --create-home neurofold

USER neurofold
EXPOSE 8000
CMD ["uvicorn", "neurofold.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
