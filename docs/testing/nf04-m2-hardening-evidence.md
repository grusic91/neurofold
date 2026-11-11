# NF-04 M2 independent-review hardening checkpoint

Date: 2026-11-11. Historical first-pass implementing-agent software evidence.
Independent re-review found O1/W1/W2 and test gaps; see the
[second-pass checkpoint](nf04-m2-hardening-pass2-evidence.md) for corrections. No scientific approval or general platform compatibility is claimed.
All changes remain uncommitted. No push, publication, deployment or PR was made.
No executable adapter, frontend prediction polling, Boltz-2, GPU runtime, export
or alignment-policy change is included.

## Baseline and retained evidence

The checkout started clean on `main` at
`823a33007f1d0a2453038a8513d9badb0333bb52`, two commits ahead of the local
`origin/main` ref. Staged and unstaged diffs were empty. Relevant history:
`ca74e9e` M1 contracts, `823a330` M2 orchestration; prior NF-03 M1–M3 were inspected.
No unrelated work was present or overwritten. LICENSE and attribution are unchanged.

The supplied independent review, LEDGER, main probes and useful agents2 reports/
probes were copied into ignored `backend/outputs/nf04-m2-hardening/review/`.
`SHA256SUMS.json` inventories 2,324 retained files. A further
`review-reproductions.tar.gz` preserves 8,835 raw reproduction files, including
work/data artifacts, with a per-file SHA-256 inventory. Replaceable environments,
caches, duplicate exported checkouts and model/weight directories were excluded. These are review evidence, not
trusted executable instructions. Temporary reviewer exports/caches were not used
as application dependencies. Raw diagnostics, local environments, baseline/source
snapshots and acceptance logs remain ignored outside Git. No real provider payload
was added to source control; live-provider probes were unnecessary and not run.

Fresh baseline probes in an isolated `git archive HEAD` reproduction showed:

- H2: after truncation to zero bytes, reopening silently created new history;
  replaying the old key returned a different job ID.
- H3: exact `mypy src tests` failed on missing `prediction_m2_schema` import.
- M1: holding a SQLite writer transaction caused worker.run to exit with
  PREDICTION_BUSY; release did not revive it.

See ignored `baseline-probes.log`, `baseline-mypy.log` and the preserved review
inventory for original reproductions. Other findings were checked against source
and exercised by focused regressions; sensitivity experiments below verify that
removing the relevant guards is observable.

## Finding disposition

