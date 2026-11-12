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

Schema version 2 uses `PRAGMA user_version`; verified version 1 databases migrate
by adding failure-extension tables and a legacy-failure inventory, without changing
any job/attempt/publication/scientific bytes. Unknown versions fail closed. Each
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

SIGINT/SIGTERM stop admission and request bounded child cleanup before returning.
Termination sends SIGTERM to the session/process group, waits a bounded grace,
then SIGKILL. Leader reaping waits at most max(0.5 seconds, grace), with death-pipe
closure attempted in a finally block. Darwin EPERM first permits a 0.5-second
leader-exit wait, then signal retries every 1 ms for at most 100 ms while exiting
same-group helpers disappear. Persistent refusal remains a cleanup failure; a
leader's exit alone cannot excuse an unsignalable group member.

Unconfirmed cleanup retains staging/worker-block.json before bounded outcome
recording. Job/attempt ownership checks remain mandatory; get/finish retry SQLite
contention, and same-attempt JOB_CONFLICT from a concurrent cancellation, using
min(2 seconds, lease/4) as a retry-scheduling budget even after shutdown is requested.
This is not a hard wall-clock deadline: backoff and the final attempt can extend
it, including a final SQLite busy timeout of up to one second (2.17 seconds was
measured in review for a nominal two-second phase).
Then the worker blocks with UNCONFIRMED_CLEANUP and exits 78. Its safe diagnostics
contain job/attempt/worker IDs, PID/PGID when available, error class, whether the
block was retained and whether the outcome was recorded. They exclude exception
messages, sequences, request bodies and child output. Successful cleanup and
normal requested shutdown retain exit 0 only when the worker is not integrity-
blocked. The common entrypoint contract is 0 for a normal requested shutdown,
78 only for UNCONFIRMED_CLEANUP, and 65 (data error) for ARCHIVE_INTEGRITY detected
either during startup or in the running queue. Integrity parks until requested
stop, logs a safe critical reason/code, error_type and fixed authored validation
message without traceback or chained exception details, and creates no cleanup
marker by itself. Uncaught errors keep Python's ordinary nonzero crash behavior.
This distinguishes storage restoration from uncertain-process recovery.
Only recognized fixed authored integrity messages are emitted; wrapped or
unrecognized detail uses a generic validation message so retained input cannot
enter the log.

