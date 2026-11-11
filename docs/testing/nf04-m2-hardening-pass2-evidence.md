# NF-04 M2 second-review hardening checkpoint

Date: 2026-11-11. Historical pass-2 implementing-agent software evidence; independent acceptance and
an authorized first GitHub CI run remain pending. This checkpoint follows the
independent re-review of [the historical first pass](nf04-m2-hardening-evidence.md).
M3 is still open. No scientific approval or general platform compatibility is claimed.
Round 3 found a macOS cleanup defect and invalidated the original W2 cleanup
guarantee below. See the [macOS correction](nf04-m2-macos-cleanup-evidence.md) for
the subsequent fix, regressions and current source identity.

## Baseline and evidence preservation

HEAD remains `823a33007f1d0a2453038a8513d9badb0333bb52`. The starting worktree was
the reviewed 42-file uncommitted change set (36 modified, six new), with nothing
staged. Prior work, LICENSE and attribution were preserved. No commit, push, PR,
publication, deployment, remote CI or model execution was performed.

Ignored `backend/outputs/nf04-m2-hardening-pass2/` preserves the supplied request,
`rereview-artifacts.tar.gz`, its per-file `rereview-sha256.json`, the starting
`before-source.json`, first failures, subsequent checks, isolated mutation logs
and final source identities. Reviewer environments/caches and duplicate source
exports were excluded from the evidence archive. No reviewer probe was treated
as an instruction or imported as an application dependency.

## Gate 1 dispositions

| Finding | Correction and regression |
| --- | --- |
| O1 mapping lineage | Scope mapping hashes in artifact `parents` in both manifest and staged descriptors; restore canonical ordering. The regression includes mapping/spec/raw parents, unchanged raw bytes, successful publication and reopen. Input/source identities and scientific hash domains stay unchanged. |
| W1 invalid-output misclassification | Set SUPERVISION_FAILED after successful bundle decoding, before reservation and validating writes. Real SQLite writer locks exhaust retries independently at both writes; the immutable failure records SUPERVISION_FAILED. Early lock release instead succeeds and proves operation retries are active. Decoder/semantic output failures remain INVALID_OUTPUT. |
| Missing failure extension | Both status and failure routes return integrity 500 for a missing modern extension. Nonfailed and inventoried historical failures retain 409; missing jobs remain 404. No historical failure is invented. |
| Failure integrity tests | Independent checksum, job ID/hash, attempt, end-time and terminal-state corruption tests recompute checksums when testing linkage. Both read routes are exercised. Actual UPDATE and DELETE attempts must raise IntegrityError and leave the record unchanged. |
| Linkage precheck | Independently mismatch manifest samples, returned IDs, result ID and raw references before scoping can normalize/reseal them; each must raise InvalidChildOutput. |
| Cancel before launch | An externally observed Event records a launch call; the assertion is outside the supervisor's exception handler. Removing the prelaunch cancellation guard now fails. |
| HTTP assertions | Explicit attachment and private/no-store header checks, and running cancellation 202/Retry-After/pending termination followed by confirmed 200. |
| W2 controlled launcher | Replace blocking FIFO open/read with nonblocking bounded polling, child-exit checks and an interruptible stop Event. The original claim that every startup failure reaped and closed the death pipe was false on macOS: EPERM for an exited, unreaped group could bypass both. Round 3 fixes ProcessChild and restores the immediate-exit child regression; see the macOS correction. The FIFO reader still closes in the launcher finally, with its direct FD assertion gap tracked separately. The acceptance worker wires its signal-driven stop Event into the launcher. Tests cover exit before readiness, silence, malformed signal and shutdown during startup, with cleanup assertions before fallback test cleanup. |
| NF-09 checklist | Add the missing `npm run test:integration` command. Refresh authored fixture identities and inventory both hardening regression files. |

No database/schema migration or new public schema was needed. Frozen M1
job/result/manifest/provenance codecs, status/child schemas and failure/1 bytes
remain unchanged by this pass. Optional dependencies, model registration, frontend
polling, Boltz-2, GPU execution, alignment policy and exports remain outside scope.

## Regression sensitivity

`before-fixes.log` preserves direct reproductions of O1, missing failure routing
and both W1 contention paths. Four initial linkage-test setup failures were
corrected to valid individual records before sensitivity checks; these are not
claimed as product defects. Earlier full runs also caught stale fixture hashes
and an actual macOS process-cleanup failure when the malformed-readiness child
exited immediately. Changing that child to wait hid the adapter defect; it did
not fix it. Round 3 restores immediate exit and fixes the adapter. The original
failing logs and pass-2 hashes remain historical evidence, not closure evidence.

