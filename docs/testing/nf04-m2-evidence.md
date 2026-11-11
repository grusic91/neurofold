# NF-04 M2 — Durable orchestration evidence

Historical implementing-agent evidence for the named source state below. The
independent review found additional blockers; this document is not current approval.
See the [separate hardening checkpoint](nf04-m2-hardening-evidence.md).

Date: 2026-11-10. Initially clean checkout
`ca74e9e0c0d291a7f1ec6822e65aec3bf7888878`. **M2 implementation and required
native/Linux acceptance are complete.**
All changes are uncommitted. No commit, push, publication or PR. No Boltz-2,
weights, GPU, real inference, executable fake adapter or frontend prediction UI.
This is implementing-agent software evidence, not independent scientific approval.

## Contracts and consistency

[Orchestration decisions](../prediction-orchestration.md) were written before the
storage/worker implementation. Core stays standard-library-only; application
services import core seams, while SQLite/filesystem/process implementations live
in adapters. The API never launches a child or invokes prediction. One trusted
operator, one API process and one separate local worker are supported.

Scientific M1 contracts, identities, schemas and authored fixture bytes are
unchanged. NF-02/NF-03/NF-08 archives retain their original bytes and semantics.
SQLite schema 1 stores strict checksummed job snapshots, attempts, durable keys,
publication intents and immutable registrations. Each operation owns/closes its
connection; WAL/FULL, foreign keys, short BEGIN IMMEDIATE transactions and 1000 ms
busy handling apply. Reads use a consistent transaction snapshot across job and
attempt rows. A durable identity marker prevents missing DB history from being
silently recreated. No deletion, retention expiry, broker or automatic retry.

Submission verifies exact references/variants, resolves M1 defaults/hashes and
persists the complete spec. Concurrent identical keys converge, different content
conflicts; keys survive reopening. Explicit retries create linked new jobs.
Versioned heartbeats/stages, lease/worker/attempt/fence identities and immutable
terminal history preserve M1 lifecycle. Queued cancellation confirms no execution;
running cancellation becomes cancelled only after confirmed exit/reaping. Expired
owners are fenced and fail WORKER_LOST; possibly completed inference is not rerun.

A prior publication validation never authorizes a later success. Filesystem
registration happens before ready SQL rows: bounded staged bytes are verified,
fsynced and hard-linked without replacement, including exact input copies,
raw dependencies, mappings, manifest and result. A durable intent binds this
exact graph. The final transaction rechecks running state/version, active
attempt/worker/lease/fence, current expiry, execution deadline, cancellation and
every immutable ready registration before binding result/manifest refs and
committing success. Cancellation, expiry and success serialize on that writer.
There is no filesystem/SQL atomicity claim. Crash boundaries can leave orphan
stages/registrations/intents; restart fences expired owners, never replays output
or exposes unregistered success. Every retained success read verifies its graph;
missing/corrupt dependencies are integrity errors, never ordinary absence/repair.

## Process and HTTP behavior

The separate worker has a lifetime file lock, private fresh attempt directories,
argument-only trusted module launch, process groups, parent-death EOF guard,
heartbeats, monotonic execution deadlines, per-file/CPU/Linux address-space bounds,
SIGTERM grace then SIGKILL, confirmed wait/reaping and shutdown admission control.
Lost ownership/heartbeat failures terminate children. Publication/termination
capacity is never released by cancelling an HTTP awaiter. macOS address-space
limits are not claimed. Real hardware/runtime limits remain M4 work.

Test-only children copy authored M1 proposal bundles or wait/crash/ignore
termination; no prediction algorithm or production capability is added. The
supervisor validates the proposal’s launch identity before sealing operational
execution time/current heartbeat, then rehashes unregistered manifest/result.
This satisfies M1’s exact full-attempt equality without rewriting retained bytes.

Seven HTTP resource paths implement capabilities, submit/get/cancel,
result/manifest and job-graph-bound artifacts. Strict required fields/nulls,
Idempotency-Key, 202/200/409, Location/Retry-After, sanitized error/request IDs and
bounded executor uncertainty semantics are documented. An additive
`neurofold-prediction-status/1` envelope wraps the unchanged M1 job and nullable
operational failure reason; `neurofold-child-proposal/1` versions child staging.
OpenAPI exposes required nested shapes; both additive schemas are reproducible.
Static capabilities and health never touch storage/runtime readiness. All shipped
profiles remain contract_only/unavailable. No polling can execute a provider/model.

