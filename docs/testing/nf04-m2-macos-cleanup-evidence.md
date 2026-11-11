# NF-04 M2 round-3 macOS cleanup correction

Date: 2026-11-11. Historical implementing-agent evidence for the round-3 medium
finding. M2 acceptance and the first authorized GitHub CI run remain separate
steps. Round 4 found an uncovered Darwin exit-transition window: poll() can still
report running when killpg already returns EPERM. The closure claim below was
incomplete; see the [exit-transition follow-up](nf04-m2-exit-transition-evidence.md).
No push, commit, PR, deployment, model runtime or scientific approval is
included. M3 remains under its documented entry conditions.

## Baseline and correction

The starting tree matches all **204 per-file hashes** in the pass-2 checkpoint:
HEAD `823a33007f1d0a2453038a8513d9badb0333bb52`, 39 modified and eight untracked
files, nothing staged. Existing work, lockfiles, scientific schemas/codecs and
LICENSE were preserved. Ignored `backend/outputs/nf04-m2-macos-cleanup/` retains
the request, round-3 ledger/workflow and relevant probes, starting hashes/patch,
reproduction failures, check logs and the final source inventory.

The independent round-3 review reports both full Linux suites passing all 2,025
pre-fix tests on this exact starting tree, plus full container acceptance. These
are reviewer results on the **pre-fix** identity; they are not relabeled fresh
checks of the corrected tree. The earlier loaded-host Linux variant-test timeout
passed alone and in the idle full rerun. The recommendation was one macOS fix,
then M2 acceptance; the implementer does not claim a post-fix independent review.

Darwin can raise PermissionError when signalling a process group whose child has
exited but is still unreaped. Previously this escaped `terminate_and_reap()`
before waiting or closing the parent-death pipe, then escaped the worker's finally
block. The first pass-2 malformed-readiness failure exposed this production bug.
Changing that test child to wait hid the bug. The W2 row and attribution in the
[pass-2 evidence](nf04-m2-hardening-pass2-evidence.md) are now corrected.

The local fix is confined to the process adapter:

- Tolerate PermissionError only after `poll()` confirms the child exited; preserve
  permission errors for a live child.
- Run reaping from the termination finally block, even if signalling fails.
- Close and invalidate the death writer in the reap finally block, even if waiting
  or the final group signal raises. Existing descendant SIGKILL behavior remains.

The malformed-readiness test child again exits immediately. New tests observe real
kernel exit without consuming status (Darwin kqueue; Linux waitid/WNOWAIT), then
invoke cleanup while the child remains unreaped. Cancellation, shutdown and a
still-owned timeout must retain their terminal state. Assertions verify actual
waitpid exhaustion and EBADF for the closed death writer before fallback test
cleanup. Additional injected errors check both finally blocks, live-child denial,
and Darwin's exited-group behavior on Linux CI too. No sleep coordinates the exit
race. The FIFO reader's direct close assertion is still a separate low test gap.

`before-fix-reproduced.log` records six failures and one passing live-denial test
against the old adapter. Initial helper setup and timeout-fixture errors were
corrected separately: kqueue needs explicit closing, and the timeout must advance
past the job budget while remaining inside its lease. These are not additional
product findings. Four isolated guard-removal experiments detect removal of the
exited-error guard, the live-child check, pipe-finally and termination-finally;
logs and exact targets are retained in `sensitivity-results.json`.

## Validation and source identity

Locked installs and every required native check were rerun. Ruff check/format
and strict mypy pass on both Python versions, for both `src tests` (87 files) and
`src tests scripts ../infra/testing` (97 files).

| Environment | Fresh result |
| --- | --- |
| macOS ARM64, Python 3.12.16 | **2,033 passed**, 95.48% coverage (`pytest312-verified.log`). |
| macOS ARM64, Python 3.13.2 | **2,033 passed**, 95.48% coverage (`pytest313.log`). |
| Node 24.5.0 / npm 11.5.1 | Locked install, lint, typecheck, build and browser install pass; **36 unit / 12 browser / 1 integration** tests pass. |
| Emulated Linux AMD64, Python 3.12.16 and 3.13.18 | Locked installs, Ruff/format and broad mypy pass on both; **27 affected process tests pass on each**, ResourceWarning as error. |

The first full Python 3.12 run started before the fixture hash/timeout setup
corrections and failed those two checks; it is retained as `pytest312.log`, and
the final run passes. The fresh Docker build succeeds for both services. The
initial Compose health wait reported unhealthy while emulated checks were active;
the retained backend-health.json also contains two three-second health-check
timeouts among later successful checks. The repeated up/wait and HTTP smoke
succeeded; this does not establish stable health checks under emulated load. The health settings
were not changed. `docker-smoke.log` records backend/frontend/proxy health, static
contract-only/unavailable capabilities and non-root runtime. `docker-up.log` keeps
the initial failure; `docker-up-verified.log` keeps the successful wait. The
isolated project uses loopback 29002/26175, is removed without deleting its archive
volume, and leaves pre-existing Docker resources untouched.