| Finding | Disposition and current evidence |
| --- | --- |
| H2 retained database integrity | Reproduced and fixed. Only an absent unmarked DB initializes; established missing/empty/truncated/version/schema/trigger/index/marker damage fails closed. Read/write opening cannot recreate missing retained history. Eight simultaneous initializers and two real processes exercise legitimate first creation. Version-1 migration preserves every job byte. |
| H3 required checks | Reproduced and fixed. Schema scripts use an explicit scripts package; pytest declares its project import root. Both exact narrow mypy and the broader meaningful source/tests/scripts/infra scope pass. AGENTS is authoritative; README, NF-09 guidance, testing guide and CI use the same broad checklist. No dependency changes or lockfile updates were needed. |
| M1 worker resilience | Reproduced and fixed for SQLite contention and corrupt job rows. Real held-lock tests reach the retry/backoff path, recover after release and stop while still contended. Queued/active corruption parks the worker with one diagnostic, preserves raw bytes and blocks all execution until operator recovery/restart. No deletion/repair/requeue or crash/restart loop. |
| M2 archive-read contention | Confirmed and fixed. Immutable successful graphs verify without the publication lock. Held-lock status reads complete, cancelled awaiters release capacity after real completion, and biological retained routes continue using the shared executor. Writer admission is nonblocking/retryable. |
| M3 mixed status/read snapshots | Confirmed and fixed. Job, attempt and reason come from one read transaction. Trace barriers pause between job/attempt or job/reason reads while another connection commits a heartbeat/timeout; the response remains the old consistent snapshot. |
| M4 server configuration | Confirmed and fixed. Malformed code identity is submission-only 503 CODE_IDENTITY_REQUIRED; retained reads/cancel remain usable. A symlinked archive root gives 503 CONFIGURATION_ERROR on biological and prediction routes. Round 3 corrects this earlier broad claim: symlinked prediction sub-folders can return differing 500 responses; their error translation remains open. Client representation errors remain 422. |
| M5 error/retry semantics | Confirmed and fixed. Queue-full is 429; SQLite/advisory contention is retryable 503; both have Retry-After: 1. Pre-write rejection has no false uncertainty. Known composition/input/availability I/O failures are also deterministic and create no job. A fault injected after a real commit produces explicit uncertain-mutation 503, and deliberate same-key replay converges. Await timeouts retain uncertainty. |
| M6 frontend mutation abort UX | Deferred to M3 before expanding the workflow/polling UI. Existing pin/import aborts can leave orphan retained records; no new frontend feature is included here. The 95-second workflow versus five-second health budget is corrected in current docs. |
| M7 output ownership | Confirmed and fixed for new service publication. Job/attempt/kind/local-ID namespace is assigned before registration; multiple jobs reusing structure-1/confidence-1, multiple samples sharing identical bytes and an actual variant job publish/reopen without collisions. Different bytes require distinct logical sample-local IDs even if filenames repeat. Existing successful archives/IDs remain unchanged. |
| M8 truthful failures | Confirmed and fixed through the documented compatible extension. New operational causes are immutable/checksummed and bound to the terminal job hash/attempt/time; explicit same-spec new-job retries are declared. Semantic ownership/evidence rejection is INVALID_OUTPUT, distinct from publication I/O. Frozen M1 failure fields are legacy placeholders, not operational causes/retry policy. Historical failures are inventoried, never rewritten or invented. |
| M9 weak regressions/schema healing | Confirmed and addressed for the requested safety guarantees. Useful independent mutation probes were ported with no hardcoded reviewer paths. Live recovery, cancelling capacity, retry-parent conflict, profile evidence, variant graph and supervisor guards now have sensitive regressions. Schema comparisons generate in memory; deliberate drift fails twice without changing the drifted file. |
| M10 stale documentation | Confirmed and updated across README, epic, architecture, integration, test matrix and tasks. Original M1/M2 evidence is explicitly historical; this is the separate checkpoint. No implementing-agent test result is relabeled independent approval. |
| FIFO/device/directory/symlink/oversized output | Confirmed and fixed. Nonblocking/nofollow descriptor opening, fstat regular-file/size checks and bounded chunks reject these before reads/decoding; tests assert neither read nor decoder runs. No privileged device creation is required: a real /dev/zero descriptor exercises the device check. |
| Cancellation between claim/launch | Confirmed and fixed. A synchronized cancellation after staging prevents launch and finishes cancelled with confirmed absence of execution. Running cancellation still requires reaping. |
| Deadline/shutdown/publication ownership | Confirmed and fixed within the trusted local-storage topology. Deadlines include preparation/read/publication; cooperative checkpoints classify TIMEOUT/SHUTDOWN accurately. Publication reserves a bounded live lease, retains orphan evidence on interruption and preserves final version/lease/cancellation fencing. A clock-controlled slow-registration test proves recovery does not fence the owner. |
| Prediction artifact transport | Additional low finding fixed: binary OpenAPI response, attachment/nosniff/private-cache headers, raw checksum and ETag are checked against returned bytes. |
| Historical variant container gap | Closed only by the newly executed variant POST/GET, publication/linkage and post-recreation retained-read acceptance recorded below. Historical evidence remains historical. |
| H1 biological mapping and reference ambiguity | Deferred as a separate required correction before any scientific use of mappings/NF-05/06 interpretation. Tagged/truncated constructs and reference X/B/Z/J handling remain unresolved. Alignment policy was deliberately unchanged. |

## Compatibility and operational decisions

