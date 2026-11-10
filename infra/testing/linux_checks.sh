#!/bin/sh
# Source-only input is extracted into a disposable Linux container filesystem.
set -eu
export UV_CACHE_DIR=/work/.cache/uv
printf 'Linux acceptance mode: %s\n' "$1"
uname -a
uv --version
node --version
npm --version
case "$1" in
  python312|python313)
    case "$1" in python312) runtime=3.12;; python313) runtime=3.13;; esac
    cd backend
    uv sync --locked --python "$runtime"
    uv run --locked --python "$runtime" python --version
    uv run --locked --python "$runtime" ruff check . ../infra/testing
    uv run --locked --python "$runtime" ruff format --check . ../infra/testing
    uv run --locked --python "$runtime" mypy src tests scripts ../infra/testing
    uv run --locked --python "$runtime" pytest
    ;;
  frontend)
    cd backend
    uv sync --locked --python 3.12
    cd ../frontend
    npm ci
    npm run lint
    npm run typecheck
    npm run build
    npm run test
    npm run test:browser
    npm run test:integration
    ;;
  *) printf 'Unknown Linux acceptance mode\n' >&2; exit 2;;
esac