The exact Linux command is retained in `linux-command.json`. The current Linux
scope is the affected process suites, not a repeated full matrix. Earlier pass-2
and independent round-3 full-matrix results remain historical. No remote CI ran.
`state-identity.json` inventories **206 source files**, including all ten
untracked files. The worktree has 40 modified files and ten untracked files;
nothing is staged and HEAD is unchanged. `final-source.tar.gz` and
`final-tracked.patch` preserve the source bytes and tracked diff. Aggregates use
UTF-8 JSON with sorted keys, compact separators and no newline:

- Source map excluding only this checkpoint to avoid a self-reference:
  `4a975875ef5d7af8aa62c2d2373169d482dda5abd4c8dcd8ded2b7f43c5e6179`.
- Runtime/config/schema/test map:
  `efce25d2285faeede8d2747d78f06cb1add6d93c3e84ad1d3d2104c6b2bfc86d`.
- Tracked `git diff --binary HEAD`:
  `16c1e6b05a0630c2858cff0de0dc889da22ff712aa5e6db6e2ca8c6d1d99be10`.

Every runtime/config/schema/test file matches the source tar used by both Linux
runs. The only production source change since the reviewed 204-file baseline is
`adapters/prediction_process.py`. Schemas, dependency manifests/locks, the remaining
production code and LICENSE are byte-identical to that baseline. Historical
pass-2 identities remain in their original ignored artifacts; corrected W2 prose
is not asserted to match the old snapshot.

## Non-blocking findings and deferred triggers

The following are explicit deferrals, not claims of fixes or waivers. Production
code outside the macOS adapter fix is unchanged in this follow-up.

| Finding | Disposition and trigger |
| --- | --- |
| Colliding parents after remapping classified PUBLICATION_FAILED | Open; address child-output validation/classification before M3 expands staged output shapes. |
| Staged dependency descriptors remapped; child-local names discarded (O2/O4) | M3 naming rule must distinguish retained dependencies from owned outputs and define preservation of child-local names. Current output IDs do not preserve local IDs. |
| Failure route omits tampered label/cause cross-checks | Open tamper-only consistency gap; include in M3 retained failure validation. |
| Publication writes not retried; bundle-read IO labeled INVALID_OUTPUT | M3 terminal-write/recovery work must include these older publication/classification gaps alongside finish() retry. |
| Re-sort test probabilistic, FIFO-reader close and reason-on-nonfailed guards untested | M3 regression strengthening; no deterministic coverage claim for these guards. |
| Variant concurrency test's five-second budget tight under emulation | Round 4 widens this test's operation and synchronization budgets to 30 seconds; concurrency and publication assertions remain unchanged. Earlier load-induced failures are retained. |
| SIGTERM Event.set re-entrancy window | M3 worker readiness/shutdown design; the macOS process fix does not change signal handlers. |
| DB-3 startup/init-lock failure, W4 backward clock/raw IO exits, W5 launch failures draining queue | M3 readiness/restart/error-recovery policy must define these cases. |
| DB-4 ANALYZE/PRAGMA optimize introduces rejected schema objects | Open deployment/maintenance policy; do not claim these maintenance commands are supported before that policy and schema validation are reviewed. |
| API-A2 committed mutation followed by read failure loses uncertainty; API-A3 cancel status/body snapshot split | M3 mutation recovery and HTTP outcome consistency, before expanding UI mutations. |
| API-A4 retained IO conflated with integrity; API-A5 pre-connect access errors imply false uncertainty | M3 storage/error classification and retry work. |
| API-A6 prediction sub-folder symlink error translation | Open deployment configuration gap. integration.md, orchestration guidance and the first-pass M4 row now qualify the incorrect broad 503 claim; no runtime fix is included. |
| CL-5 production-worker entrypoint evidence thin | Retain full entrypoint startup/shutdown acceptance before adding M3 executable registrations; round-3 reviewer evidence on the starting tree is recorded separately. |
| API-A7/CL-2 headers and running cancel tests, CL-3 NF-09 checklist, CL-4 hardening fixture inventory | Closed in pass 2 and independently verified in round 3. |
| W6 interrupted checkpoints lack regression sensitivity | Open; strengthen prelaunch, chunk-read and exception-cause reclassification checkpoint tests before M3 execution expands. |
| H-01 readiness read/poll race | Open controlled-launcher gap; a child can write ready and exit between the reader check and poll. Review a final FIFO drain before rejection during M3 harness work. |
| CL-1 Linux completeness wording | Historical results and current affected-suite scope are explicit; no fresh full-matrix or remote CI claim. |

Gate 2 still needs explicit push authorization. M3 must include readiness/restart,
upgrade order and operation-time schema-version guard, finish() retry, M6 frontend
mutation recovery and child-staged dependency naming. H1 remains required before
NF-05/06 and scientific mapping use. M4/M5, deployment and scientific gates remain
unchanged. See the [entry conditions](../prediction-orchestration.md#second-review-hardening-and-m3-entry-conditions).
