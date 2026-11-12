# NF-04 M2 post-closure checkpoint — 2026-11-12

Implementing-agent evidence for the round-6 low findings on `fd2c8d5`, followed by
the round-7 repairs recorded below. The round-6 results/identities are historical
and are not relabeled as tests of the round-7 tree. This task
makes no commit, push, PR, publication, deployment, M3 feature or scientific
approval claim. H1 and biological-foundation review remain separate prerequisites
before interpreting mappings or accepting NF-05/NF-06.

## Starting state and process record

Initial local `main` and `origin/main` both resolve to
`fd2c8d51b7911265f31a77440f6a1ed7f5f94fb5`, with a clean worktree. The origin reflog
records `update by push` at **2026-11-12 07:40:56 +0100**. The older retained
`committed-checkpoint.json` with push_performed=false predates that push and is
preserved. The earlier request to push three local commits is moot.

**Push attribution (verbatim): “Me”.** This is the user's answer to who performed
or authorized the 07:40:56 push, not an inference from the reflog. The user also
answered **“Authorize read-only GitHub lookup for fd2c8d5”** and **“Authorize
registry access for locked installs/checks”**. Before those answers, all checks
used local caches and GitHub was not contacted. Authorized read-only lookup then
verified a successful hosted run for fd2c8d5, recorded below. No hosted rerun or
new push is authorized or performed. The first recorded hosted checkpoint is
green for the starting commit; it does not validate this uncommitted follow-up.
CI changes here take effect only after a separately authorized new push.

The supplied review reports no medium-or-higher findings on fd2c8d5 and reports
2,072 native passes per Python version, 2,052 Linux passes plus 20 Darwin skips,
and complete container acceptance. Those are review results on the starting
commit; they are not relabeled as current-tree results or independent acceptance
of this follow-up. Historical evidence remains intact, with a dated correction
note added to the cleanup-closure checkpoint.

Raw commands/logs, the request, starting source hashes/reflog, reproductions,
mutants and final identity are retained in ignored
`backend/outputs/nf04-m2-post-closure/`. No research inputs, weights or datasets
are used.

## Findings, reproductions and dispositions