The block is checked before recovery or claim on every new worker, including when
its contents are partial or invalid. The presence check uses lstat: only
FileNotFoundError means no marker. EACCES, ENOTDIR and other stat errors block
before recovery/claim with exit 78 and an errno name, without exception text. Clearing an in-memory stop Event cannot
resume a blocked worker. Unconfirmed termination is never cancelled: while storage
and ownership permit, it records failed/SUPERVISION_FAILED with termination false.
If the bounded recording attempt fails, the retained block still prevents new
work; an operator must inspect it and reconcile the outcome. Physical block-write
failure is explicitly logged, still exits 78, and must never trigger automatic
restart. See the manual recovery procedure in [infra/README](../infra/README.md#unconfirmed-cleanup-and-manual-recovery).
Normal crash/lease recovery without an uncertainty block remains unchanged.
Cancellation of queued jobs confirms execution never began; running cancellation
moves to cancelling; only confirmed termination moves it to cancelled. Timeout and
shutdown are failed attempts unless cancellation already won. Child crash,
malformed/bounded-output failure and publication integrity fail safely without
exposing logs, local paths or sequences in error messages.

A launcher owns every process it creates until it returns the Child handle.
An ordinary launch exception guarantees that no process remains unconfirmed. If
startup fails and bounded cleanup cannot confirm termination, LaunchCleanupError
transfers the child handle to the supervisor, which retries bounded cleanup and
uses the same blocked-outcome path if still uncertain. This applies to production
and controlled-test launchers. Optional process identity comes from the child
handle; the supervisor never infers an arbitrary adapter's PGID from a PID.

Child input is strict `PredictionJob` JSON in request.json. Output is a separately
versioned bounded proposal bundle (result, manifest, descriptor/base64-byte pairs),
without paths. Only fixed argument arrays are launched, with no shell. Future
adapter children call the existing synchronous seam. The supervisor checks the
proposal's original attempt identity against its launch snapshot, then seals operational execution times/current heartbeat snapshot and assigns
owned output identities as defined below, recomputing mapping/manifest/result
hashes without changing raw bytes or scientific hash domains. These are unregistered proposals, not rewritten retained history.
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
reproducible from `backend/` with
`uv run --locked python -m scripts.prediction_m2_schema`.
OpenAPI derives exact required nested shapes without filesystem/model imports.
Each retained read transaction uses a consistent SQLite snapshot across job and
attempt rows, including operational failure lookup during concurrent heartbeats.


## Independent-review hardening decisions (2026-11-11)

These decisions supersede conflicting operational statements in the original M2
record above. See the [separate acceptance checkpoint](testing/nf04-m2-hardening-evidence.md).

### Retained database identity and initialization

An absent database with no marker is the only fresh-initialization case. An
existing zero-byte/unversioned file is not fresh. A marker with missing/empty/
truncated/incompatible/incomplete database fails closed; old keys cannot create
replacement jobs. A bounded advisory initialization lock serializes WAL selection,
schema creation/migration and fsynced marker publication across processes.
Established files open with SQLite `mode=rw`, so later missing files cannot be
recreated. Reopening checks exact tables/indexes/triggers, version, SQLite
quick_check and foreign keys before any migration. A complete version-1 database
without a marker (crash after DB commit) can acquire its marker after validation;
an incomplete first creation needs explicit operator recovery. Retain the database,
WAL, identity marker and registered archive together; never erase the marker to
"fix" missing history. SQLite contention is retryable, not evidence of corruption.

### Supervision, liveness and bounded output

Worker polling retries SQLite contention with exponential backoff capped at one
second; operation-level retries use a min(2 seconds, lease/4) scheduling budget,
not a hard elapsed-time cap. A final attempt can add SQLite's one-second busy
wait, and backoff/scheduling can extend elapsed time. Event waits
allow prompt SIGINT/SIGTERM shutdown. Active contention never assumes ownership:
if its retry budget is exhausted, the child is reaped and the attempt fails or
is left for lease-expiry recovery when storage cannot record the failure.
A corrupt queued/active row parks the whole worker, logs one integrity diagnostic
and preserves raw rows/keys/staging/outputs. It neither skips, deletes, repairs,
requeues nor executes those jobs. The process remains alive and accepts shutdown;
the operator must restore/inspect retained storage and explicitly restart.
`/health` remains API liveness only. Parked-worker readiness and lease-expired job
presentation are M3 liveness work, never a model probe in health.

The supervisor opens bundle.json relative to its nonsymlink attempt directory with
O_NOFOLLOW/O_NONBLOCK, verifies fstat reports a regular file and a bounded size,
then reads at most 16 MiB in 64 KiB chunks. FIFOs, devices, directories, symlinks
and oversized files fail INVALID_OUTPUT before decoding. Shutdown/deadline checks
run between chunks, before/after decoding and between publication dependencies.
A cancelled claimed job is observed before launch; confirmed absence of a launched
process permits cancelled rather than a supervision failure. Cancellation racing
a launch still wins final ownership checks and causes confirmed process reaping.

The deadline starts at claim, includes launch/read/validation/publication, and is
checked against both monotonic elapsed time and recorded claim wall time. Before
publication, the worker renews the lease through the remaining execution budget
plus the normal lease interval. This bounded reservation prevents recovery from
fencing a publishing owner during a slow fsync/registration without weakening
final version/lease/cancellation checks. A crash during this phase can therefore
delay WORKER_LOST until that reservation expires. Shutdown/timeout are checked
again at publication boundaries and before the final commit. A kernel filesystem
call itself cannot be preempted by Python; trusted local working storage remains
a topology requirement. Process groups cannot contain deliberately detached
sessions; stronger Linux containment is a prerequisite for untrusted/real runtimes.

Current limits are explicit test-profile bounds: 16 MiB serialized bundle, 16 MiB
supervisor file bound, 8 MiB per retained artifact and 16 MiB child RLIMIT_FSIZE.
Base64 expansion reduces usable raw bundle capacity below 16 MiB. RLIMIT_CPU sums
thread CPU time and is an additional bound, not the wall deadline. Real multi-sample
structures/PAE/runtime bounds and containment must be redesigned/measured at M4/M5.

### Immutable reads and consistent snapshots

Committed registration graphs and archive nodes are immutable. Successful reads
verify every dependency/hash/size and M1 invariant without taking the exclusive
publication lock. No publisher can replace their nodes. Writer lock acquisition
is nonblocking and reports retryable PREDICTION_BUSY rather than waiting forever.
Status returns job, attempt and operational failure from one explicit SQLite read
transaction. A concurrent heartbeat/finish cannot combine an old running job with
a new timeout. Cancellation of an HTTP awaiter still holds executor capacity until
the actual bounded read finishes; it then becomes reusable by biological routes.

### Configuration and mutation outcomes

Malformed or absent NEUROFOLD_CODE_IDENTITY blocks submission with 503
CODE_IDENTITY_REQUIRED; malformed identity never becomes client 422. Submission-only
configuration is ignored by retained reads and cancellation. A symlinked archive
root returns 503 CONFIGURATION_ERROR. In the reviewed default composition,
symlinks at predictions/ and predictions/registered returned 500 ARCHIVE_INTEGRITY
and 500 INTERNAL_ERROR respectively. Other sub-folder symlinks were not
exhaustively checked; uniform translation for these unsupported paths remains open. Deterministic rejection carries no publication
uncertainty.

Queue capacity returns 429 PREDICTION_QUEUE_FULL; SQLite/advisory-lock contention
returns 503 PREDICTION_BUSY. Both are retryable and include Retry-After: 1. Invalid
keys are 422; idempotency/lifecycle conflicts are 409. Unavailable profile/code
configuration is 503, nonretryable until the operator changes availability/config.
A database commit I/O error whose result cannot be established returns 503
PREDICTION_MUTATION_UNCERTAIN, non-automatic retry, with recovery by known job ID
or deliberate replay of the same submission key. Await timeout remains 504 with
uncertain mutation outcome; disconnect does not assert rollback. Do not infer a
new job exists from a deterministic rejection.

### Owned output identities

Local filenames are not global archive identities. Before registration the service
checks original result/manifest/sample linkage and assigns IDs using SHA-256 of
canonical JSON `["neurofold-output/1", job_id, attempt_id, kind, local_id]`, prefixed
`output-`. Kinds are artifact, sample, mapping, manifest and result. Every result
raw artifact is output-owned. Adapters must give distinct logical local IDs to
different bytes (e.g. `sample-1:model_0.cif`, `sample-2:model_0.cif`); identical
filenames in different sample directories do not authorize duplicate bundle IDs.
Samples may intentionally share one artifact when its bytes are identical.

Source receipts, references/variants, locks, weights and resolved input identities
stay retained. Structure/raw/sequence hash domains remain unchanged. Mapping and
confidence references are rebound and their canonical hashes recomputed together;
original raw bytes never change. Only new proposals are scoped; old successful
archives/IDs remain readable unchanged. Publication still verifies full M1 input,
profile evidence, provenance and graph integrity after scoping.

### Truthful retained operational failures

Frozen M1 job/1 contains a validation-oriented failure enum and cannot represent
all operational causes. Its legacy ILLEGAL_PREDICTION_TRANSITION/lifecycle/false
field remains a compatibility placeholder; it is not an operational cause or
execution-retry policy. New failures atomically retain a separate immutable,
checksummed `neurofold-prediction-failure/1` record bound to the exact terminal job
hash, attempt and end time. It records TIMEOUT, WORKER_LOST, CHILD_FAILED,
INVALID_OUTPUT, PUBLICATION_FAILED, SHUTDOWN or SUPERVISION_FAILED and the explicit
policy `explicit-new-job-same-spec`. There are no automatic execution retries.

`GET /v1/prediction-jobs/{id}/failure` returns this record (200); absent job is 404,
nonfailed/historical failure without an extension is 409. Its
[schema](schemas/neurofold-prediction-failure-1.schema.json) is generated alongside
the unchanged status/child schemas. Status/1 remains unchanged and verifies the
sidecar label against the checksummed extension. Missing/tampered new extensions
are integrity failures. Legacy failures are inventoried at schema migration and
never retroactively rewritten or promoted to newly verified failure evidence.
Any future export of an operational failure must include both job/1 and its
failure extension, or explicitly label a legacy extension unavailable; exporting
the M1 placeholder alone as a cause is prohibited. No export implementation is
added here. Successful and historical scientific contract bytes remain frozen.

Known I/O failures during composition, retained input reads and availability checks
precede job mutation and return deterministic PREDICTION_UNAVAILABLE without a
publication-uncertainty hint. Commit I/O and await timeouts retain their distinct
uncertain outcomes. Semantic child ownership/linkage/evidence/M1 validation failures
are INVALID_OUTPUT, even when discovered during registration; actual immutable
publication I/O remains PUBLICATION_FAILED. Cause classification does not depend
only on the step reached.

Schema-2 migration is forward-only for the shipped code: the older schema-1-only
M2 binary rejects it. Rollback requires a coherent pre-migration backup; editing
user_version or dropping extension tables is not a supported recovery operation.

### Second-review hardening and M3 entry conditions

The [second-pass checkpoint](testing/nf04-m2-hardening-pass2-evidence.md) records
O1/W1/W2 and the failure-route/test corrections. Output scoping remaps mapping
hashes in artifact lineage parents in both manifest and staged descriptors, then
restores canonical parent ordering. Retained input/source hashes and raw bytes
stay unchanged. After successful bundle decoding, lease reservation and stage
write failures are SUPERVISION_FAILED; decoding failures remain INVALID_OUTPUT.
The controlled test launcher's readiness handshake is bounded by startup and job
budgets, observes child exit/shutdown, and reaps on startup failure. This is a test
harness correction, not a production readiness mechanism or an M4/M5 resource-limit
claim.

M3 remains gated on independent acceptance of M2 and a recorded green hosted CI
checkpoint. Before expanding fake execution or its frontend workflow, M3 must include:

- Explicit worker readiness and a restart policy, including parked/corrupt storage
  and unavailable storage behavior. Preserve exit 65 for startup/runtime integrity
  damage and exit 78 for uncertain cleanup/inaccessible marker checks; both require
  operator recovery before restart. Normal requested shutdown exits 0. API health
  remains independent of model IO.
- A documented upgrade order and an operation-time schema-version guard. Stop all
  schema-1 workers before upgrading storage, migrate with schema-2 code, then
  restart only compatible API/workers. An already running old worker can otherwise
  write a failed job without its required new failure extension. Rollback still
  requires a coherent pre-migration backup. The guard is deferred; this checkpoint
  does not claim rolling mixed-version safety.
- Bounded contention retries for terminal `finish()` writes so confirmed cleanup
  is retained when a writer briefly holds SQLite. Current recovery remains the
  fallback if that terminal write fails; no execution retry is implied.
- M6 frontend mutation recovery: preserve an explicit uncertain outcome and reuse
  the same identity/key before offering another mutation after abort/timeout.
- An explicit naming rule for dependencies staged by the child, distinguishing
  retained dependencies from job-owned outputs without implicit ID collisions.

H1/reference ambiguity remains a separate prerequisite before NF-05/06 or
scientific interpretation. M4/M5 runtime limits, deployment and scientific review
continue to require their existing gates. No M3 implementation is included here.


### Focused cleanup closure and M3 preservation

The [closure checkpoint](testing/nf04-m2-cleanup-closure-evidence.md) records the
five conditions of the user's conditional approval. The bounded unconfirmed-
cleanup outcome retry is implemented here; general terminal/publication write
retries remain M3 work. M3 must preserve the durable manual block, safe launch
ownership transfer and distinct exit-65/exit-78 recovery handling while adding its
readiness/restart, schema compatibility, M6 mutation recovery, dependency naming and harness
conditions (including W6 and H-01). The local origin ref now records the push of
fd2c8d5; its first recorded hosted checkpoint is
[CI 43169838959](https://github.com/grusic91/neurofold/actions/runs/43169838959),
with a green conclusion. This uncommitted follow-up is not covered by that run.
Changes to CI in this post-closure follow-up take effect only after a
separately authorized new push; none is performed here. H1 mapping correction and biological-foundation review are
required before scientific interpretation and NF-05/NF-06 acceptance.


### Shutdown budget and recovery reference data (2026-11-12)

Let G be child termination grace and R=max(0.5 s,G). A conservative scheduled-call
cleanup allowance is G+R+3*(0.5 s+0.1 s), or 5.8 s for G=2 s. A post-spawn launch
failure can require both launcher cleanup and supervisor cleanup: reserve twice
that allowance (11.6 s). Then reserve the retry-scheduling budget min(2 s,lease/4),
up to 0.2 s backoff and a conservative 2 s for the final SQLite read/write pair:
about **15.8 s** before filesystem/OS scheduling margin at defaults. Review measured
6.7 s on one cleanup-failure path; that measurement is not the maximum contract.
Both worker compositions now allow **20 s** before Docker force-kill. At M4, and
whenever grace/lease/storage configuration changes, recompute this envelope,
measure teardown under the intended memory/IO workload, and set stop_grace_period
at least to the resulting allowance plus margin. Kernel IO and descheduling are
not hard real-time bounded by Python; increase margin where measurements require.

New block records add UTC created_at, host_id (the owning host/container hostname;
null if lookup fails without interrupting the marker/outcome record),
and child_launched_at, the worker's timestamp immediately before the launch call,
not an asserted kernel process birth time. Null launch time means no launch-call
reference was available. worker_id is also in the critical log. These private
reference fields support investigation, not automatic PID signalling; presence
still blocks regardless of record contents or parseability.