## Executed offline tests

M2 adds **79 tests** across durable storage, supervision and HTTP suites:

- Eight synchronized independent SQLite submissions, four overlapping HTTP
  submissions, durable keys/conflicts/reopening, exact source/variant linkage,
  unavailable execution, defaults, explicit linked retries and terminal history.
- Competing atomic claims, version/worker/lease/fence/clock/deadline rejection,
  renewals, expiry/recovery, cancellation versus ready publication and a real
  barrier-synchronized cancellation/success race with one serialized winner.
- Complete graph registration/reopening; bad bytes/spec/attempt/provenance/
  evidence/missing or unlisted output; missing/corrupt/symlink retained inputs,
  outputs/maps/roots; schema/contention/checksum and missing DB integrity.
- Real abrupt process exits after intent, first artifact, registration, ready and
  success commit; IO failure before/after registration, SQLite readiness and
  response loss after commit. Recovery never invents success or rewrites history.
- Real guarded children with FIFO/event barriers: success/crash/missing/malformed/
  oversized output, cancellation, ignored termination/forced kill, timeout,
  shutdown, heartbeat failure, confirmed reaping and actual parent-death EOF.
- HTTP strict types/required nulls/unknowns/duplicate headers/keys, response
  schemas, retained artifacts, errors, startup/health/capability isolation,
  admission/uncertain timeout and draining. All-core import isolation and frozen
  compatibility remain in the full suite.

Linux smoke exposed a failure-reason read spanning a heartbeat’s two snapshots.
The adapter now begins a read transaction there; a trace-callback/event regression
pauses between the actual job/attempt reads while another connection commits a
heartbeat. This establishes snapshot consistency rather than relying on sleeps.

Every new source-backed fixture is inventoried in fixtures.json. Existing fixture
hashes changed only for edited test assertions; standalone frozen fixture bytes,
LICENSE and dependency manifests/locks were verified unchanged with git diff.

## Native checkpoints

macOS Apple Silicon, uv **0.13.7**, default CPython **3.12.16**, alternate
CPython **3.13.2**, Node **v24.5.0**, npm **11.5.1**. No dependencies changed.
`UV_CACHE_DIR=/private/tmp/neurofold-uv` was set for all uv invocations because the
default user cache is outside the write sandbox. Python 3.13 locked wheels needed
network-enabled installation into its separate temporary environment.

From backend:

```sh
uv sync --locked
uv run --locked python --version
uv run --locked ruff check . ../infra/testing
uv run --locked ruff format --check . ../infra/testing
uv run --locked mypy src tests scripts ../infra/testing
uv run --locked pytest
```

Python 3.12: all passed, **91 strict-mypy files**, **1,946 tests passed**,
**95.09%** combined statement/branch coverage (90% gate), 81.19 seconds.
Final fixture inventory/lint/format/mypy rechecks also passed.

For every alternate command, set
`UV_PROJECT_ENVIRONMENT=/private/tmp/neurofold-nf04-m2-py313` and the same cache,
and consistently supplied `--python 3.13`:

```sh
uv sync --locked --python 3.13
uv run --locked --python 3.13 python --version
uv run --locked --python 3.13 ruff check . ../infra/testing
uv run --locked --python 3.13 ruff format --check . ../infra/testing
uv run --locked --python 3.13 mypy src tests scripts ../infra/testing
uv run --locked --python 3.13 pytest
```

Python 3.13: all passed, **91 files**, **1,946 tests**, **95.09%** coverage,
79.69 seconds, no warnings. COVERAGE_FILE was isolated at
`/private/tmp/neurofold-nf04-m2-coverage313`. Default .venv remains Python 3.12.
An earlier 3.13 run exposed test connection cleanup warnings; test connections now
explicitly close, and the final full run above is clean.

From frontend, Node 24:

```sh
npm ci --cache /private/tmp/neurofold-npm-cache --offline
npm run lint
npm run typecheck
npm run build
npm run test
npm run test:browser
npm run test:integration
```

