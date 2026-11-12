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
admission and attempt bounded termination/reaping before exit. Unconfirmed cleanup
blocks further work, attempts bounded outcome recording and exits 78; it does not
claim successful termination. A killed supervisor’s
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
If no worker-block.json is retained, restart the worker to fence expired
running/cancelling attempts as WORKER_LOST;
reads alone do not perform recovery. Explicit retries create new linked jobs and
never automatically rerun possibly completed inference.

See [transaction and crash boundaries](../docs/prediction-orchestration.md) and
[executed M2 evidence](../docs/testing/nf04-m2-evidence.md). Linux acceptance uses
`compose.prediction-test.yaml` with its own disposable project and named volume;
the driver is documented in the testing guide. Its optional cleanup retains the
volume unless `--volumes` is deliberately supplied for that disposable project.


### Unconfirmed cleanup and manual recovery

Both production and controlled workers use one exit-code contract:

- **0:** normal requested shutdown with no retained integrity block.
- **78 / UNCONFIRMED_CLEANUP:** uncertain process cleanup or an inaccessible marker
  check; follow the process-recovery procedure below. Do not resume automatically.
- **65 / ARCHIVE_INTEGRITY:** startup or running-queue integrity damage. Stop
  admission, preserve DB/WAL/identity/staging/registered data, inspect and restore a
  consistent backup deliberately before restart. This path creates no cleanup
  marker by itself; if one is present, also complete the exit-78 procedure.
- Other uncaught failures retain Python's usual unsuccessful crash behavior.

Integrity diagnostics contain the reason/code, error_type and fixed authored
validation message, without a traceback or chained exception details.
Only recognized authored messages are emitted; wrapped/unrecognized detail falls
back to "Retained archive validation failed" rather than echoing retained input.
A normal SIGTERM after an integrity park still exits 65, not 0 or 78. Keep restart
disabled for this condition; M3's future
restart/readiness policy must preserve the manual gate.

A private `staging/worker-block.json` under the prediction worker root records
worker/job/attempt IDs, PID/PGID when available, error class, blocked reason,
UTC created_at, owning host/container host_id, and child_launched_at (launch-call
start time, which is not claimed to equal kernel process birth time).
Hostname lookup failure records host_id=null and never prevents the blocking
marker or the specific outcome record. Treat a missing host reference as requiring
additional investigation before restart.
It contains no sequences, proposal bytes or raw exception messages. The production
path is `$NEUROFOLD_ARCHIVE_ROOT/predictions/staging/worker-block.json`; the explicit
controlled-test composition uses `$NEUROFOLD_ARCHIVE_ROOT/staging/worker-block.json`.
The final log also reports `outcome_recorded` and `block_retained`. A partial,
corrupt, symlinked or otherwise present marker blocks startup before recovery or
claim; lstat errors other than missing-file also block, with the errno name
logged. Deleting it is not routine retry handling. Include it with archive backups.

1. Stop admission and the worker; disable any external automatic restart for exit
   78. Preserve logs, the marker, staging, DB/WAL/identity and registered artifacts.
2. Inspect the recorded job and attempt and the owning host/container process
   namespace. Compare host_id with the hostname inside that host/container, and
   worker_id with the critical log. Compare the OS process start time with the
   interval from child_launched_at to created_at, accounting for clock accuracy;
   also verify the command/staging ownership before acting. Missing/partial fields
   require more investigation, never bypass. PID/PGID numbers can be reused. Establish that the owned group and helpers have exited,
   or deliberately stop the owning container/processes. API health is not proof of
   termination. Do not kill an unrelated process based only on a stale number.
3. Check whether the specific SUPERVISION_FAILED outcome was retained. When it was
   not, leave the job unchanged until its owner lease expires and reconcile it by
   normal worker recovery only after resolving termination uncertainty. Recovery
   will record WORKER_LOST for an expired active attempt, never invent cancelled.
   Inspect storage/permissions if `block_retained=false` or recording failed.
4. After confirming cleanup and storage consistency, retain a private copy of the
   block in ignored operator evidence and deliberately remove only the blocking
   marker. Do not edit terminal rows, drop triggers, delete DB identity or remove
   staging/registered evidence. Start a **new** worker manually; a blocked instance
   cannot be resumed by clearing its stop Event.
5. Verify the retained outcome/recovery and the queued work before restoring
   admission. Explicit retries are new linked jobs; never silently rerun an
   uncertain attempt or fabricate a scientific result.

This procedure closes the M2 uncertainty gate. General readiness/restart policy,
rolling schema compatibility, terminal-write retries outside this cleanup path,
mutation recovery, dependency naming and harness conditions remain M3 work. H1
mapping correction and biological-foundation review remain separate prerequisites
before scientific interpretation or NF-05/NF-06 acceptance.


The default and controlled worker stop_grace_period is 20 seconds. The design's
conservative default double-cleanup/recording allowance is about 15.8 seconds plus
filesystem and scheduler margin; the review's measured 6.7 seconds is not a hard
maximum. Recompute and re-measure before changing child grace, lease or storage
behavior, and at M4 before enabling real runtime helpers. Keep the stop grace
above the computed/measured total plus margin; never use force-kill timing as
proof of confirmed scientific execution cleanup.