`sensitivity-results.json` records **19 targeted experiments**, each detected:
lineage remapping, postdecode cause, checksum, job/attempt/time/state binding,
missing failure routing, both immutable triggers, all four linkage predicates,
prelaunch cancellation, operation retry, attachment/no-store headers and running
cancel 202. Experiments use isolated source copies and assert behavior, not a
mutation percentage. Startup liveness, timeout and cleanup removals were also
detected. The initial startup shutdown assertion allowed waiting until the job's
own timeout; a tighter two-second response assertion detects that removal too
(`startup-sensitivity-final-results.json`). No claim is made that the secondary
survivors from the prior independent review were all eliminated.

## Executed checks and platform scope

All required native checks used locked installs. Ruff check/format and strict
mypy (both `src tests` and `src tests scripts ../infra/testing`) pass on both
Python versions. The final native logs are `pytest312-verified.log` and
`pytest313-verified.log`; initial failures remain separate.

| Environment | Fresh result |
| --- | --- |
| macOS 27.0.1 ARM64, Python 3.12.16 / SQLite 3.53.1 | **2,025 passed**, 95.46% branch-aware coverage. |
| macOS 27.0.1 ARM64, Python 3.13.2 / SQLite 3.50.4 | **2,025 passed**, 95.43% branch-aware coverage. |
| Native Node 24.5.0 / npm 11.5.1 | `npm ci`, lint, typecheck, build, browser install pass; **36 unit**, **12 browser**, **1 integration** tests pass. |
| Colima Linux 6.8 AMD64 emulation, Python 3.12.16 / SQLite 3.46.1, glibc 2.41, UID 999 | Controlled HTTP/process acceptance passes: retained success/idempotency and variant linkage after recreation, cancellation, graceful shutdown, timeout/forced reaping and worker-loss recovery; **158 affected storage/process/HTTP tests pass**. |
| Same emulated kernel, checks image Python 3.13.18 / SQLite 3.53.1, glibc 2.36, UID 1000 | Locked install, Ruff/format and broad mypy pass; **109 affected tests pass** with ResourceWarning as error. |

Default and controlled Compose configurations validate. Both rebuilt production
services pass health, frontend/proxy and static capability smoke; non-root archive
writes work and torch/boltz are absent. `production-smoke-verified.log` records the
successful probe after Compose health completed. The earlier probe ran too soon,
failed with connection refusal, and was retained separately; it is not counted as
a pass. Image IDs are retained in `docker-images.txt`.

The Linux 3.12 run emits one harmless pytest-cache permission warning because the
non-root runner cannot write its image's backend directory; tests and retained
storage checks pass. The isolated services were stopped after their HTTP phases
to release CPU during process/storage tests. Existing containers, images and
archives were not removed or reused. Test projects use loopback ports
29000/26173 and production smoke uses 29001/26174, with separate named volumes.
Cleanup stops/removes only these projects' containers/networks and retains volumes.

The Linux scope is the affected orchestration suites and controlled acceptance;
this pass does not claim a fresh full Linux backend/frontend matrix or remote CI.
Native browser testing uses synthetic offline fixtures and the installed browser.

## Source identity for re-review

`state-identity.json` inventories **204 source files**, including all eight
untracked files; `final-source.tar.gz` preserves their bytes. The worktree has
39 modified and eight untracked files, nothing staged; HEAD is unchanged.
The final tracked patch and per-file hashes are retained alongside it. SHA-256
aggregates use UTF-8 JSON with sorted keys, compact separators and no newline:

- Source map excluding only this checkpoint (avoids a self-reference):
  `676e31c0cc490a9f993526990d39259a76ec4c621dd02a3f1b213d47392e28bc`.
- Runtime/config/schema/test map (backend, frontend, infra, Compose, schemas and
  fixture inventory):
  `aec2122b5add302f9bddcfbb2e70906ae4506c4b9b6854cfdf2580d4e5c394e0`.
- Tracked `git diff --binary HEAD`:
  `7d8a008d1dc7415d54bd422e286fe117867d170d01c28923a875a62e5450ba99`.

The runtime/config/schema/test map exactly matches the source tar exercised by
Linux Python 3.13; subsequent documentation changes are outside that map. Every
schema, frozen scientific codec checked by the state recorder, dependency lockfile
and LICENSE remains byte-identical to the reviewed baseline. The inventories
include untracked source; a tracked diff alone does not describe this checkpoint.

## Remaining gates

Gate 2 requires explicit push authorization and the first real GitHub CI run;
local Docker is not remote CI. Gate 3 is tracked in
[the M3 entry conditions](../prediction-orchestration.md#second-review-hardening-and-m3-entry-conditions):
worker readiness/restart policy, safe upgrade order plus operation-time schema
version guard, retried terminal `finish()`, M6 frontend mutation recovery, and a
naming rule for child-staged dependencies. These are deferred requirements,
not implemented protections. In particular, a running old worker must be stopped
before storage migration; mixed-version rolling upgrades are not safe yet.

H1/reference ambiguity remains required before NF-05/06 or scientific mapping use.
Existing M4/M5 runtime/resource-limit, deployment and scientific validation gates
remain unchanged. Bounded test-child startup does not establish real model resource
limits or prediction reproducibility.