All passed: **36 component tests / 4 files**, **12 browser tests** (Chromium and
WebGL-disabled), **1 actual browser → Vite proxy → production biological routes**
integration test. Browser listeners required execution outside the restricted
sandbox; the initial sandbox EPERM was not treated as a product failure. No
frontend source or lockfile changes. No prediction interaction was added.

## Linux/container acceptance

Colima’s existing stopped runtime was started for this assignment. Docker client
**29.5.2** (macOS ARM64); server **29.2.1**, Linux **x86_64/AMD64**, kernel
**6.8.0-100-generic**, glibc **2.41**, container CPython **3.12.16**, SQLite
**3.46.1**, non-root UID **999**, frontend Node **v24.22.2**. This is emulated
Linux AMD64, not the historical NF-02 ARM64 run and not NVIDIA hardware.

Normal API/frontend/idle standalone worker images built successfully. The
isolated normal stack used BACKEND_PORT=18000, FRONTEND_PORT=15173 and project
neurofold-nf04-m2-prod:

```sh
docker compose -p neurofold-nf04-m2-prod --profile worker up --build --detach --wait --wait-timeout 120 backend frontend worker
# After startup-budget failure under emulation, services became healthy:
docker compose -p neurofold-nf04-m2-prod --profile worker up --detach --wait --wait-timeout 180 backend frontend worker
```

Actual health/page/proxy checks returned 200 at 18000/health, 15173/ and
15173/api/health; runtime/non-root versions were queried in the containers.
The stack stopped/removed cleanly, retaining its isolated named volume. Slow
emulated Python process startup initially exceeded the existing 3-second health
command budget. The controlled test override now uses a 15-second command timeout
and 45-second start period; production liveness behavior is unchanged.

Controlled-child image build and Compose config passed. Earlier executed phases
verified non-root persistent writes, successful publication/idempotency after
backend recreation, cancellation and graceful shutdown. The initial timeout phase
found the snapshot race above. A later startup-budget interruption was also
recorded; neither partial run is claimed as full acceptance.

Final executed controlled acceptance **passed** with the corrected snapshot
read and test-only emulation health budget:

```sh
docker compose -p neurofold-nf04-m2 -f compose.yaml -f compose.prediction-test.yaml config --quiet
docker compose -p neurofold-nf04-m2 -f compose.yaml -f compose.prediction-test.yaml build backend controlled-worker
docker compose -p neurofold-nf04-m2 -f compose.yaml -f compose.prediction-test.yaml up --detach --wait --wait-timeout 180 backend controlled-worker
python3 infra/testing/prediction_smoke.py
docker compose -p neurofold-nf04-m2 -f compose.yaml -f compose.prediction-test.yaml run --rm --no-deps controlled-worker pytest tests/test_prediction_http.py::test_prediction_paths_accept_full_m1_identifier_bounds --no-cov
```

The driver completed every phase: frontend/proxy/API health, non-root persistent
writes, verified success and identical key/job/result after API recreation,
cancellation with confirmed termination, graceful shutdown, ignored termination
with timeout/forced kill, SIGKILL worker loss, lease-expiry restart to WORKER_LOST
and no rerun, then Linux stale-owner/storage/race/abrupt-publication/process tests.
**78 tests passed in 219.11 seconds**, followed by the final M1 160-character HTTP
identifier regression (**1 passed in 12.63 seconds**). Both Linux runs emitted
one harmless pytest cache warning because the non-root test image’s application
directory is read-only; tests and required persistent-storage writes passed.
The transient pytest cache is not retained job storage.

Normal, offline biological and prediction Compose syntax checks all passed.
CI now executes this controlled composition after existing service/proxy and
biological retention checks. No remote Actions run was triggered or inferred.
The isolated stacks were stopped/removed; their named volumes remain retained.
Colima was left running. No unrelated stack or archive was modified.

No required M2 check remains unavailable.

## Remaining gates

M2 software/process/storage acceptance is complete. M3 executable synthetic
prediction/frontend polling, M4 reviewed release/weights/licenses/runtime/MSA/
hardware limits, M5 real Boltz-2 integration, exports and independent scientific
acceptance remain open. Process/storage tests establish no prediction accuracy,
biological effect, clinical utility or scientific approval. Power-loss and
malicious out-of-band storage modification are not simulated.
