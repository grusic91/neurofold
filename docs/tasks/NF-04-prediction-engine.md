# NF-04 — Molecular Prediction Engine

Status: **M1/M2 implemented; focused cleanup closure under conditional approval; fd2c8d5 hosted CI green; post-closure follow-up uncommitted; M3–M5 open.**
[First-pass evidence](../testing/nf04-m2-hardening-evidence.md);
[second-review hardening checkpoint](../testing/nf04-m2-hardening-pass2-evidence.md);
[round-3 macOS cleanup correction](../testing/nf04-m2-macos-cleanup-evidence.md);
[exit-transition follow-up](../testing/nf04-m2-exit-transition-evidence.md);
[focused closure checkpoint](../testing/nf04-m2-cleanup-closure-evidence.md).
[M2 orchestration decisions](../prediction-orchestration.md) and
[M2 execution evidence](../testing/nf04-m2-evidence.md).
[Contract decisions](../prediction-contracts.md) and
[executed evidence](../testing/nf04-m1-evidence.md). Parent: [NF-EPIC-001](../EPIC.md). Initial real adapter target:
Boltz-2; no installation or inference is authorized by this planning document.

## 1. Objective and scientific motivation

Execute traceable structural predictions for exact reference and substituted
sequences through interchangeable model adapters. Keep slow or GPU-dependent
execution outside HTTP handling while preserving inputs and failures for audit.
The output is a computational model, not measured structure or a variant-effect
assay.

## 2. Scope and non-goals

Include capability discovery, validated job submission, durable lifecycle,
separate worker execution, cancellation, bounded resources, fake inference,
one-chain Boltz-2 translation, immutable artifacts and full provenance.

MVP inputs are canonical single polypeptides. The application constructs mutated
sequences using NF-03 before model translation. The adapter does not receive
`A4V` and infer its meaning, and it does not mutate an experimental coordinate
file. Reference and variant are independent jobs using a matched profile.

Exclude API-embedded inference, FastAPI background-task execution, GPU packages
in the API environment, automatic weight downloads at startup, model training,
multi-chain/ligand/affinity workflows, stability or pathogenicity scoring,
high-throughput scheduling and a distributed broker. Boltz-2 is an initial target,
not a guarantee that all neurodegeneration-relevant systems can be modeled well.

## 3. Dependencies

- [NF-03](NF-03-protein-variants.md) immutable definitions and mutated sequence.
- NF-02 exact source snapshots and artifact access.
- [NF-08 M1](NF-08-reproducibility.md) request hashing, manifests, evidence kinds,
  license records and artifact integrity rules.
- NF-09 defines CPU tests and the opt-in real-runtime validation gate. NF-05/06
  consume descriptors and metric definitions rather than runtime-specific files.

## 4. Architecture and interfaces

`PredictionService.submit/get/cancel` is implemented in `application/` and uses
core `DurableJobs`/`PublicationArchive` in `core/orchestration.py`, reference/variant
repositories, and capability records. The older M1 `JobRepository` protocol is an
unused proposal, retained for compatibility; it is not the transactional M2 seam.
`PredictionWorker` uses the injected `ChildLauncher`; no dispatcher/runtime is registered. HTTP handlers validate/submit/return; they do not
import or invoke a model. Composition selects storage/dispatch implementations.

Preserve the synchronous worker seam:
`PredictionAdapter.predict(request, *, output_dir) -> PredictionResult`.
Evolve the existing NF-01 frozen records explicitly: request adds versioned,
typed profile/parameter/source references; result adds multiple sample descriptors,
confidence/artifact references and a manifest reference while retaining or
deliberately migrating the current path fields. Update the protocol's tests and
all callers in M1; do not maintain conflicting legacy and rich contracts. Core
uses standard-library types only; arbitrary dictionaries cannot bypass profile
validation. Paths are worker-internal, never public artifact URLs.

