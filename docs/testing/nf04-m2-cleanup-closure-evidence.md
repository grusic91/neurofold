# NF-04 M2 focused cleanup closure checkpoint

Date: 2026-11-11. This is the bounded closure patch requested under the user's
conditional approval, followed by a local hardening commit. No push, hosted CI,
M3 implementation or scientific approval is included. The reviewer reported no
remaining medium-or-higher findings; the user read the report/code without
independently rerunning probes. This checkpoint reports targeted implementing-
agent verification, not another independent review cycle.

## Scope and baseline

The starting 51-file worktree on
`823a33007f1d0a2453038a8513d9badb0333bb52` matched all **207 source hashes** of the
[exit-transition checkpoint](nf04-m2-exit-transition-evidence.md). Nothing was
staged. All prior hardening work remains included in the authorized checkpoint.
Raw review/probe material, starting identity and fresh logs are retained in ignored
`backend/outputs/nf04-m2-closure/`; earlier snapshots are not overwritten.

The round-5 reviewer full Linux suites (2,039 passed, ten Darwin skips per Python
version), container acceptance and earlier native matrices apply to the starting
tree. They are historical evidence, not fresh full-suite results for this patch.
Per the user request, verification here is limited to affected checks.

## Five closure items

| Item | Closure and targeted evidence |
| --- | --- |
| EXIT-R5-01 | After the bounded leader-exit wait, retry group signals on EPERM every 1 ms for at most 100 ms. The real same-group EOF-helper proposal publishes **10/10** without false SUPERVISION_FAILED or worker blocking. Persistent denial still raises, leaves termination unconfirmed, closes the death pipe and blocks work. |
| EXIT-R5-02 | Retain the uncertainty block, then retry the complete ownership-checked get/finish operation within min(2 seconds, lease/4), ignoring an already-requested stop only during this bounded recording phase. Transient read and real SQLite writer contention retain the specific SUPERVISION_FAILED outcome for cancellation, shutdown and timeout before stop is finalized. Exhaustion is bounded and reports outcome_recorded=false; no false cancellation or automatic resumption. |
| EXIT-R5-03 | Explicit UNCONFIRMED_CLEANUP, private retained worker-block.json, safe worker/job/attempt/PID/PGID identifiers, error class and outcome/block recording flags. Raw exception messages, child output and sequences are excluded. Both worker entrypoints exit **78**, distinct from normal requested exit 0. The marker blocks new instances before recovery/claim, including partial contents; clearing an Event cannot resume the old instance. |
| EXIT-R5-04 | ChildLauncher documents ownership until return. Ordinary exceptions guarantee cleanup; LaunchCleanupError transfers the unconfirmed Child handle to the worker. Production and controlled launchers guard post-spawn failures and transfer when cleanup fails. Tests cover confirmed cleanup, handle transfer, worker reconciliation and prevention of falsely confirmed cancellation. |
| DOC-R5 | Design and operator guidance now describe bounded waits/retries, uncertainty, exit 78, marker retention and manual recovery before restart. See [design](../prediction-orchestration.md#supervision-and-clocks) and [operator procedure](../../infra/README.md#unconfirmed-cleanup-and-manual-recovery). |

The marker is private operational metadata under staging, not a scientific record,
public API or database migration. A partial/existing marker is never repaired or
deleted automatically. Failure to durably write it is explicitly logged and still
requires exit-78 manual handling; no storage-failure persistence guarantee is
invented. Operator recovery must verify actual process identity/termination, not
blindly signal a potentially reused number. If recording failed, normal lease
recovery is permitted only after uncertainty is resolved and the marker is
preserved/removed deliberately; it may then record WORKER_LOST conservatively.

No model/runtime registration, biological mapping policy, export, GPU operation,
frontend flow, schema/lockfile or scientific hash-domain change is included.

## Targeted verification

Final native results: **713 affected tests passed on Python 3.12.16 and 3.13.2**
(`affected312-verified.log`, `affected313-verified.log`), including fixture identity
validation. Ruff check/format and strict mypy pass in both the broad 99-file scope
and narrow 89-file scope. The dedicated real-helper log is **10/10 passed**
(`helper10.log`); the same ten cases also pass in each native affected-suite run.
No current full-suite coverage percentage is claimed. Emulated Linux AMD64
Python 3.12.16 and 3.13.18 each pass **167 affected tests, 20 Darwin-only skips**,
with ResourceWarning as error (`linux-affected-verified.log`). Locked installs,
Ruff/format and broad mypy pass there too; `linux-command.json` retains the exact
command and `linux-image.txt` identifies the existing checks image. Both worker
Compose configurations validate. The disposable runner was removed automatically;
no existing stack/image/volume was changed. Initial checks retained a new fixture-hash mistake and one formatting
line; all selected behavior tests passed in those runs. The fixture records and
formatting were corrected before final verification. No failure log is discarded
or counted as passing evidence.

The tests cover real helper exit, persistent refusal, actual SQLite contention,
read-BUSY injection, retry exhaustion, ownership transfer, private diagnostics,
retained block reopening, and production/controlled unsuccessful exit codes.
Current full frontend/full Linux/container-lifecycle suites are intentionally not
rerun under the user's targeted-verification instruction. Frontend source is
unchanged from the reviewed baseline; hosted CI will run the authoritative full
checklist after push authorization.

## Remaining gates

Commit is authorized after this focused closure. Pushing and the first hosted CI
checkpoint require separate authorization; local checks do not substitute for
hosted CI. M3 remains gated on that checkpoint and must explicitly include:

- readiness/restart policy that preserves exit-78 manual handling and the block;
- upgrade order and operation-time schema compatibility guard;
- remaining terminal/publication-write retries beyond this cleanup outcome path;
- M6 mutation recovery and dependency naming/ownership rules;
- harness conditions, including W6 checkpoint sensitivity and H-01 readiness race.

**H1 remains separate and unresolved.** Complete mapping correction and the
biological-foundation review before interpreting mapping tables scientifically or
accepting NF-05/NF-06. M4/M5 runtime, deployment and scientific gates are unchanged.


## Tested change identity

`tested-change-identity.json` inventories **210 source files** and the complete
**56-file hardening commit candidate**, including all prior reviewed work and
fourteen new source/documentation files. The parent is
`823a33007f1d0a2453038a8513d9badb0333bb52`. Source and tracked patch are retained as
`final-source.tar.gz` and `final-tracked.patch`. Aggregates use sorted-key compact
UTF-8 JSON without a newline:

- Source map excluding only this checkpoint to avoid a self-reference:
  `e16881024113a267b2676392d4caa0f3cf660370a81b9451fbfa4b99860cb2ef`.
- Runtime/config/schema/test map, matching the exact Linux-tested tar:
  `8b2f34fad8c96b315070cbf4b007c61e5131e2657542c664c6231b0db65689b4`.
- Tracked `git diff --binary HEAD` before the commit:
  `f1e957e8256b237f9040074951921823cb14b487a7eab1cb433dbed6ca0c6bc4`.

Every public schema, scientific core codec, dependency manifest/lockfile and
LICENSE matches the conditional-approval baseline. The only core change is the
framework-independent launcher/diagnostic protocol; no scientific wire format
changes. All index blobs are compared to the tested source map before committing.
The resulting commit is reported separately, avoiding a self-referential commit
hash in this file. Hosted CI remains unexecuted until push authorization.