| Item | Disposition, tests and sensitivity |
| --- | --- |
| L1 exit contract | Fixed: 0 normal requested stop; 78 only UNCONFIRMED_CLEANUP; 65 ARCHIVE_INTEGRITY at startup or after a runtime park. Both entrypoints catch startup integrity errors and log a safe critical line without traceback; other crashes retain Python behavior. Eight subprocess cases cover both entrypoints. Four integrity cases fail on fd2c8d5 and pass after the fix. |
| L2 inaccessible marker | Fixed with lstat; only FileNotFoundError means absent. Injected EACCES/ENOTDIR block before recover/claim with errno names, no exception text, exit 78. Both fail on fd2c8d5 and pass after the fix. |
| L3 portable signal-retry tests | Eight fake-clock cases exercise reap and terminate: short denials, disappearance just before 100 ms, persistent refusal and disappearance just after it. They do not sleep. All eight fail on the named single-retry mutant and pass on the actual loop. The persistent cases also require the original error and pipe closure. |
| L4 cleanup contention | The first-BUSY hook now checks stop and releases the writer on the worker thread before retry resumes. Main-thread observer scheduling cannot decide the outcome. An event-controlled pre-edit reproduction deliberately delayed that observer until the old budget expired and failed the original assertion without CPU stress. |
| L4 hang guards | Controlled-entrypoint startup guard is 60 s; recording-exhaustion outer guard is 30 s. Inline comments identify both as emulation/scheduling hang guards; functional retry/execution limits are unchanged. |
| L4 publication early release | Cheap same repair applied: release the writer inside the renewal/stage BUSY hook for successful-retry cases. Failure/exhaustion cases keep their original sequencing. |
| L4 copy/succeeded | Still timing-sensitive through its real child profile/handshake budget; not widened. Listed in test-matrix with trigger **hosted CI flake**. Current repetition counts are below, not a claim of universal timing independence. |
| Info 1 cancel race | Fixed: bounded cleanup recording may retry JOB_CONFLICT, re-reading ownership/state each time. A finish wrapper cancels before the first real finish; fd2c8d5 leaves cancelling, the fix retains failed/SUPERVISION_FAILED after a second ownership-checked attempt. Foreign/terminal attempts are not adopted. |
| Info 2 EPERM bound | Keep 100 ms, pinned by L3. Defer re-measurement to **M4's first child that spawns helpers on macOS**. The review's 510 stressed runs / 73 ms maximum are historical reviewer measurements, not a new performance guarantee. |
| Info 3 untested paths | Added dangling-marker, failed-write/in-memory block, recovered launch-transfer cleanup and foreign-attempt tests. Named stat-following, removed-memory-guard, discarded-transfer and adopted-foreign-attempt mutants each fail their dedicated test; unmodified code passes. Bound sensitivity is L3. |
| Info 4 shutdown budget | Document the conservative double-cleanup plus recording allowance (~15.8 s at defaults before IO/scheduler margin). Set both stop grace periods to 20 s. Require recomputation/measurement plus margin at **M4 or any grace/lease/storage change**; no hard real-time guarantee for kernel IO. |
| Info 5 recording wording | Correct current design wording: min(2 s,lease/4) is a retry-scheduling budget, not hard elapsed time. Backoff/final SQLite busy waits can extend it; review measured 2.17 s. Append a correction to historical closure evidence. |
| Info 6 CI strictness | Add error::ResourceWarning pytest configuration and Python -VV / SQLite version output to CI. Dependency declarations and lockfiles are unchanged. Full native suites run with the warning rule. CI changes remain unpublished until authorized. |
| Info 7 old mypy omissions | Dated note identifies both retained early logs and their invalid-base-alias failures; corrected final passes are not used to erase them. |
| Info 8 reference data | Add UTC created_at, host/container host_id and worker-recorded launch-call time to the private marker; worker_id joins the critical line. A deterministic test fails with missing fields on fd2c8d5 and passes afterward. The runbook explains host/time/command comparisons and missing-data handling. Marker contents never determine whether it blocks. |
| Additional full-Linux HTTP failure | Round-6 full failure and diagnostic logs are preserved below. **Fixed in round 7**, not deferred: bounded retries honor 503/PREDICTION_BUSY and Retry-After with the same key/body; final uniqueness, 202 and durable reopening assertions remain. Injected busy fails the old test and passes the repair. |
| Additional durable concurrency failure | **Fixed in round 7**, not deferred: bounded retries cover service construction/submission on PREDICTION_BUSY or raw SQLite busy/locked errors. Identical keys/specs, all eight results, reopening and conflict checks remain. Both injected busy forms fail before and pass after. |
| Additional full-Linux slow-publication failure | Round-6 full failure and diagnostic logs are preserved below. **Fixed in round 7**, not deferred: an already-finished child isolates publication/lease ownership from subprocess startup. Injected startup elapsed time fails the old test and passes the repair; removing lease reservation still fails the repaired test. Production timeouts remain unchanged. |

`baseline-regressions.log` records seven failures on unchanged fd2c8d5 (four L1,
two L2, one cancel race); the separate baseline reference-data log fails with the
missing created_at. `sensitivity-results.json` records the L3 and four informational
minimal mutants. The event-scheduling L4 reproduction and stress driver are
retained. Initial static checks caught non-exported os/time test patch targets and
long lines; corrected final checks are distinguished from those logs.

Linux-specific L3 sensitivity also passes: **8/8 cases reject the single-retry
mutant**, with the original source untouched. The disposable container uses the
same offline image/environment as the full run. See
`linux-signal-single-retry-mutant.log`, its command JSON and
`linux-signal-sensitivity-driver.log`. All eight pass unmutated in the full Linux
suite; these results do not depend on Darwin-only probes.

The pytest-only pyproject edit is the explicit Info-6 request. No dependency
manifest section, lockfile, public schema, scientific codec, alignment policy,
model registration or frontend source changes.

## Round-6 verification (before round-7 repairs)

- Full native Python 3.12.16: **2,096 passed**, **95.32%** coverage.
- Full native Python 3.13.2: **2,096 passed**, **95.35%** coverage.
- Native platform: macOS 27.0.1 (26A434), arm64; frontend Node 24.5.0 / npm 11.5.1.
- Locked offline installs, Ruff/format, broad strict mypy (100 files) and narrow
  strict mypy (90 files) pass on both; versions are retained in runtime logs.
  Native SQLite is **3.53.1** for Python 3.12 and **3.50.4** for Python 3.13.
- L4 saturation: **ten iterations of all five families / 100 parameterized
  executions pass**, using **11 busy loops for 11 reported CPUs**. No full suite,
  frontend check or container suite overlaps this explicit stress batch.
  Cleanup-contention passes **10/10 per each of six parameters**; controlled
  blocked startup, exhausted recording, early-release renewal and copy/succeeded
  each pass **10/10**. Per-node names and results are in the ten verbose logs.