Introduce SQLite **only here**, for durable job metadata and transactional
claim/status/idempotency operations; use the standard-library adapter behind
`DurableJobs`. Immutable scientific inputs/outputs remain in ignored filesystem
stores. Initial topology: one API process and one separately launched worker on
one host, one running job at a time. Atomic claim/version checks prevent duplicate
execution; worker/API mutations use short transactions, never locks held through
inference. No network filesystem for this database.

The API inserts a queued job; the independently started worker polls/claims it.
The worker launches the selected adapter in a child process with an isolated
attempt directory and explicit timeout. It supervises heartbeats and cancellation,
terminates the child process group when required, waits for exit, and verifies
outputs before publishing. All writes are staged then atomically registered.
`/health` remains pure liveness and does not initialize the repository or runtime.

For Linux/NVIDIA, provision a separate, pinned worker environment/image and
lockfile, including its exact supported Python version and CUDA/PyTorch/runtime
dependencies. API Python 3.12+ support is unchanged; if the selected upstream model
requires a different worker Python, document the isolated compatibility boundary.
Model imports occur only after selecting that adapter in the child. macOS and
ordinary CI run the fake adapter without weights, network or scientific runtime.

Future remote execution uses a versioned immutable input bundle and output manifest
through dispatch/artifact protocols. It must not require shared local paths or
direct API database access. Transport, authenticated worker trust, leases and
object storage are a later deployment decision; do not claim local SQLite solves
remote scheduling.

## 5. Data models and API contracts

| Record | Required content |
| --- | --- |
| `AdapterCapability` | adapter/profile/version, evidence kind, supported alphabet/molecule types, parameter schema/defaults, sequence/sample/time limits, MSA modes, runtime availability and reason |
| `PredictionSpec` | schema version, reference ID/hash, optional variant ID, exact input sequence/hash, adapter/profile version, complete resolved parameters, seed, MSA/template/constraint artifact IDs/hashes or explicit none, code identity |
| `PredictionJob` | job ID, immutable spec/hash, state/version, submission/start/end times, cancellation flag, attempt ID, worker/lease identity, heartbeat, parent retry ID, sanitized error, result/manifest IDs |
| `PredictionSample` | sample ID, model-returned rank plus ranking definition, structure descriptor, chain/token-to-residue map, confidence descriptors, raw artifact IDs/hashes |
| `PredictionResult` | all samples, manifest ID/hash, raw output inventory, warnings; worker validates before success |

`seed` is an explicit integer in the selected profile's documented range. Resolve
all defaults before request hashing. Reject unknown parameters and incompatible
MSA modes; never pass arbitrary CLI flags, paths or shell fragments from HTTP.
The server loads sequences from immutable records, recomputes hashes, and does
not trust sequence bytes supplied alongside an ID.

M2 uses the additive `neurofold-prediction-status/1` envelope around the unchanged
M1 job with an explicit nullable operational failure reason. Result and manifest
bodies keep their exact M1 contracts. See the linked orchestration guide for
required fields/nulls, precise errors, resource bounds and recovery semantics.

| Method/path | Contract |
| --- | --- |
| `GET /v1/prediction-capabilities` | 200 static profiles/limits/availability; authored synthetic profile is `contract_only`, Boltz-2 unavailable; no runtime probe |
| `POST /v1/prediction-jobs` | `{reference_id, variant_id: null\|id, adapter_profile_id, parameters, seed, msa_artifact_id: null\|id, retry_of_job_id: null\|id}` plus required `Idempotency-Key`; 202 status envelope with `Location` and `Retry-After: 1` |
| `GET /v1/prediction-jobs/{job_id}` | 200 status envelope with full M1 state/timestamps/stage/null progress/failure/result refs; 404 unknown |
| `POST /v1/prediction-jobs/{job_id}/cancel` | Required `{}`; 202 pending, 200 queued/already cancelled; 409 succeeded/failed |
| `GET /v1/prediction-jobs/{job_id}/result` | 200 verified M1 result; 409 unless succeeded |
| `GET /v1/prediction-jobs/{job_id}/manifest` | 200 verified M1 successful provenance; 409 unless succeeded |
| `GET /v1/prediction-jobs/{job_id}/artifacts/{artifact_id}` | Verified registered bytes only from the bound graph; 404 unknown, 500 known corruption |

