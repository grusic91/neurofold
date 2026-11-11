# NF-04 M2 Darwin exit-transition follow-up

Date: 2026-11-11. Implementing-agent software evidence for the remaining round-4
finding. No independent post-fix acceptance, scientific approval or remote CI is
claimed. Changes stay uncommitted; no push, PR, deployment or M3 implementation.

## Starting point and reproduction

The starting tree matched all **206 source hashes** of the
[historical macOS correction](nf04-m2-macos-cleanup-evidence.md): HEAD
`823a33007f1d0a2453038a8513d9badb0333bb52`, 40 modified and ten untracked files,
nothing staged. Round-4 review results (2,033 native tests per Python version,
full Linux 3.13, the loaded-host Linux 3.12 variant timeout and subsequent isolated
passes, and container acceptance) apply to that starting tree, not this follow-up.

The previous fix covered an exited, unreaped leader but missed Darwin's exit
transition: killpg can return EPERM while poll still reports running. Acting at
the **first EPERM**, without a kqueue notification or an intervening poll, failed
all ten native repetitions against the old adapter. A portable gated-child test
and the worker cleanup-error test also failed (`before-fix.log`: 12 failed).
These tests were added before changing production code. Kernel-exit notification
tests alone could not cover this window; the earlier closure claim was incomplete.

Ignored `backend/outputs/nf04-m2-exit-transition/` retains the starting source map,
round-4 ledger/workflow/probes, reproduction failures, check commands/logs,
isolated mutation results and final source bytes/hashes. Earlier artifacts remain
intact. Reviewer probes informed the regressions; they are not runtime dependencies.

## Corrections and behavior

- On EPERM, the adapter waits at most **0.5 seconds** for the leader to become
  waitable, then retries the group signal. If the child remains live, the denial
  propagates. If the leader exits but a group member still cannot be signalled,
  that denial also propagates; leader exit alone is not termination confirmation.
- Reaping waits at most **max(0.5 seconds, termination grace)** and attempts
  death-writer closure in its finally block. Cleanup after a signal error preserves that original error
  after its bounded reap attempt. A truly unsignalable live child no longer makes
  cleanup wait indefinitely with the pipe open. This does not claim an unkillable
  child has been reaped or that POSIX groups contain detached descendants.
- The worker catches cleanup errors, records SUPERVISION_FAILED with termination
  **unconfirmed** when its ownership/storage still permit finishing, and stops
  accepting new work. Cancellation does not become falsely confirmed. Failed
  storage/lease fencing still falls back to existing recovery; finish() contention
  retries remain an M3 condition. An operator must resolve unconfirmed cleanup
  before restarting this worker; no new restart policy is implemented here.
- The repeatedly load-sensitive variant-concurrency test now uses **30-second**
  operation and barrier budgets. It still overlaps four publishers and requires
  one 201, three verified 200 duplicates, exact response bytes and one stored node.
  Timeout-behavior tests keep their deliberately short budgets.

Native regressions begin cleanup at the first EPERM in ten cases per full run.
A portable test releases a real gated child while injecting EPERM plus the old
poll observation, so Linux CI also detects replacing the wait with one poll.
Additional tests check live-denial bounds, denied group signals after leader exit,
and retained failures for cancellation, shutdown and timeout despite cleanup
errors. Actual writer EBADF and exhausted waitpid checks precede fallback test
cleanup. Unknown cleanup also prevents a subsequent queued job from launching.

Seven guard-removal experiments in isolated source copies detect: reverting to a
single poll, removing the reap bound, discarding group denial, masking the initial
error, removing the worker cleanup guard, falsely confirming termination, and
continuing after unknown cleanup (`sensitivity-results.json`). No mutation
percentage or general process-containment claim is an acceptance criterion.

## Documentation and remaining findings