- Idle-host emulated Linux L4 repetitions: **three batches / 30 parameterized
  executions pass**. Cleanup-contention passes **3/3 per each of six parameters**;
  controlled blocked startup, exhausted recording, early-release renewal and
  copy/succeeded each pass **3/3**. See `l4-linux-idle-01..03.log` and
  `linux-followup-results.json`. These run after the full suite, without stress.
- Frontend source is unchanged. Cached `npm ci --offline --ignore-scripts`, lint,
  typecheck, build, **36 unit / 12 browser / 1 integration** tests pass. Install
  hooks were disabled to honor the unapproved-network restriction. Verified cached
  Playwright markers allowed browser-install validation without downloads or cache
  GC. That initial pass does not claim a registry-enabled install.
  After registry authorization, normal **`npm ci`** also passes, followed by
  all required frontend commands again: **36 unit / 12 browser / 1 integration**
  passes, plus lint/typecheck/build and cached browser installation. These are
  separate `frontend-authorized-*.log` files and the driver log. Frontend source
  and its lockfile remain unchanged; the earlier offline run is preserved.
- Default, controlled-test and isolated offline Compose configurations pass
  `docker compose ... config --quiet`.
- Full emulated Linux Python 3.12.16 / SQLite 3.46.1: **2,075 passed, 20
  Darwin-only skipped, one failed**, **95.34%** coverage, 2,684.63 s. All 24 new
  post-closure cases pass, as do the process/worker/cleanup/re-review modules.
  The unchanged `test_concurrent_http_submissions_share_one_durable_job` fails
  its all-replies-202 assertion, with an OrchestrationError in the safe log.
  Its production API/service/storage paths are unchanged by this patch. The
  traceback does not identify the specific error code; no stronger cause is
  inferred. The full Linux suite is **not recorded as green**. Isolated diagnosis
  passes **3/3 without coverage**, retained in `http-linux-isolated-01..03.log`;
  this differs from the instrumented full suite, whose failure is preserved.
  No timeout or assertion is changed to conceal it. Revisit
  this test on the next full Linux/hosted checkpoint, especially on recurrence;
  its full-run failure cause remains unresolved. Separate L4 repetitions are
  recorded above.
- Initial Linux Python 3.13.18 locked offline install is **unavailable**: the existing
  checks image has the interpreter but lacks the mypy 1.20.2 wheel in its cache.
  `uv sync --offline --locked --python 3.13` fails without making a request,
  with pulling disabled and `--network=none`. No 3.13 Linux suite result is
  claimed from that attempt. The user subsequently authorized registry access;
  the authorized retry is recorded separately. See `linux313-offline-install.log`.
- Authorized Linux Python **3.13.18 / SQLite 3.53.1** locked install succeeds,
  followed by broad Ruff/format and strict mypy (**100 files**). The affected
  eight-module suite passes **209 / 20 Darwin-only skips** in **469.90 s**, with
  ResourceWarning treated as an error. It includes cleanup closure, post-closure,
  process, hardening, re-review, durable, worker and HTTP modules. This targeted
  run uses --no-cov; it is separate from the subsequent full Linux 3.13 suite.
  See `linux313_checks.sh` and `linux313-affected.log`.
- Full Linux **3.13.18 / SQLite 3.53.1**: **2,075 passed / 20 Darwin-only skips /
  one failed**, **95.35%** coverage, **2,617.14 s**. All 24 new post-closure
  cases pass. The unchanged slow-publication reservation test reaches registration
  but observes failed rather than succeeded afterward. Its specific outcome is
  not in the original traceback; focused covered diagnostics below reproduce a
  TIMEOUT failure. The full suite is **not recorded as green**. Source/static checks
  are the same locked 100-file checks as the affected run and pass again.

Full native suites and other timing-sensitive suites run sequentially, without
CPU stress.

### Additional HTTP diagnostic limitation

The unchanged concurrent HTTP test passes 3/3 in isolated no-coverage runs and
in the cached-image 158-test container acceptance. Under isolated coverage, a
safe observer installed **after test collection** captures PREDICTION_BUSY in
both failures: **one pass / two failures**. Its logs have no pre-import coverage
warning. This suggests SQLite contention under emulation/instrumentation is the
full-run failure mechanism; the original full log itself records only the error
class, so its missing code is not presented as measured fact.