One idempotency key reused with the same resolved spec returns the existing job;
different content returns 409 `IDEMPOTENCY_CONFLICT`. Record keys durably for the
job's retention period. Explicit retries use a new key/job ID and `retry_of_job_id`
in the submission schema; they retain the prior failure rather than overwrite it.
Reject incompatible reference/variant pairs with 422, missing records with 404,
admission limits with 429, and unconfigured worker/profile with 503. Accepted jobs
can fail later; a 202 response is not a scientific result.

```mermaid
stateDiagram-v2
  [*] --> queued
  queued --> running: worker claims
  queued --> cancelled: cancel before claim
  running --> cancelling: cancel requested
  running --> succeeded: verified artifacts and manifest committed
  running --> failed: execution, integrity, timeout or worker loss
  cancelling --> cancelled: child exit confirmed
  cancelling --> failed: worker lost before confirmation
  succeeded --> [*]
  failed --> [*]
  cancelled --> [*]
```

Terminal jobs are immutable. Cancellation racing with success is serialized:
whichever terminal commit/transition wins determines the response; no success may
be committed from `cancelling`. Partial attempt files remain non-result artifacts.
Use a proposed 5-second heartbeat and 60-second lease for the local supervisor;
test with a fake clock and tune before deployment. After lease expiry, fence the
attempt and mark `failed/WORKER_LOST`; late output from the fenced attempt cannot
publish. Do not automatically rerun possibly completed inference. Stage progress
is nullable: show `queued`, `preparing`, `inference`, `validating`, not invented
percentages. Capacity and execution deadlines are required profile settings.

### Boltz-2 adapter translation and scientific outputs

