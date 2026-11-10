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
The [operational check guide](../docs/testing/operational-checks.md) also documents
the disposable locked Linux runner and opt-in provider probe.

## NF-04 M2 worker and recovery

The production `worker` service is opt-in and separate from Uvicorn:

```sh
docker compose --profile worker up --build --detach worker
docker compose stop worker
```

Native equivalent from `backend/`: `uv run --locked python -m neurofold.worker`.
Use the API’s same absolute NEUROFOLD_ARCHIVE_ROOT. The worker lifetime lock rejects
a second local supervisor. One active job blocks other claims until confirmed
exit or expired-owner fencing. API restart does not affect it. SIGTERM/SIGINT stop
admission and terminate/reap active children before exit. A killed supervisor’s
parent-death pipe kills its child process group; Docker `init: true` reaps orphans.
The default 5-second heartbeat/60-second lease uses a stable UTC host clock;
monotonic time supervises deadlines. macOS has no reliable RLIMIT_AS enforcement;
Linux applies the profile’s address-space ceiling. Real limits need M4 measurement.

No shipped M2 profile is executable. A production worker can run idle, and
submissions remain explicitly unavailable. Never enable the contract-only profile
by changing a request or adding a test-mode flag. The separate test image/override
copies authored output proposals; it contains test dependencies and is not a
production runtime or the M3 fake adapter.

Retain jobs.sqlite3, any live WAL/SHM, its identity marker, registered/ and staging/
together. For backup, stop API admission and gracefully stop the worker, then copy
the whole archive (or use a coordinated SQLite backup); do not copy a running DB
without its WAL. No cleanup or automatic repair is implemented. Never delete the
marker to bypass a missing database error. Preserve damaged files for inspection
and restore a verified consistent backup deliberately. A known corrupt success
returns integrity failure, not an absent job or a newly generated replacement.
Pending intents/orphan registrations after interruption are safe to retain.
Restart the worker to fence expired running/cancelling attempts as WORKER_LOST;
reads alone do not perform recovery. Explicit retries create new linked jobs and
never automatically rerun possibly completed inference.

See [transaction and crash boundaries](../docs/prediction-orchestration.md) and
[executed M2 evidence](../docs/testing/nf04-m2-evidence.md). Linux acceptance uses
`compose.prediction-test.yaml` with its own disposable project and named volume;
the driver is documented in the testing guide. Its optional cleanup retains the
volume unless `--volumes` is deliberately supplied for that disposable project.