`diagnostic_late_plugin.py`, `linux_http_covered.py`,
`http-linux-covered-late-01..03.log` and the command/results JSON retain the
observation. The selected-test coverage threshold is explicitly zero for this
diagnostic; no whole-project coverage or full-suite pass is claimed from it.
An earlier observer imported NeuroFold before coverage began: its two passes / one
PREDICTION_BUSY failure and module-not-measured warnings are preserved in
`http-linux-covered-*.log`, not treated as equivalent coverage evidence. The
corrected observer changes no checked-in application/test code or retry behavior.

The full Python 3.13 failure is
`test_publication_reserves_live_ownership_across_slow_registration`. Three isolated
covered repetitions in the same locked **3.13.18 / SQLite 3.53.1** environment
give **two passes / one failure**. The failing diagnostic records
**TIMEOUT, terminated=True**, with both recovery calls returning zero. This
supports real-child/profile deadline coupling as the explanation rather than
observed lease fencing in that repetition; the original full run lacks a retained
failure code, so that original cause remains an inference. The test is unchanged
and its lease assertion is not weakened. A future harness repair should isolate
elapsed time or the already-finished child, triggered by a hosted CI flake or
harness/profile change, as recorded in test-matrix.

`linux313_publication_probe.sh`, `repeat_publication.py`,
`diagnostic_publication_plugin.py` and `linux313-publication-probe.log` retain all
three outcomes. The safe observer is installed after collection and prints only
recovery counts and outcome enums/termination flags. The selected-test coverage
threshold is zero solely for diagnosis; no full coverage/pass claim follows.

### Isolated container acceptance

The checked-in `infra/testing/prediction_smoke.py` passes in its entirety,
including **158 in-container tests in 340.11 s**. Retained success/idempotency and
variant links survive backend recreation; proxy/health, non-root writes,
cancellation, graceful shutdown, timeout/forced termination, worker-loss restart,
storage races, stale-owner rejection and abrupt publication all pass. The one
warning is **PytestCacheWarning** for the image's unwritable cache path, not a
ResourceWarning. The new ResourceWarning rule is mounted into the test container.

Real production-container probes then return **78** for a partial synthetic
cleanup marker and **65** for a damaged synthetic predictions/jobs.identity.
Both contain the expected safe reason/code and no traceback. The damaged identity
belongs to the new production namespace in this disposable test volume; no user
archive is modified. `container-exits.json` and `container-exit-*.log` retain the
actual CLI return codes/diagnostics, not inferred success from container stopping.

Project **neurofold-r7-post**, ports **127.0.0.1:29004 / 26177**, uses existing
images with pull_policy=never and current source/test/pyproject overlays.
Backend and production uv.lock hashes and the frontend package-lock hash are
asserted equal to this checkout before acceptance. Runtime is Python 3.12.16 /
SQLite 3.46.1 and container frontend Node 24.22.2. Image identities:

| Role | Existing local image SHA-256 |
| --- | --- |
| Backend and controlled worker | cfb132e1d598755264569aaa4e6ed44d913d678ab20e0cd30efc2d6135bf6a10 |
| Production worker | 3c965d6ea099b5b064fcedaeeb30122d55ea1089bac439cd6cf96c7e2b92abd8 |
| Frontend | 9a02a2ce863c474e878d5985522df1090befb0d87157f007dd6062c7cafd7d26 |

The first setup attempt used an internal-only Docker network: services became
healthy, but Colima's published host ports refused the driver's connection before
acceptance began. Its logs/config/command are preserved with `internal-attempt`
names. The successful retry uses this project's normal bridge with loopback
published ports. All requests use local synthetic providers; no registry or
external service is contacted. This is source-overlay smoke/acceptance using
cached images, **not a fresh Dockerfile/image rebuild**. The user subsequently
authorized registry-backed locked installs/checks; fresh builds and the Linux
3.13 retry are recorded separately rather than relabeling this cached-image run.

`container_checks.py`, `compose.offline.yaml`, `container-command.json`,
`container-image-identities.log`, `container-acceptance.log` and
`container-services.log` retain the procedure and results. Its finally block stops
and removes only the isolated services/network and retains the synthetic evidence
volume. Existing stacks and Colima configuration are not changed.

After registry authorization, a fresh
`docker compose -p neurofold-r7-built -f compose.yaml -f compose.prediction-test.yaml --profile worker build backend frontend worker controlled-worker`
passes for all four images. A second isolated project,
**neurofold-r7-built-check**, ports **29005 / 26178**, repeats the complete
acceptance on those fresh images: **158 passed in 360.66 s**, with the same single
non-fatal cache-permission warning. Both real production exit probes pass again
(marker **78**, integrity **65**, no tracebacks). Backend/worker are Python
3.12.16 / SQLite 3.46.1; fresh frontend is Node **24.22.3**. All four role lock
hashes are asserted equal to this checkout. Its services/network are removed and
its synthetic volume retained separately. See `fresh-image-build.log` and the
`fresh/` command, override, image IDs, service logs, acceptance and exit artifacts.
This adds actual fresh-build evidence; it does not overwrite the earlier cached
run or failed internal-network setup.