The historical macOS evidence now explicitly retracts complete closure of the
exit path. Its retained health snapshot contains **two three-second timeouts**
among later successes; successful up/wait and HTTP smoke did not prove stable
health checks under load. That text is corrected without discarding the log.
The inaccurate kqueue comment now simply identifies a registration/exit race.
Symlink guidance identifies only the two reviewed default-composition paths:
predictions/ returned ARCHIVE_INTEGRITY and predictions/registered returned
INTERNAL_ERROR. Other sub-folder symlinks were not exhaustively checked.

The deferral table now includes **W6**, missing checkpoint sensitivity for
prelaunch/chunk-read/exception classification, and **H-01**, the controlled
launcher's FIFO-read/child-poll readiness race. Both remain M3 harness requirements.
The live-denial hang and swallowed post-leader group EPERM are addressed above;
other round-2/3 dispositions remain in the historical table. H1 before NF-05/06,
M4/M5 runtime limits, deployment and scientific gates remain unchanged.

M3 still requires worker readiness/restart policy, upgrade order plus an operation
schema-version guard, finish() retry, M6 frontend mutation recovery and staged
dependency naming. First GitHub CI requires explicit push authorization. This
follow-up supplies reviewable local fixes, not authorization to push or start M3.

## Fresh checks and source identity

All required checks use locked installs. Native Ruff/format and both strict
mypy scopes pass on Python 3.12 and 3.13 (97 files broad, 87 narrow).

| Environment | Current-tree result |
| --- | --- |
| macOS ARM64, Python 3.12.16 | **2,049 passed**, 95.49% branch-aware coverage. |
| macOS ARM64, Python 3.13.2 | **2,049 passed**, 95.46% branch-aware coverage. |
| Additional native first-EPERM stress | **40 passes** in four ten-case runs, no escape (`darwin-window-stress.log`). |
| Node 24.5.0 / npm 11.5.1 | `npm ci`, lint, typecheck, build, browser install pass; **36 unit / 12 browser / 1 integration** tests pass. |
| Emulated Linux AMD64, Python 3.12.16 and 3.13.18 | Locked installs, Ruff/format and broad mypy pass; **34 passed, 10 Darwin-only skips on each**. ResourceWarning is an error. |

Both service images build; Compose config/up/wait and backend/frontend/proxy
health/capability smoke pass in the isolated project on loopback 29003/26176.
The retained health snapshot has five successful backend checks and one initial
frontend exit-code-1 check followed by four successes; both services are healthy
at capture. This is point-in-time smoke evidence, not a load-stability claim. Only this
project's containers/network were removed; its archive volume was retained.
See `docker-up.log`, `docker-smoke.log`, `docker-health.jsonl` and image IDs.
The Linux scope is process/worker regressions and the widened variant concurrency
case, not a fresh full Linux suite or full lifecycle acceptance. The exact command
is retained in `linux-command.json`; ten first-EPERM cases are Darwin-only, while
the injected transition/denial tests also run on Linux. No remote CI ran.


`state-identity.json` inventories **207 files**, including all eleven untracked
files. The worktree has 40 modified and eleven untracked files, nothing staged;
HEAD is unchanged. `final-source.tar.gz` and `final-tracked.patch` preserve the
source and tracked diff. SHA-256 aggregates use sorted-key compact UTF-8 JSON
without a newline:

- Source map excluding only this checkpoint to avoid a self-reference:
  `03d846baf6d678c868d302ca0702341895cb74545d8b529d2f497633e4e8bba1`.
- Runtime/config/schema/test map:
  `e0472739243ddd1f1a75c3201efd6f356bfe3e4fe2b54e71440e668ed5081495`.
- Tracked `git diff --binary HEAD`:
  `18c8dba8619e3c2e34e717b6c95788091d3b7cf8d3c94cdb8ee9a1f55cfd41cc`.

The runtime map matches the exact tar exercised by both Linux versions. The only
production changes since round 4 are the process adapter and worker cleanup guard.
Core/scientific codecs, schemas, manifests/lockfiles and LICENSE are unchanged.
All previous checkpoint identities remain historical in their original artifacts.
