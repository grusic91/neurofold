# NF-04 M1 — Contracts/capabilities acceptance evidence

Date: 2026-11-10. Implementing-agent software validation against initially clean
`df4c6960bb16e9095e1c24498b5b1481b50e7045`. **M1 complete; M2–M5 remain open.**
Existing NF-02, NF-03 and NF-08 work was inspected and preserved. Changes remain
uncommitted; no commit, push, publication or PR. No dependency/lockfile, LICENSE,
frozen schema/fixture, archive, application/API composition or frontend source change.
This is software contract evidence, not independent scientific approval.

## Interfaces and identity decisions

[The prediction guide](../prediction-contracts.md), authored before dependent
implementation, specifies fields, exact versions, supported types/values, absence,
error precedence, lifecycle invariants, identities and publication boundaries.
`core/prediction.py` exports one authoritative `PredictionRequest`/`PredictionSpec`
class and rich `PredictionResult`. Synchronous
`PredictionAdapter.predict(request, *, output_dir) -> PredictionResult` remains.
NF-01's sequence/seed-only and path-only constructors are deliberately migrated;
inspection found no executable adapter/callers. Protocol signature/import and
migration rejection are tested. Paths stay inside later worker staging; public
scientific records use registered IDs and hashes.

Four additive v1 families are implemented: `neurofold-prediction/1`,
`neurofold-prediction-job/1`, `neurofold-prediction-result/1` and
`neurofold-prediction-provenance/1`. Every wire field/default/null is required;
unknown fields/versions, coercion, duplicate keys, floats and unsafe integers fail.
Versioned JSON Schemas accompany the strict standard-library codecs. The schema
generator is reproducible and included in strict mypy/CI checks. Schema shape
validation does not replace domain or byte validation.

A spec embeds a validated immutable profile, exact source/optional NF-03 variant
references, independently hashed input sequence, complete resolved parameters,
seed, auxiliary policies and registered input identities, code/dirty-patch identity
and ordered transformations. Profile validation cannot be bypassed by arbitrary
dictionaries/CanonicalObject. Full spec canonical JSON is the scientific input
identity, separate from sequence/raw domains and operational job/attempt/time/retry
identity. A full independently spelled literal document and fixed SHA-256 golden
(`5eedf8b6a799e1350b343733265c13dabaa9f2d7d03af52189ab815701b1e8ce`)
anchor its exact bytes. NF-03 validates exact derivation/linkage; no substitution
logic or variant identity document is duplicated.

Static capability inspection requires no runtime import/probe, provider, GPU or
weight access. The shipped authored synthetic profile is **contract_only** with
small authored bounds, not measured model capacity or fake execution. Boltz-2 is
unavailable with unresolved version, weights/licenses, runtime and measured limits;
no supported release or reviewed license is invented.

## Lifecycle and successful-publication guarantees

Pure snapshots validate queued → running/cancelled, running →
cancelling/succeeded/failed, cancelling → cancelled/failed. Terminal records cannot
transition or be rewritten. Cancellation requires confirmed termination to become
cancelled, persists through failure and forbids success from cancelling. Attempt,
worker, lease, heartbeat and positive fencing identities are explicit. Stale job
versions, wrong/fenced/expired attempts cannot propose success. Retry creates a
separate linked queued job. Unknown progress stays null; declared progress uses
integer basis points. Tests model two proposals against one snapshot and explicitly
do not claim actual race resolution. M2 must recheck state/version/lease/fence
atomically inside the success transaction.

Samples retain unique identities and ranks, explicit ranking definitions,
registered structure/raw references, separate predicted mappings, input/token/
coordinate numbering, angstrom/Cartesian conventions, transformations and source-
defined confidence scales/units/mappings or reasoned absence. Equal structure bytes
can belong to independent samples without erasing sample identities. Missing
confidence is not zero; generic B-factors/ranking do not establish accuracy.

Complete successful provenance is separate from the unchanged NF-08 skeleton.
It retains the full exact spec/source receipt, model/version and independent
checksummed weight rights, code/locks, runtime/OS/hardware/libraries, accelerator/
driver/CUDA applicability, complete attempt/timing, preprocessing, actual captured
auxiliary inputs, all samples/raw descriptors, warnings, nondeterminism and limits.
Synthetic model/weight states must be explicitly not_applicable with reasons;
unavailable is rejected. Required real model/weight/runtime identity cannot be
unknown. Remote policy declarations alone are incomplete: resolved local input
bytes, exact declared query identity, provider/version and capture time are needed.
The manifest identifies its result by ID only; the result hashes the manifest,
avoiding self-checksums and impossible result/manifest checksum cycles.

Pure publication validation checks verified inputs/profile, running active attempt,
cross-record identities/times/evidence/inventories, completeness, declared time and
output bounds, available artifact sizes/raw hashes, dependency rights consistency,
closed artifact parent identities and acyclic raw lineage via an injected resolver.
Safe typed failures expose static codes and allowlisted stage details only.
There is no exception-message classification or copying paths, sequences,
credentials, logs or raw exception text into public errors.