### Commands and retained logs

Native checks use a locked offline sync for each selected Python runtime, then
the AGENTS.md Ruff, formatting, broad mypy and full pytest commands. The raw
checks and runtime output are `install312/313.log`, `runtime312/313.log`,
`ruff312/313.log`, `format312/313.log`, `mypy312/313.log` and `full312/313.log`.
Additional narrow mypy logs cover src/tests/infra separately. The stress,
reproduction and sensitivity drivers are retained as `stress_l4.py`,
`reproduce_l4.py` and `sensitivity.py`, beside their per-run logs and JSON results.

Frontend commands are `npm ci --offline --ignore-scripts`, then `npm run lint`,
`typecheck`, `build`, `test`, `test:browser`, and `test:integration`; cached browser
installation is validated with
`PLAYWRIGHT_SKIP_BROWSER_GC=1 npm run test:browser:install`. Each has a separate
`frontend-*.log` (installation is `npm-offline-install.log`).

Linux 3.12 uses the existing preinstalled locked test environment, not a fresh
registry install: image `neurofold-nf04-pass2-backend:latest`, ID
`sha256:cfb132e1d598755264569aaa4e6ed44d913d678ab20e0cd30efc2d6135bf6a10`.
Its uv.lock hash matches this checkout exactly. The captured source tar is
extracted into a disposable directory; current src is also mounted at the
installed editable path for subprocess imports. The container runs with
`--pull=never --network=none`, then `python -VV`, SQLite version, the AGENTS.md
Ruff/format/mypy/full pytest checks. Its scheduled three L4 repetitions did not
start because full pytest exited 1. `linux_followup.py` runs those separately on
an idle host, along with isolated HTTP diagnosis; raw logs and results are kept
separately. Full combined output is `linux312-full.log`; the captured exact
command/mount information is `linux312-command.log`.

### Round-6 tested change identity (historical)

Base commit is fd2c8d51b7911265f31a77440f6a1ed7f5f94fb5; changes remain uncommitted.
The **166-file code/configuration payload**, excluding Markdown prose, hashes to
`e57bac21336a081fad25137b9dee1417ba665fb5ef99fe459cd9f31f8ad83e78`.
Encoding is SHA-256 of compact UTF-8 sorted JSON mapping paths to raw-byte SHA-256
hashes. Every payload hash equals the captured source used for verification;
later evidence prose does not change that identity. `tested-code-config.json`,
`tested-change-identity.json` and `final-source-map.json` retain the maps and
checks. `identity.py` also verifies the dependency tables and 50 protected
core/frontend/license/lock files against the starting map. Source tar SHA-256 is
`963b4166574e9196fd320260c74beacec34ef10a0fef624612a4c1b8753a8eb9`.

The complete **211-file reviewable tree excluding this checkpoint itself**
(including the operator/design/task Markdown) hashes to
`10fe9ab9d7ee6d090aaa3979f919cd32d4bc28a394e3ad98a17d56463d26273d`
under the same compact sorted JSON-map encoding. `reviewable-tree.json` retains
that map; `final-source-map.json` additionally records this checkpoint's final
raw-byte hash. This separates stable tested runtime inputs from later evidence
prose without omitting the rest of the reviewable change.

## Hosted CI record

