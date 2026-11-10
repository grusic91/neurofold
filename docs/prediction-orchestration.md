# NF-04 M2 durable local orchestration

Decision record, 2026-11-10, before implementation. M1 scientific bytes, hash
identities, schemas and synchronous `PredictionAdapter.predict(request, *,
output_dir)` remain authoritative. No shipped profile is executable in M2.

## Topology and ownership

One trusted operator, one API process, one separately launched local worker and
one active child process group. SQLite and archive must share a durable local
filesystem with working fsync, hard links and advisory locks; NFS/SMB and external
archive writers/deleters are unsupported. No authentication or distributed broker.
The API never launches children. Worker configuration selects code, never HTTP
parameters, executable paths or shell commands. Test compositions inject controlled
children separately; they are not production adapters or capability registration.

The adapter owns staging; the supervisor owns its private attempt directory and
process group. Each claim allocates fresh job attempt, worker, lease and monotonic
fence identities. No automatic execution retry, including after a worker crash.
Explicit retries use a new key/job and an unchanged spec linked to a failed or
cancelled parent. Terminal records and their attempt history are immutable.

## SQLite and idempotency

Schema version 1 uses `PRAGMA user_version`; unknown versions fail closed. Each
operation owns and closes its own connection (no cross-thread shared connection),
foreign keys, WAL, FULL synchronous durability, a bounded 1000 ms busy timeout,
short BEGIN IMMEDIATE write transactions and rollback on errors. SQL lives only
in the adapter. Jobs contain strict M1 snapshots plus independent checksums;
attempt snapshots, durable idempotency keys, publication intents and immutable
registration rows are separate tables. Reads verify snapshot/hash/index agreement.
There is no deletion/expiry policy: keys and all dependencies live as long as jobs.

Keys are explicit 1–128 ASCII `[A-Za-z0-9._:-]` characters, scoped to this local
repository across all profiles. Precedence: HTTP representation/key, verified
reference/variant, profile and M1 scientific validation, durable key comparison,
retry validation, availability/admission, insert. Identical resolved spec AND retry
parent return the existing job even if its runtime later becomes unavailable.
Different content or retry parent conflicts. Availability is included in M1's
embedded profile and therefore scientific identity; it is never silently rewritten.
Operational keys, worker/lease/fence, timestamps, retry links and progress remain
outside scientific identity. Concurrent submissions serialize on the key row.

Claims serialize globally: a running/cancelling job (even with an expired lease)
blocks new execution until recovery fences it. Version increments for every
transition, heartbeat and stage update. Stage changes preserve unknown/null
progress; they require the active identity and unexpired lease. All worker writes
check worker AND lease identity in addition to attempt/fence/version/state.

## Supervision and clocks

Default heartbeat 5 s, lease 60 s, child execution deadline from profile;
supervision also bounds staged bytes, control messages and publication. UTC wall
clock owns leases; monotonic clock owns process deadlines. Clock rollback fails
eligibility; operators must maintain a stable clock. Forward jumps can fail work.
Only a live unexpired owner can renew. Database failures or lost ownership cause
termination, never continued inference on an assumed lease. Restart reconciliation
fences expired active attempts and fails WORKER_LOST, including cancelling jobs
whose termination cannot be confirmed. It never claims they were cancelled.
A lifetime worker file lock prevents another local supervisor launching while an
old worker is alive. Children receive a parent-death pipe: EOF terminates their
process group even if the supervisor was SIGKILLed. Recovery does not automatically
rerun inference; stale output cannot regain ownership. API restart changes nothing.

SIGINT/SIGTERM stop admission, request child termination and reap before returning.
Termination sends SIGTERM to the session/process group, waits a bounded grace,
then SIGKILL and waits for confirmed exit. Capacity is held through reaping and
publication/failure handling. Unconfirmed exit is failed, never cancelled.
Cancellation of queued jobs confirms execution never began; running cancellation
moves to cancelling; only confirmed termination moves it to cancelled. Timeout and
shutdown are failed attempts unless cancellation already won. Child crash,
malformed/bounded-output failure and publication integrity fail safely without
exposing logs, local paths or sequences in error messages.

Child input is strict `PredictionJob` JSON in request.json. Output is a separately
versioned bounded proposal bundle (result, manifest, descriptor/base64-byte pairs),
without paths. Only fixed argument arrays are launched, with no shell. Future
adapter children call the existing synchronous seam. The supervisor checks the
proposal's original attempt identity against its launch snapshot, then seals only
operational execution times/current heartbeat snapshot and recomputes manifest and
result hashes. These are unregistered proposals, not rewritten retained history.
M1's exact manifest-attempt equality is preserved. No scientific metadata is
invented: complete authored proposals are used only in tests. End time records
supervisor sealing after confirmed child exit, before graph verification and
registration; the final commit separately checks the live clock.

## Filesystem/database publication and transactional success

A SQLite transaction does NOT make filesystem writes atomic. Publication order:

