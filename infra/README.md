# Development infrastructure

Run `docker compose up --build --wait` from the repository root. Compose uses
`docker/backend.Dockerfile` and `docker/frontend.Dockerfile`, each with the
repository root as its build context. See the root README for URLs and native
development instructions.

- Backend: Python 3.12 slim, version-pinned uv, locked runtime dependencies, and a
  non-root user. Compose adds Uvicorn reload for the mounted Python source.
- Frontend: Node 24 Debian slim, `npm ci`, a non-root user, and Vite with live reload.
  Its server-only proxy target is the Compose backend service.
- Source mounts are read-only. Virtual environments and `node_modules` stay inside
  their respective images, avoiding macOS/Linux binary incompatibilities and stale
  dependency volumes. Rebuild images after manifest or lockfile changes.
- Host bindings use `127.0.0.1`; internal listeners use `0.0.0.0`. Health checks
  gate frontend startup and allow `docker compose up --wait` to await both services.
- `.dockerignore` excludes secrets, local tool environments, and scientific
  artifacts. Dockerfiles explicitly copy the original repository license.

Validate syntax without a daemon using `docker compose config --quiet`. With a
daemon running, use `docker compose up --build --wait` and check:

```sh
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:5173/
curl --fail http://127.0.0.1:5173/api/health
docker compose down
```

CI runs these container checks on Linux. These images are for development.
Production static serving, immutable base-image digests, resource limits,
deployment configuration, and a separate NVIDIA CUDA inference image are future
work. No image publishing or deployment workflow is configured.


NF-02 M4 retains biological records in the private `biological-archive` named
volume at `/app/data/archive`. The image precreates/chowns/chmods the mountpoint
for its non-root user; Docker initializes a new named volume from it. Existing
volumes need compatible ownership. Normal `docker compose down` retains records;
`down --volumes` deletes the archive. One process/operator is supported.
See [configuration and offline smoke commands](../docs/integration.md).
`compose.offline.yaml` is only for deterministic authored-fixture acceptance;
normal Compose uses HTTPX and contacts providers only on requested operations.