Translate the exact constructed sequence to the pinned release's documented
protein YAML schema, chain `A`. Boltz's current
[prediction documentation](https://github.com/jwohlwend/boltz/blob/main/docs/prediction.md)
describes custom MSAs, optional server-generated MSAs, a single-sequence mode,
structure files and confidence outputs. Reverify this against the selected release.
Make MSA policy explicit per job: stored local MSA, disclosed opt-in remote
generation, or explicitly selected single-sequence mode with a limitation warning.
Never silently change modes when a service fails. Validate each MSA query against
the exact input sequence; reusing a reference MSA for a variant requires a recorded,
reviewed query-row transformation, not accidental cache reuse.

Keep each job in a fresh output directory so upstream cache/override behavior
cannot substitute an earlier run. Capture the emitted input YAML, processed inputs,
MSA/template artifacts, command arguments, logs, coordinates and confidence files
as permitted. Network MSA generation transmits the sequence; explain this before
submission and record endpoint/version/time and returned bytes.

Normalize supported per-residue confidence, pTM, and optional PAE/PDE only with
explicit source fields, scales, units and token/residue mapping. Preserve raw
values and files. Interface metrics are unavailable for a monomer where not
scientifically applicable; absence is not zero. Do not infer scale from magnitude
or treat generic B-factors as confidence. Export every returned sample and its
ranking policy; selection of a displayed sample must remain visible.

These outputs support model inspection and cautious geometric comparison. They do
not directly measure mutation-induced stability, aggregation, toxicity or disease
causality. Affinity outputs are outside this single-chain MVP.

## 6. Implementation milestones

1. **M1 — Contracts/capabilities (complete):** one authoritative evolved NF-01
   seam; strict versioned capabilities, resolved inputs, lifecycle/attempt/fencing,
   samples/maps/confidence and complete successful-provenance contracts; pure
   publication validation, safe typed errors, schemas and offline synthetic tests.
   No execution/storage implementation. See the linked guide/evidence above.
2. **M2 — Durable orchestration (implemented; hardening re-review pending):** SQLite
   jobs/attempts/idempotency, fenced atomic transitions, separate child supervisor,
   leases/deadlines/cancellation, verified graph publication, retained reads and
   strict HTTP routes. Test-only controlled children copy authored M1 bundles;
   no executable fake adapter or frontend interaction is included.
3. **M3 — Fake vertical slice:** deterministic synthetic coordinates and known
   confidence, injected failures/timeouts, separate CPU worker and frontend polling.
   Fake execution is never a fallback for a failing real model.
4. **M4 — Real-runtime gate:** choose exact Boltz-2 revision/weights, verify
   licenses and checksums, lock separate dependencies, select MSA policy and test
   limits on named Linux/NVIDIA hardware. Document startup commands at this stage.
5. **M5 — Boltz-2 integration:** translate inputs, supervise real execution,
   validate mappings/confidence/provenance and run reviewed reference/variant
   smoke experiments. Record limitations and release evidence for NF-09.

## 7. Acceptance criteria

- API startup, health, domain tests and fake execution work with no GPU/model
  package. Accepted jobs remain queryable across API restart.
- A separate worker claims a job once; crashes, expired leases, cancellation,
  timeout and failed artifact validation cannot produce a successful record.
- Submitted reference/variant sequences and hashes match NF-02/03 exactly. Matched
  comparisons expose any difference in profile, parameters, MSA or environment.
- Real execution is enabled only for a reviewed pinned runtime with explicit
  limits, weight identities/licenses and input-disclosure policy.
- All returned samples/raw outputs and their manifests are preserved; missing
  confidence and unsupported inputs have explicit reasons.
- Remote execution can be added through protocol implementations without model
  imports or shared-path assumptions in API/core.

## 8. Automated testing requirements

Fake-adapter unit/API tests cover valid reference/variant jobs; parameter/default
hashing; unsupported alphabets/limits; unknown records/profiles; idempotency;
state transitions; duplicate claims; cancellation at each stage; success races;
timeouts; restart/lease expiry; stale worker publication; disk full; corrupt,
missing or mismatched outputs; and safe error serialization. Test child cleanup
with a harmless controllable subprocess, not actual inference. Verify queued and
completed jobs survive repository reopening.

Contract tests validate every route/status and artifact/manifest link. Import
tests forbid optional model/numerical imports in API/core and verify health is
independent of job/worker availability. Adapter translation tests use synthetic
YAML/output fixtures and mocked subprocess boundaries, not weights.

Opt-in Linux/NVIDIA tests exercise the pinned real adapter, MSA handling, memory/
time limits, coordinate/confidence mapping and provenance on public reviewed
inputs. They are separate from offline CPU CI. Use justified numerical tolerances
and inventory invariants, not GPU byte-for-byte golden coordinates.

## 9. Scientific validity and reproducibility

NF-08 captures input/source hashes, adapter/model revisions, checksummed weights
and license, resolved parameters, seed, preprocessing/MSAs/templates, lockfiles,
code revision/dirty state, OS, CPU/GPU, driver, CUDA and relevant library versions.
Pin runtime image digests; the existing development image tags are insufficient
scientific runtime identity. Record known nondeterminism and all sample selection.

Compare reference/variant predictions under a declared matched protocol, and
report sample/seed variation where multiple runs exist. A single matched seed
does not isolate a causal mutation effect or guarantee identical GPU execution.
Discuss disorder, missing biological partners, constructs and training overlap;
the MVP is not an independent accuracy benchmark or an in-vivo mechanistic assay.

Upstream currently describes code and weights as MIT in its
[repository](https://github.com/jwohlwend/boltz). Verify the exact selected code,
weights, auxiliary databases and MSA service terms independently before M4; record
their notices and redistribution permissions. NeuroFold's Apache-2.0 license does
not replace those terms.

## 10. Risks and unresolved decisions

- **Real profile:** exact release, weights, CUDA stack, GPU memory and sequence/
  sampling limits are unresolved until M4 measurements. Fake work can proceed.
- **MSA disclosure/reproducibility:** choose reviewed local databases or an
  explicitly disclosed server policy, retain returned artifacts, and document
  licensing/storage constraints. Unrecordable preprocessing is a release blocker.
- **Protocol migration:** the NF-01 path-only result is insufficient for multiple
  samples/confidence. M1 must make one authoritative versioned contract.
- **Local coordination:** SQLite plus local files supports the declared single-host
  topology only. Remote workers need a separate deployment/security design.
- **Scientific applicability:** target selection must include relevant monomer/
  assembly/disorder limitations; failure on a target is reportable, not replaceable
  by a plausible synthetic result.

## Historical M1 boundary and carried gates

The public interfaces/identity documents and exact versions are specified in
[the prediction guide](../prediction-contracts.md). NF-02/NF-03/NF-08 frozen
records, identity/fixture bytes and archive semantics are preserved. The NF-08
skeleton still cannot certify successful predictions. The authored capability
profile is contract-only, not fake execution or measured real capacity.

M2 owns SQLite/idempotency, transactional final fencing/state checks, staging and
publication, supervisors and routes; M3 owns executable synthetic inference and
its vertical slice; M4 chooses reviewed pinned real releases/licenses/weights and
measures named hardware; M5 integrates real Boltz-2 execution. Independent review
remains required at the real prediction/comparison gates. The historical NF-03 M3
stopped-daemon gap is superseded by newly executed variant route/publication and
retained-linkage checks in the hardening checkpoint. Current acceptance gaps are
listed there; historical reports are not relabeled as fresh execution.

## Independent-review hardening gate

The [separate checkpoint](../testing/nf04-m2-hardening-evidence.md) records H2/H3,
M1–M5/M7–M10 and supervision findings, compatibility decisions, regression sensitivity,
platform checks and deferred triggers. M3 begins only after independent re-review of
this checkpoint. H1 and reference ambiguity are separately required corrections
before scientific use of biological mappings; no alignment policy changes belong here.


The second pass addresses O1 mapping lineage, W1 failure classification, missing
failure-extension routing, sensitive regressions and W2 bounded controlled-child
startup. Subsequent review conditionally approves moving forward after the five
focused cleanup closure items; the closure checkpoint records their targeted
verification. Hosted CI for fd2c8d5 is recorded green below; this follow-up
remains uncommitted and untested on hosted CI. M3 must
include the [explicit entry conditions](../prediction-orchestration.md#second-review-hardening-and-m3-entry-conditions):
worker readiness/restart policy (manual recovery for integrity exit 65 and cleanup
uncertainty exit 78), upgrade order and schema-version guard, terminal
write retries, M6 mutation recovery UX and child-staged dependency naming. These
are tracked requirements, not completed features.


The focused closure includes EXIT-R5-01 bounded Darwin signal retries,
EXIT-R5-02 bounded uncertain-outcome recording, EXIT-R5-03 persistent blocking and
exit diagnostics, EXIT-R5-04 launcher ownership transfer, and DOC-R5 manual
recovery. These narrow protections must remain in M3. General readiness/restart,
schema compatibility, remaining terminal/publication retries, mutation recovery,
dependency naming and W6/H-01 harness conditions are still explicit M3 scope.
H1 mapping correction and biological-foundation review remain separate required
work before scientific interpretation or NF-05/NF-06 acceptance.


Dated state note (2026-11-12): local main and origin/main are fd2c8d5, and the
origin reflog records the 07:40:56 +0100 push. Earlier no-push statements are
historical. The **first recorded hosted CI checkpoint** is
[CI 43169838959](https://github.com/grusic91/neurofold/actions/runs/43169838959),
**success** for fd2c8d5 (2026-11-12). The user attributes the push to “Me”.
This uncommitted follow-up is not covered by that hosted result.
Current follow-up: [post-closure evidence](../testing/nf04-m2-post-closure-evidence.md). H1 is unresolved; M3 has not started.