1. Create a durable SQLite intent for the exact active version/owner.
2. Under the prediction archive publication lock, validate the full M1 graph,
   source/variant, sizes, lineage, evidence, provenance and bytes outside SQL.
3. Copy verified source dependencies, raw artifacts, reference/variant, mappings,
   manifest and result into the prediction archive using fsynced same-directory
   staging + no-clobber hard links + directory fsync. Retain originals unchanged.
4. Record exact kind/ID/canonical-or-raw hash and size registration rows only after
   durable registration. Store the exact dependency graph and result/manifest
   references in the durable intent. Registration rows cannot be replaced/deleted.
5. In the final BEGIN IMMEDIATE transaction, load the actual current job and intent;
   check running state, expected version, active attempt, worker, lease, fence,
   not fenced, unexpired at CURRENT clock, cancellation absent, exact intent graph
   and every immutable ready registration still eligible. Only then bind the exact
   result/manifest refs, transition to succeeded and mark intent committed together.

Prior validation is never authority for a later success. Concurrent cancellation,
lease expiry/recovery and success serialize on the SQLite writer transaction.
A cancellation winner changes state/version; success loses. A committed success
makes later cancellation a terminal conflict. The archive lock and registration-only
API protect against replacement/deletion within this topology, without holding SQL
transactions during hashing or execution. Out-of-band malicious modification is
not prevented; retained reads detect corruption and never repair it.

Before intent: only orphan staging. After intent/before registration: pending
intent and staging. During registration: complete immutable orphan files may
remain; they are never results. After registration/before success: ready intent
and orphan registrations may remain. On restart expired owners are fenced, intents
abandoned, no inference/publication replay occurs. After success commit: exact
registered graph is authoritative and survives process recreation. Response loss
or IO failure can leave committed state: read the job or deliberately repeat the
same idempotency key; never infer rollback or automatically create a new job.
No garbage collection is provided; cleanup must not delete referenced data.
Every successful job/result/manifest/artifact read verifies the retained graph,
including input copies, checksums, byte sizes and M1 publication validation. Known
missing/corrupt dependencies are integrity errors, never 404 or silent repair.

## HTTP v1

Prediction job/profile/artifact IDs accept M1’s full 1–160 ASCII identifier
bound; reference/variant fields retain their existing 1–128 HTTP convention.
All POST fields are required, including explicit nulls. Submission fields:
`reference_id`, `variant_id`, `adapter_profile_id`, `parameters` (strict scalar
values), `seed`, `msa_artifact_id`, `retry_of_job_id`. M2 supports explicit null MSA
only; local/remote execution stays unavailable until a reviewed profile supports
it. Required single `Idempotency-Key`; unknown/duplicate fields/query/headers fail.
Production code identity is operator configured; absent identity blocks submission.

- GET /v1/prediction-capabilities: 200 array of unchanged M1 capabilities; static,
  independent of database/archive/model readiness.
- POST /v1/prediction-jobs: 202 status envelope (also duplicates), Location and Retry-After: 1.
- GET /v1/prediction-jobs/{id}: 200 status envelope; Retry-After: 1 if active.
- POST /v1/prediction-jobs/{id}/cancel: empty JSON object; queued -> 200 cancelled,
  running/cancelling -> 202; already cancelled -> 200; succeeded/failed -> 409.
- GET /v1/prediction-jobs/{id}/result or /manifest: 200 unchanged M1 record when
  succeeded, 409 otherwise. Controlled artifact links are
  /v1/prediction-jobs/{id}/artifacts/{artifact_id}; only the bound graph is readable.

Unknown jobs -> 404; bad input/key -> 422; conflicting key/version/lifecycle ->
409; capacity -> 429/Retry-After: 1; unavailable profile/worker/configuration/SQLite
busy -> 503; known retained corruption -> 500 ARCHIVE_INTEGRITY. Existing typed
M1 errors retain code/stage. Existing request-ID/error envelope and 16 KiB body
limit apply. Blocking work, graph verification and serialization run in the
existing bounded executor. 504 mutation timeout explicitly reports uncertain
outcome/no automatic retry. Health/startup never open the archive/database. Polls
read storage only, never providers or execution. Frontend polling remains M3.


The status envelope is exactly `neurofold-prediction-status/1` with required
`schema_version`, unchanged M1 `job` and explicit nullable `operational_failure`.
Operational failure labels are WORKER_LOST, TIMEOUT, SHUTDOWN, CHILD_FAILED,
INVALID_OUTPUT, PUBLICATION_FAILED or SUPERVISION_FAILED. They supplement the
unchanged M1 failure enum rather than extending frozen job v1 bytes. Additive
[status](schemas/neurofold-prediction-status-1.schema.json) and
[child proposal](schemas/neurofold-child-proposal-1.schema.json) schemas are
reproducible with `uv run --locked python scripts/prediction_m2_schema.py`.
OpenAPI derives exact required nested shapes without filesystem/model imports.
Each retained read transaction uses a consistent SQLite snapshot across job and
attempt rows, including operational failure lookup during concurrent heartbeats.