These guarantees concern supplied records and bytes. They do not prove truthful
runtime capture, exhaustive adapter file discovery, molecular/MSA parsing, model
execution, biological validity, license approval or database atomicity. No artifact
publication, persistence, executable fake adapter, dispatcher/supervisor, polling,
prediction route, frontend interaction, SQLite, model installation, downloads,
container/GPU provisioning, real inference or export is implemented.

## Executed software checks

macOS Apple Silicon CPU-only: uv **0.13.7**, default CPython **3.12.16**, separate
Homebrew CPython **3.13.2**, Node **v24.5.0**, npm **11.5.1**.
`UV_CACHE_DIR=/tmp/neurofold-uv-cache` was set on every uv command to keep cache
writes inside the permitted temporary directory. From `backend/`:

```sh
uv sync --locked
uv run --locked python --version
uv run --locked ruff check . ../infra/testing
uv run --locked ruff format --check . ../infra/testing
uv run --locked mypy src tests scripts ../infra/testing
uv run --locked pytest
```

All passed. Final Python 3.12: **1,867 passed, 0 failed**, **97.43%** combined
statement/branch coverage (90% gate), **53.50 seconds**. Strict mypy checked **70**
source files; Ruff formatting checked 70 files. Compared with the prior 1,341-test
checkpoint, the new contract suite adds **526 tests**.

For every alternate command below, both the same UV_CACHE_DIR and
`UV_PROJECT_ENVIRONMENT=/tmp/neurofold-nf04-py313` were set. `--python 3.13` was
supplied consistently, including lint/format/types and sync:

```sh
uv sync --locked --python 3.13
uv run --locked --python 3.13 python --version
uv run --locked --python 3.13 ruff check . ../infra/testing
uv run --locked --python 3.13 ruff format --check . ../infra/testing
uv run --locked --python 3.13 mypy src tests scripts ../infra/testing
uv run --locked --python 3.13 pytest
```

All passed. Final Python 3.13: **1,867 passed, 0 failed**, **97.43%** combined
coverage, **53.44 seconds**. The alternate pytest used
`COVERAGE_FILE=/tmp/neurofold-nf04-coverage313`. A final default interpreter check
confirmed `.venv` remains **Python 3.12.16**; it was not replaced. Both checkpoints
were actually executed locally, not inferred from the unchanged CI matrix.
Prediction seam/base/input/job modules report **100%** coverage; output/provenance/
publication module reports **98%**. Existing skeleton success-rejection, health/
startup, all-core `-I -S` import isolation, offline guards, archive/API and fixture
inventory tests pass in both full checkpoints.

The new tests cover strict direct/codec/schema round trips and every required
exchange field; unsupported versions/types and unsafe canonical values; parameter
defaults/rules and precedence; exact NF-02/NF-03 inputs; alphabet/seed/resource
boundaries; declarative availability; all lifecycle state pairs, stale/fenced/expired
attempts, terminal/cancellation/retry history and competing proposals; samples/
ranks/maps/confidence and explicit absence; each missing required provenance section;
synthetic versus real conditional declarations; captured auxiliary input/dirty patch
bytes; missing/corrupt/mismatched inventories, references, rights and artifact
lineage. Helpers contain authored metadata/byte placeholders, never molecular
predictions or weights. All new standalone/source-backed fixtures are inventoried;
existing frozen fixture bytes and socket/DNS guards are unchanged.

Additional offline command from `backend/`:
`uv run --locked python tests/contract_exchange.py` **passed**, producing all nine
actual biological route/service/parser/archive response groups. No new producer
uses this exchange. It also passes through the existing frontend guarded child.
`uv run --locked python scripts/prediction_schema.py` ran successfully and its
checked-in output reproducibility is tested in the full suites.

From `frontend/`, under Node v24.5.0:

```sh
npm ci --cache /tmp/neurofold-npm-cache --offline
npm run lint
npm run typecheck
npm run build
npm run test
```

All passed: locked install added 268 packages/audited 269; **4 test files / 36 tests
passed**, 0 failures. No frontend or dependency/lockfile changes. `git diff --check`
passed after final documentation/inventory review.

## Unexecuted checks and remaining gates

No infrastructure changed. Browser/live-provider/container investigations were not
repeated, as authorized for contract-only work. Carry forward the exact
[NF-03 M3 gap](nf03-m3-evidence.md): Compose configuration passed at that checkpoint,
but its stopped Docker daemon prevented builds/smoke tests. **Container build/smoke
execution remains unverified at this checkpoint.** No historical check is presented
as newly executed; no current daemon availability is inferred. Close the gap when
execution infrastructure changes. Pure contract design is not blocked by it.

Only NF-04 M1 is complete. M2 owns durable SQLite/idempotency, transactional final
fencing/publication, isolated supervision and HTTP; M3 owns executable synthetic
inference and its vertical slice; M4 owns reviewed pinned real software/weights/
licenses/MSA and measured hardware limits; M5 owns Boltz-2 integration and reviewed
real reference/variant runs. NF-08 capture/export/audit and independent scientific
acceptance remain open. [Scientific review](scientific-review.md) is required before
the relevant real prediction/comparison acceptance gates; these software tests
cannot supply that approval. Shared seeds do not imply GPU determinism, causal
mutation effects, pathogenicity, disease mechanism, clinical utility or biological
accuracy.