Commit: fd2c8d51b7911265f31a77440f6a1ed7f5f94fb5.
First recorded checkpoint: **[CI 43169838959](https://github.com/grusic91/neurofold/actions/runs/43169838959),
success**, event push, created 2026-11-12T06:40:58Z, completed by 06:44:35Z.
All four jobs conclude success. Backend runner image is **ubuntu-26.04,
20261101.186.1**, OS Ubuntu 26.04.1 LTS, runner agent 2.338.2.

| Hosted backend | Full result | Coverage |
| --- | --- | --- |
| Python 3.12.16 | 2,052 passed / 20 Darwin-only skips | 95.40% |
| Python 3.13.18 | 2,052 passed / 20 Darwin-only skips | 95.37% |

Frontend is 36 unit / 12 browser / 1 integration passes; containers include
158 passes. SQLite versions are **unavailable in this run's logs**: the workflow
did not print them. They are not inferred from a Python release or the runner's
SQLite CLI. The new version-print steps cannot establish a historical runtime
version retrospectively. `hosted-runs-fd2c8d5.json`,
`hosted-run-43169838959.json` and `.log` retain the authorized lookup results.
This records the green hosted-CI checkpoint for fd2c8d5 only; no independent
acceptance, current-tree hosted result or M3 start is claimed.

## Round-7 follow-up — 2026-11-12

The user reports the independent round-7 review accepted L1–L4 and the
informational fixes on the earlier uncommitted tree. This follow-up repairs the
three remaining concurrency/publication test paths, integrity diagnostics and
hostname lookup failure. It does not change production SQLite/child timeouts,
public schemas, scientific codecs, model availability, dependencies or lockfiles.
H1 remains unresolved and M3 has not started.

| Repair | Behavior, test and sensitivity |
| --- | --- |
| Concurrent HTTP submission | At most eight attempts, only for 503/PREDICTION_BUSY with retryable=true, respecting the server's Retry-After. Each attempt reuses the identical key/body. Only the initial four calls enter the synchronization barrier. All final responses must still be 202, share one job ID, and match durable reopening. Four injected initial busy responses fail the old test and pass the repair. |
| Durable concurrent submission | Round 7 retained the value assertions and bounded retries, but construction after the barrier serialized submits on the initialization flock. Its passing runs did not preserve the original race sensitivity. Round 8 corrects this: finish independently retried construction before the barrier, then retry submit separately on the same repository. Only typed PREDICTION_BUSY is retried; raw SQLite exceptions propagate. See T1 below. |
| Slow-publication lease reservation | Uses an already-finished child and the same authored bundle, isolating publication from real subprocess startup. The existing three-second UTC advance, recovery==0 and final succeeded assertions remain. Simulated 100-second startup elapsed time fails the old test and passes the repair; a minimal mutant removing lease reservation still fails the repaired test. Real process lifetime/timeout tests remain unchanged. |
| Integrity diagnostics | Startup and runtime handlers retain exit 65 and log error_type plus recognized fixed authored validation messages, without traceback or chained causes. A fixed-message gate replaces unrecognized/wrapped detail with a generic authored validation message. Four subprocess cases through both entrypoints fail on missing details before and pass after. A private chained cause never appears; an additional unknown-message regression fails on the direct-str intermediate logger and passes the message gate. |
| Hostname diagnostic failure | gethostname is guarded independently of PID/PGID collection. Lookup exceptions yield host_id=null while preserving the marker, known process IDs, failed/SUPERVISION_FAILED with termination false, the stop flag and exit 78. Injected OSError and RuntimeError each escape before the fix and pass after it. |

These repairs close the HTTP/durable/publication deferrals; test-matrix records
resolved treatments rather than future fixes. **Round-8 correction:** although the
assertion text was retained, round 7 weakened the durable submit race by moving
initialization after the barrier. Its native/hosted passes are not evidence of
unchanged transaction-race coverage. T1 below restores that sensitivity.
HTTP/barrier outer hang guards include bounded client retries and
loaded thread startup, with inline justification; server limits are unchanged.
The test-only response protocol supports both installed HTTP client response
types without changing application dependencies.

Raw results are in ignored `backend/outputs/nf04-m2-round7/`. The original round-6
logs and manifests remain in their original directory. Baseline concurrency
probes record four genuine test failures (HTTP busy, service busy, raw SQLite
locked, startup elapsed); the same probes record four passes after the repairs.
The baseline diagnostics record six failures / four passes before repair.
`reservation-mutant.log` records the retained lease invariant's sensitivity.
Initial probe setup mistakes (wrong cwd and early fixture acquisition) are
retained separately under probe-setup and are not counted as sensitivity results.
Initial mypy found the two HTTP response types and missing list annotations;
a structural response protocol and explicit annotations fix those errors.

Each of the **three repaired cases passes 10/10 under native CPU saturation**:
**30 executions with 11 busy loops for 11 reported CPUs**. The stress driver
always terminates/reaps its own load processes before full suites. The final
stress batch follows the privacy-message gate; earlier intermediate full native
passes are retained under intermediate-before-message-gate and are not relabeled
as final-tree checks.

Final full native **Python 3.12.16 and 3.13.2 each pass 2,106 tests**, each at
**95.33% coverage** (113.63 s / 113.60 s). Locked installs, Ruff, formatting and
strict mypy (**102 files**) pass on both. SQLite is **3.53.1 / 3.50.4** respectively.
The additional ten cases cover bounded retry behavior and diagnostic failure
paths. The final code's focused diagnostics run passes **18 cases**. Runtime
3.12 is restored as the default development environment afterward.

The final **168-file runtime/configuration payload** hashes to
`49653c3f327e52e9cddfb19c16c74f7e2c0f649dad0a9534eafba1da0b174dd3`.
The complete **213-file reviewable tree excluding this checkpoint itself** hashes
to `09fce373b8f9a088c90daf5ab8e6f912bd1fb9f577c51032595dc678c6dba65c`.
Encoding is SHA-256 of compact sorted JSON maps from paths to raw-byte SHA-256
hashes. The raw maps and `tested-change-identity.json` are retained in the round-7
output directory. The identity check verifies all runtime inputs predate the
final native checks, and **90 protected API/adapter/core/frontend/schema/license/
configuration/lock files** equal the accepted starting tree. It records no
commit/push authorization. The final artifact manifest hashes the retained logs,
probes and maps separately from source identity.
Frontend source is unchanged; normal npm ci and all AGENTS.md frontend commands
pass (36 unit / 12 browser / 1 integration tests), including browser installation.
Both local Compose configurations validate. No full emulated Linux suite is run
for round 7. New image/compose/controlled smoke and Linux checks are reserved for
the hosted checkpoint, as the user requested.

### Round-7 hosted checkpoint — recorded in round 8

The user authorized the round-7 commit and feature-branch push separately.
[CI **43257968940**](https://github.com/grusic91/neurofold/actions/runs/43257968940)
concluded **success**, event **push** on **fix/nf04-m2-round7-hardening** at
**8b7acc0657a22771829c46f963025f965a3de9f5**. It started
2026-11-12T16:22:36Z and completed by 16:26:16Z. All four jobs passed.
Runner: **ubuntu-26.04**, image **20261101.186.1**.

| Backend Python | SQLite | Full result | Coverage |
| --- | --- | --- | --- |
| 3.12.16 | 3.53.1 | 2,086 passed / 20 Darwin-only skips | 95.33% |
| 3.13.18 | 3.53.1 | 2,086 passed / 20 Darwin-only skips | 95.33% |

Frontend: **36 unit / 12 browser / 1 integration** passes. Compose smoke and
controlled prediction smoke pass, including **158 in-container tests** (one
non-fatal pytest cache-permission warning). Exact metadata, logs and the parsed
record are retained in `backend/outputs/nf04-m2-round7/hosted-checkpoint.json`,
`hosted-checkpoint.md` and `hosted-run-43257968940.*`.

This corrects the committed pre-push pending text. The results are for 8b7acc0;
they do not validate the round-8 follow-up or resolve its newly identified T1
coverage gap. Main was not pushed. No merge or M3 start is implied.

## Round-8 follow-up — 2026-11-12

Work starts from clean 8b7acc0 on fix/nf04-m2-round7-hardening. No production
code, SQLite/child timeout, scientific codec, public schema, dependency or lockfile
changes are included. H1 remains unresolved and M3 has not started.

| Item | Repair and sensitivity |
| --- | --- |
| T1 | Each worker constructs its independent repository with bounded retry **before** the eight-party barrier, then submits with a separate bounded retry on that same repository. This removes the initialization flock from the racing submit path. All eight results, single ID, reopening, conflicts, availability ordering and exact specs remain asserted. A submit-only deferred-BEGIN mutant, with initialization and other writes unchanged, passes the round-7 test 3/3 and fails the repaired test 3/3. No forced sleep or additional rendezvous is used to obtain those mutant failures. |
| T2 | Both entrypoints get an additional startup-private case: startup raises ArchiveIntegrityError('PRIVATE_DETAIL_DO_NOT_LOG'); exit 65, generic authored message, absence of PRIVATE/Traceback are required. Replacing only either main's message renderer with str(exc) fails its dedicated case. |
| R8-REL-1 | The actual 43257968940 round-7 result is recorded above, replacing the pending status. Follow-up run 43280081847 is recorded below after the separately approved commit and feature-branch push. |
| R8-REL-2 | Design and test-matrix now explicitly require M4 remeasurement of the 100 ms Darwin EPERM bound before enabling the first macOS runtime child that spawns helpers, under representative CPU/IO load, with boundary-test and shutdown-margin updates if changed. |
| Optional drift check | A static AST check discovers ArchiveIntegrityError subclasses and literal constructor messages, requiring allowlist membership or a reasoned explicit exclusion. The three InvalidChildOutput literals are explicitly excluded as proposal rejection messages. Removing an existing allowlist entry fails this drift test. |
| Optional retry cleanup | The raw sqlite3 retry branch is removed. A raw database-locked OperationalError now belongs to the non-retry tests and must propagate immediately; only the repository's documented typed PREDICTION_BUSY is retried. |

Raw before/after probes and checks are retained under ignored
`backend/outputs/nf04-m2-round8/`. The initial production startup-mutant probe
was not reached because the subprocess reset PYTHONPATH; this setup miss and its
logs are retained separately and are not counted as a successful sensitivity
result. The corrected probe selects the mutated main by explicit script path,
preserving all test assertions and the actual startup handler.

The restored durable submit test passes **10/10 under native CPU saturation**,
with **11 busy loops for 11 reported CPUs**. The driver terminates and reaps its
load processes before either full suite. The focused startup/drift check passes
**11 cases**. The final full native results are:

| Python | SQLite | Full result | Coverage | Duration |
| --- | --- | --- | --- | --- |
| 3.12.16 | 3.53.1 | 2,109 passed | 95.33% | 116.05 s |
| 3.13.2 | 3.50.4 | 2,109 passed | 95.36% | 115.34 s |

Locked installs, Ruff, formatting and strict mypy (**103 files**) pass on both.
The development environment is restored to Python 3.12 afterward. Normal npm ci
and every AGENTS.md frontend command pass on Node **24.5.0** / npm **11.5.1**:
**36 unit / 12 browser / 1 integration** tests, including browser installation.
Frontend checks run after both full native suites, without overlapping heavy
work. Both the base Compose configuration and its controlled-prediction overlay
validate. An initial attempt to validate the overlay without its required base
file is retained as a setup error, not a product failure or a passing check.
No full emulated Linux suite is run. The follow-up Linux/container smoke results
are recorded below; the earlier hosted result above belongs to 8b7acc0.

The final **169-file runtime/configuration payload** hashes to
`0961c3b36f1566678b8432a5804478cef59b3e8bf802347f6f6dd124ffc12265`.
The complete **214-file reviewable tree excluding this checkpoint itself** hashes
to `06c70b91e4a82694dcc0d9c7e1a3002e3b845e833a05296323ba38a2aff8bed8`.
Encoding is SHA-256 of compact sorted JSON maps from paths to raw-byte SHA-256
hashes. Raw maps and `tested-change-identity.json` are retained in the round-8
output directory. Runtime inputs predate the final native checks; **118 protected
production/backend-script/infra/frontend/schema/license/configuration/lock files**
equal the starting tree. The raw artifact manifest is separate from source
identity.

### Round-8 hosted checkpoint — recorded after authorized push

The user separately authorized the commit (**yes commit**) and branch push
(**push**). [CI **43280081847**](https://github.com/grusic91/neurofold/actions/runs/43280081847)
concluded **success**, event **push** on **fix/nf04-m2-round7-hardening** at
**d7bd884029df6b026f1b0b34714fdd6fa2804129**. It started
2026-11-12T18:27:50Z and completed by 18:31:05Z. All four jobs passed.
Runner: **ubuntu-26.04**, image **20261101.186.1**.

| Backend Python | SQLite | Full result | Coverage |
| --- | --- | --- | --- |
| 3.12.16 | 3.53.1 | 2,089 passed / 20 Darwin-only skips | 95.33% |
| 3.13.18 | 3.53.1 | 2,089 passed / 20 Darwin-only skips | 95.36% |

Frontend: **36 unit / 12 browser / 1 integration** passes. Compose smoke and
controlled prediction smoke pass, including **158 in-container tests** (one
non-fatal PytestCacheWarning for an unwritable pytest cache). Exact metadata,
logs and the parsed record are retained in
`backend/outputs/nf04-m2-round8/hosted-run-43280081847.json`,
`hosted-run-43280081847.log` and `hosted-checkpoint.{json,md}`.

This post-push evidence update records d7bd884 without changing its tested
runtime/configuration payload. The reviewable-tree identity above describes
d7bd884 before this documentation update; it excludes the checkpoint itself.
The post-push evidence and test-matrix edits are recorded separately in
`backend/outputs/nf04-m2-round8/post-hosted-documentation.json`. Main was not
pushed or merged; any change to main requires separate authorization. M3 has
not started and H1 remains unresolved.

## Remaining gates

M3 has not started. Its readiness/restart policy, schema compatibility, remaining
terminal/publication retries, mutation recovery, dependency naming and harness
conditions (including W6/H-01) remain explicit scope. H1 mapping correction and
biological-foundation review remain required independently. Commit approval does
not authorize a push or starting M3; both remain separate gates.