The detailed decision record is [prediction-orchestration.md](../prediction-orchestration.md#independent-review-hardening-decisions-2026-11-11).

- Database schema 2 validates schema 1 before adding failures/legacy-failures and
  immutable failure triggers transactionally. Jobs, attempts, keys, registrations,
  publications and successful scientific bytes are not rewritten. Unknown or
  structurally incomplete databases fail closed; restoration is an operator task.
- Older schema-1-only binaries reject schema 2. Rollback requires a coherent
  pre-migration backup, never an edited user_version or deleted extensions.
- The M1 job/result/manifest/provenance schemas, canonical identity bytes and hash
  domains stay frozen. Status/1 and child-proposal/1 remain byte-identical.
  New failure/1 is a separate checksummed record available at
  `GET /v1/prediction-jobs/{id}/failure`; future exports must include it or explicitly
  label a historical extension unavailable. Exporting the M1 placeholder as a
  truthful operational cause is prohibited. No exporter is implemented.
- New output proposals are assigned output- IDs from the canonical versioned
  job/attempt/kind/local-ID tuple. Raw hashes and bytes remain unchanged; mapping,
  confidence and manifest references are resealed together. Source/variant/input
  identities stay retained; existing successes are never renamed.
- Publication lease reservation can delay WORKER_LOST after a publishing worker
  crash until the bounded remaining execution budget plus lease expires. This is
  intentional ownership protection, not an automatic rerun. Shutdown/deadline
  checks occur between bounded operations; Python cannot interrupt a kernel fsync.
- API health/static capabilities/startup remain independent of storage, models,
  providers and GPUs. A parked worker remains alive but is not ready; M3 must add
  explicit worker liveness/readiness and expose expired leases without moving
  runtime initialization into health.

## Regression sensitivity

The ignored `mutation-results.json` records 15 targeted guard-removal experiments,
all detected by the named regressions: empty-file reinitialization, busy-worker
exit, both snapshot guarantees, live-owner recovery, cancelling capacity,
retry-parent comparison, profile evidence, variant registration, output ownership,
symlink/type/size guards, failure cause and publication lease reservation.
`additional-sensitivity.json` records detection of reintroduced archive-read
locking the HTTP-level job/failure snapshot guard, and two consecutive schema-drift
failures without healing the source file.
These experiments run in isolated source copies; they do not modify this checkout.
No mutation percentage is an acceptance target.

## Executed checks and platform scope

Initial Linux acceptance completed the HTTP/process phases but exposed a real
regression in the eight-submitter test: shortening SQLite's baseline busy timeout
from one second to 100 ms caused avoidable admission failure under emulation.
The diagnostic isolated BEGIN IMMEDIATE contention. The baseline one-second
bounded wait was restored; worker exponential retry and interruptible backoff
remain separate. Partial/failing logs are preserved, not counted as acceptance.

Broader cold Linux runs also exposed test-harness timing limits under emulation:
the two import/network-independence subprocess probes used ten seconds, and the
new lock-contention read test allowed one second for actual graph verification.
These are not application latency contracts. Their test-only waits were increased
to 30 seconds and ten seconds respectively, preserving every import/network/hash/
status assertion and the held-lock condition. Application deadlines are unchanged;
removing the read/snapshot guards is still detected. Failed initial logs remain
retained and are not counted as acceptance.

The initial broad Linux runs each had 1,989 passes and five failures: the two
cold-start probes, the one-second archive-read test and two existing variant
waiter tests. Those variant tests mixed a deliberately short mutation timeout
with successful recovery reads, and allowed the same timeout to win a cancellation
race. They now retain the 100 ms held-mutation timeout, restore a generous budget
for later real HTTP reads, and give explicit cancellation its own pending request.
Events still control the publication boundary; 429 admission, 504 uncertainty,
actual late completion/failure, cancellation, result verification and drain/log
assertions remain. Controlled Linux acceptance stops Vite only after real proxy/
page checks, avoiding unrelated load during process supervision. The output-ID
regression additionally publishes different bytes under the same local name and
verifies retained bytes after reopening.

Final executed results (all logs below are in the ignored checkpoint directory):

| Check / platform | Result and evidence |
| --- | --- |
| macOS 27.0.1 ARM64, CPython 3.12.16, SQLite 3.53.1 | Exact original narrow Ruff/format/mypy commands and authoritative broad Ruff/format/mypy scope pass; 85 narrow / 95 broad files. Full pytest: **2,001 passed**, **95.25% coverage**, 90.14 s. `verified-python312.log`. |
| Same host, CPython 3.13.2, SQLite 3.50.4 | Locked isolated environment; Ruff/format and both mypy scopes pass. Full pytest with ResourceWarning treated as error: **2,001 passed**, **95.25% coverage**, 88.14 s. `verified-python313.log`. Default backend environment remains 3.12. |
| Node 24.5.0 / npm 11.5.1, native macOS | npm ci, lint, typecheck, build, component tests, pinned browser installation, mocked Chromium/no-WebGL tests and actual browser -> Vite -> synthetic API integration pass: **36 component + 12 browser + 1 integration**. `frontend-final.log`. No frontend/package-lock dependency changes. |
| Initial broad Linux matrices, CPython 3.12.16 / 3.13.18 | Each executed the full then-current 1,994 tests: **1,989 passed / 5 failed**, as described above. Linux 3.12 took 1,892.02 s; 3.13 took 1,645.00 s. Broad Ruff/format/mypy passed. These failing runs are preserved in `linux-python312.log` / `linux-python313.log`, not relabeled passing. |
| Corrected Linux cases, both Python versions | Final Ruff/format and narrow/broad mypy pass. Corrected full affected-test selection: **58 passed** on each version (`linux-final312.log`, `linux-final313.log`). After final I/O/semantic-cause additions, Linux 3.12 hardening + prediction HTTP: **70 passed** (`linux-verified312.log`); Linux 3.13 complete affected selection: **64 passed**, ResourceWarning as error (`linux-verified313.log`). The five original failing cases are included and pass. |
| Linux process/storage/HTTP acceptance | Complete isolated normal startup/page/proxy and controlled-worker lifecycle run passed: durable API recreation/same-key reopening, actual variant POST/GET/publication/reference linkage and reopening, cancellation, timeout/forced kill, graceful shutdown, SIGKILL worker loss/restart, then **128 passed** process/storage/HTTP regressions in 297.06 s. `container-acceptance-isolated.log`. Final added adverse-path regressions are separately verified above. |
| Normal worker entry point | Final normal worker.main composition/polling and real SIGTERM shutdown pass with a readiness-only instrumentation barrier, no executable profile/model. `standalone-worker-entrypoint.log`. |
| Infrastructure / source hygiene | Normal, offline and controlled Compose config --quiet pass. Normal API/frontend/worker and controlled images build. Original LICENSE and frozen M1/M2 schema/fixture bytes remain unchanged; current authored source inventory updated. git diff --check passes. |

The authoritative backend commands were run from backend/ after uv sync --locked:

```sh
uv run --locked ruff check . ../infra/testing
uv run --locked ruff format --check . ../infra/testing
uv run --locked mypy src tests scripts ../infra/testing
uv run --locked pytest
```

The former exact `ruff check .`, `ruff format --check .`, `mypy src tests` also
pass; no scope reduction substitutes for the broad checks. Python 3.13 uses the
same commands with --python 3.13 and an ignored separate project environment;
its final full run adds `-W error::ResourceWarning`. Initial 3.13 resource warnings
identified an unclosed in-memory schema-validation connection; closing it explicitly
removed those warnings. No warning suppression was added.

The frontend sequence was npm ci; npm run lint; npm run typecheck; npm run build;
npm run test; npm run test:browser:install; npm run test:browser; npm run
test:integration. Actual integration used loopback synthetic HTTP and denied
unmatched external traffic. No live provider probes were performed.

Linux application containers were non-root UID 999, CPython 3.12.16, SQLite 3.46.1,
Linux 6.8.0-100-generic x86_64/glibc 2.41. Disposable broader-check images used
non-root UID 1000, the same kernel, glibc 2.36, managed Python 3.12.16/3.13.18
(the recorded 3.13 SQLite is 3.53.1). Frontend container Node was 24.22.2. This is
**emulated Linux AMD64 on an ARM64 Mac**, not a native AMD64 or fresh Linux ARM64
claim. Exact image IDs are retained in container-image-identities.json and
linux-image-identity.log. Base tags are not presented as immutable runtime design.

The isolated project was neurofold-nf04-hardening with loopback ports 28000/25173.
It did not reuse preexisting named volumes or stacks. Its archive is retained
as neurofold-nf04-hardening_biological-archive; cleanup uses down without --volumes.
The controlled test image emits one pytest-cache permission warning because its
application directory is read-only; persistent archive writes and all tests pass.
This is a replaceable test cache, not retained job storage.

Remaining verification limits: the full Linux suite was not rerun as one clean
combined invocation after test-harness corrections and the last adverse-path fixes;
all originally failing/current affected cases were rerun and pass, with final full
native suites above. No remote GitHub Actions run was triggered, no fresh Linux
ARM64/native AMD64 or NVIDIA acceptance was available, and no power-loss/real
ENOSPC/scientific-validation claim is made. These limits must remain visible in
independent re-review.

## Deferred findings and explicit triggers

| Finding/limit | Reason and required trigger |
| --- | --- |
| H1 and reference ambiguity | Separate biological correction/review before scientific use of maps, NF-05/06 interpretation or real prediction/comparison acceptance. Existing synthetic fixtures do not establish correctness. |
| M6 and frontend mislabeled DTO acceptance | M3 workflow/polling work must expose uncertain mutations and harden representation labels; no frontend interaction expansion here. |
| Worker availability/parked state/expired lease UI | M3 before enabling the synthetic executable adapter. Health remains liveness-only. |
| Code/profile identity changes cause old-key/retry conflicts | Frozen spec includes code and profile. Operators must restore the exact declaration for same-spec retries; changed scientific inputs need a deliberate new unlinked job. Revisit the replay UX during M3, never silently rewrite old specs. |
| Worker does not attest running code identity | M4/M5 before any real runtime/profile is enabled; declared provenance alone is not measured runtime truth. |
| Detached child sessions and CPU/output limits | Trusted authored children only at this checkpoint. Stronger Linux containment, thread CPU semantics and a non-base64 real-output protocol with measured sample/PAE bounds are M4/M5 prerequisites. No general hostile-process containment claim. |
| Metadata bool/int equality; case-sensitive upstream gzip | Separate contract/provider corrections before broader source acceptance or export; provider behavior was unchanged and no new live probe is claimed. |
| Architecture-test breadth | Existing boundary/import tests plus code inspection preserve API -> core <- adapters. Broader automatic application/adapter import rules are required when adding runtimes at M3/M4. |
| Dependency provenance/manual review | Independent human review of httpx2/httpcore2 identity remains a release gate; lockfile/install success does not resolve it. |
| Historical evidence absolute paths | Preserved as historical evidence; avoid new account-specific paths in committed evidence. Audit/redaction policy before public evidence release. No history rewrite authorized. |
| Real ENOSPC/power loss/storage semantics | Generic injected I/O, abrupt process death and no-clobber/fsync ordering are tested. Actual disk-full/power-loss acceptance and backup/retention/GC policy remain deployment gates. |
| Multi-user/remote/production hosting | Security/trust design, production /api routing, remote dispatch, immutable runtime images and operator retention/backup plan required before deployment. |
| Scientific acceptance | Domain reviewer/run operator remain unassigned. Models, weights/licenses, MSA disclosure, named Linux/NVIDIA limits and independent biological/real-prediction/export reviews remain separate required gates. |

## Tested state and recommendation

The final runtime/schema/configuration inventory matches the final Linux source
input byte-for-byte. All tracked and untracked source files are inventoried; a
Git diff alone would omit the new modules/tests/schema. The checkpoint document
itself is excluded from the aggregate below to avoid a self-referential hash.

- Base HEAD: `823a33007f1d0a2453038a8513d9badb0333bb52` (unchanged).
- Runtime/schema/config SHA-256: `3b851e96a5f5923343e134068c4390133c92f091823e4f6000b6d63f32630d15`.
- Working source tree SHA-256, excluding this checkpoint: `d6ea39e4a88fd16c6a5b5b24ec3c4620b65d1d109e5a9f65a80ed9516439d90c`.
- Tracked binary diff SHA-256, excluding this checkpoint: `e883dde1c7ffef9e8dc40f95bf66cb2fab5ddd7204edd15604db193652877672`.

Ignored state-identity.json contains the exact path/hash inventories, including
untracked files; changes.patch contains the tracked diff. source-snapshot.tar
preserves the final complete reviewable source, including this checkpoint.
artifact-inventory.json hashes retained evidence (excluding itself and replaceable
environments/type caches). Review reproduction archives have their own per-file
inventories. These are software acceptance identities, not runtime attestation for
a real prediction.

**Recommendation: ready for independent M2 re-review. Do not start NF-04 M3 on an
assumption of approval.** Re-review must accept the compatibility decisions,
regression evidence and explicitly bounded Linux rerun coverage; obtain a clean
full Linux/CI run of the reviewed final tree before treating that platform gate as
complete. No remote CI result is inferred. M3 must then implement real worker
liveness/readiness, the M6 mutation-recovery UX and explicit synthetic-adapter
registration before enabling its vertical slice. H1 remains separately blocking
scientific use of mappings. This checkpoint supplies neither independent
scientific approval nor general platform compatibility.

The isolated acceptance containers/network were removed, their named archive
retained, and the preexisting Docker daemon left in its original running state.
All repository changes remain unstaged/uncommitted for review.
