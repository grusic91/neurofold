# NF-08 — Reproducibility and Export

Status: M1 implemented; M2–M4 proposed. M1 is an early prerequisite, not
end-of-epic cleanup. Contracts and decisions:
[Shared provenance contracts](../provenance-contracts.md). Parent:
[NF-EPIC-001](../EPIC.md).

## 1. Objective and scientific motivation

Make every scientific result traceable to immutable inputs, source evidence,
execution conditions and comparison definitions. Export a self-describing research
record that can be inspected and integrity-checked offline. Distinguish the ability
to audit a run, rerun it, and obtain numerically identical results.

## 2. Scope and non-goals

Define versioned source/artifact/manifest schemas and hashes before scientific
features write data; capture provenance throughout NF-02–06; provide verified
exports with raw outputs, sequence definitions and comparison reports where
redistribution is permitted. Include software/hardware metadata, licenses,
uncertainty, privacy and retention rules.

Exclude a public data repository, cloud storage requirement, user accounts,
electronic lab notebook, cryptographic authenticity/signature service, public
sequence upload, guaranteed GPU determinism and redistribution of model weights.
A checksum detects changed bytes; it does not prove authorship or scientific truth.

## 3. Dependencies

- **M1 depends only on NF-01.** Agree canonicalization, evidence kinds, source
  receipts, artifact descriptors, manifest skeletons and compatibility policy
  before NF-02/03 content-addressed writes or NF-04 job submission.
- Source capture is implemented alongside NF-02/03, execution capture with NF-04,
  and comparison capture with NF-06. Each task owns its producer and tests.
- Final export requires these producers and repositories; NF-05/07 provide
  optional display state and the user-facing export controls. NF-09 verifies
  offline interpretation and replay documentation.

## 4. Proposed architecture and interfaces

Core contains frozen manifest records, schema version constants, hash/
canonicalization rules and `ArtifactStore`/manifest repository protocols, all
standard-library-only. API owns transport schemas. The checked-in versioned JSON
Schema is a cross-language exchange artifact, not a core dependency on Pydantic.
M1 tests records against the schema and compatibility fixtures; API schemas and
frontend DTO contract tests accompany their future producers.

Application provenance builders compose receipts as work happens. They do not
guess missing metadata after execution. Storage adapters stage, checksum and
atomically publish immutable artifacts under ignored `data/`/`outputs/` roots.
Public artifact IDs resolve through a registry; never join a supplied HTTP path
to the filesystem. Root manifests reference registered content, not host-specific
absolute paths.

An application `ExportService` resolves a closed set of immutable records,
validates integrity/licenses, creates a bounded archive in a staging directory,
then registers it. Use streaming reads and a configurable size/time ceiling;
oversized requests fail explicitly instead of blocking indefinitely or omitting
files. Start without a separate export queue. A future large-export requirement
may use the existing job seam after an explicit contract change.

## 5. Data models and API contracts

### Canonicalization and identity, version 1

- Hash algorithm: SHA-256, represented by 64 lowercase hexadecimal characters;
  identify algorithm and encoding version in every descriptor.
- Sequence digest: hash ASCII bytes of the exact stored uppercase, single-line
  sequence without FASTA header or trailing newline. NF-02 records raw source
  bytes and its extraction/normalization separately. Do not discard or replace
  unsupported biological symbols merely to make model input acceptable.
- Raw artifacts: hash original unmodified file bytes. Parsed/normalized/aligned
  derivatives are new artifacts with parent hashes and transformation metadata.
- Canonical structured content: UTF-8 JSON with lexicographically sorted ASCII
  schema keys, compact `,`/`:` separators, no trailing newline, Unicode strings
  preserved without implicit normalization, duplicate keys forbidden, and no
  NaN/infinity. Use strings, booleans, null and integers; represent nonintegral
  settings as validated canonical decimal strings, avoiding cross-language float
  serialization in identities. Unordered collections have schema-defined sort
  order; ordered sequences/atom pairs retain their order. Explicitly include
  schema version and resolved defaults. This is NeuroFold canonical JSON v1,
  not an assertion of RFC 8785 compliance.
- Numerical result matrices/metrics may be JSON numbers in result artifacts;
  hash their exact stored bytes rather than recomputing them from reserialized
  browser objects. Record precision and tolerances separately.
- Content identity excludes presentation, receipt timestamps and local paths.
  An opaque reference ID identifies its immutable snapshot; variant/spec/
  comparison digests include the relevant snapshot IDs and content hashes.
  Keep source receipts separately so equal content never erases retrieval history.

### Manifest inventory

| Section | Required information |
| --- | --- |
| Header | schema/canonicalization version, record kind/ID, created UTC, producer version, status, evidence kind, warnings |
| Sources | provider, accession/isoform/taxon, entry/sequence versions, release/date, retrieval time/query, raw receipt hashes, license and citation references |
| Inputs | reference and variant records, raw/normalized sequence hashes, exact model input, preprocessing steps/order/versions, MSA/templates/constraints/auxiliary artifact hashes or explicit absence |
| Model | model family/release/source revision, adapter version/revision, weight filenames/URLs or stable identifiers, byte sizes, SHA-256, license/notices and acquisition instructions |
| Execution | job/attempt IDs, complete resolved parameters/defaults, explicit seed, stages/times, command argument vector, sampling/ranking/selection policy, exit outcome and known nondeterminism |
| Environment | code revision and dirty flag/patch hash when applicable, API and worker lockfile hashes and retained lock contents, Python/package versions, container image digest or explicit bare-environment description, OS/kernel/architecture, CPU, GPU model/count/VRAM, driver, CUDA/cuDNN/PyTorch and relevant library versions |
| Outputs | all raw model output files and logs where allowed, artifact IDs/hashes/sizes/media types, sample identifiers, coordinate format/units/conventions, confidence definitions/scales/units and token/residue maps |
| Comparison | ordered inputs, evidence/construct distinctions, method/library versions, sequence scoring/tie policy, mappings, exclusions, exact fit/evaluation sets, transforms/conventions, metric definitions/units/filters/tolerances |
| Interpretation | measured/experimental versus predicted versus synthetic labels, hypotheses, uncertainty, applicability limits, no disease-causality inference |
| Rights/privacy | per-artifact origin/license/attribution/redistribution status, outbound sequence disclosures, redactions/omissions and reasons, retention policy/version |

Use explicit unavailable/not-applicable values with reasons. A real successful
prediction may not lack required model, weight checksum/license, exact inputs,
parameters, code/lock identity or hardware/runtime provenance. Unknown required
values fail validation/publication. Optional platform fields may be unavailable
with a documented reason. Synthetic runs specify model/weights/GPU as not
applicable and still identify the fake adapter and software environment.

Capture failure/cancellation manifests too, retaining attempt outcome and available
diagnostics, but do not advertise partial coordinates as successful results.
Worker collection must not transmit credentials or unrelated environment variables;
use an allowlist for runtime metadata and redacted shareable logs.

### Export contracts and archive

| Method/path | Contract |
| --- | --- |
| `GET /v1/manifests/{manifest_id}` | 200 versioned manifest with checksum metadata; 404 unknown |
| `POST /v1/exports` | selected reference/variant/job/structure/comparison IDs and `include_display_state`; 201 export descriptor and `Location`; 404 unknown; 409 incomplete/integrity conflict; 413 configured archive bound; 422 inconsistent selection |
| `GET /v1/exports/{export_id}` | 200 inventory, omissions, archive checksum/size and download link; 404 unknown; 410 expired archive |
| `GET /v1/exports/{export_id}/download` | 200 ZIP bytes with checksum/size/media headers; 410 expired; no arbitrary file lookup |

Export descriptor completeness is `complete` or `partial` with enumerated omissions.
A partial export must retain enough metadata to explain/reacquire omitted inputs;
it must not claim full offline replay. Integrity failure is an error, not a partial
export workaround. Resolve selected records and their input/manifest dependencies
so the archive cannot contain a comparison detached from its exact inputs.

Proposed layout:

```text
manifest.json                 # versioned root inventory and provenance links
manifest.sha256               # checksum of manifest.json; not included in itself
records/                      # references, variants, jobs, source receipts
artifacts/<sha256>/...         # raw/derived permitted content and model input files
comparisons/                  # machine-readable results and readable reports
environment/                  # lockfiles, reviewed runtime metadata
licenses/                     # license inventory, notices, citations
README.md                     # verification, rerun prerequisites and limitations
```

Root inventory hashes each payload file; it does not hash itself or its checksum
sidecar, avoiding circular identity. The registered ZIP has its own external
checksum. Archive members use generated relative POSIX names, deterministic
ordering and normalized archive timestamps; no absolute paths, `..`, symlinks or
user-controlled filenames. Archives contain no weights by default. External
acquisition URLs/identifiers and checksums describe unavailable or nonredistributable
content explicitly. Verification checks inventory, path safety, sizes and hashes
without executing embedded code or unpickling model files.

## 6. Implementation milestones

1. **M1 — Early schema foundation:** agree records/JSON Schema, canonical vectors,
   hashes, artifact/source identity, evidence kinds, unknown-value rules and
   compatibility policy. Publish these contracts before NF-02 implementation.
2. **M2 — Capture/storage:** implement atomic artifact/manifest storage and source,
   variant and job provenance alongside the corresponding feature tasks. Add
   environment allowlisting and failure receipts before real execution.
3. **M3 — Comparison/export:** integrate NF-06 provenance, license-aware closure,
   bounded packaging, integrity verification, API and readable report generation.
4. **M4 — Independent audit/replay:** implement a documented offline verifier,
   demonstrate fake replay and real rerun prerequisites, test old schema reading
   and finalize retention/omission documentation with NF-09.

## 7. Acceptance criteria

- Source, prediction and comparison records resolve exact inputs and artifacts;
  a changed byte or unsupported schema is detected rather than silently accepted.
- Real successes meet all required scientific provenance fields; fake and failed
  runs are distinguishable and cannot pass as real successful predictions.
- A complete permitted export verifies offline without provider APIs or a model
  runtime, includes all returned samples and preserves raw outputs.
- Partial exports enumerate licensing/privacy/availability omissions and avoid
  full-replay claims. Weights/secrets/patient data are not bundled by default.
- An independent verifier can reproduce the reference-to-variant transformation
  and synthetic comparison using the exported definitions; real rerun instructions
  identify hardware, dependencies, weight acquisition and nondeterminism limits.

## 8. Automated testing requirements

Golden canonicalization vectors cover key order, defaults, decimal settings,
Unicode, integers versus booleans, unordered collections, duplicate keys and
forbidden nonfinite values; backend/frontend agree on vectors if both compute
identities. Use tiny synthetic files for hash corruption, atomic write failure,
missing parents, immutable duplicate writes and concurrent publication.

Validate required-field failures, optional absence reasons, failure manifests,
fake labels, code dirty-state metadata, environment/log secret redaction and
independent model/weight licenses. Export tests cover dependency closure,
per-file checksums, safe member names, byte/size bounds, all samples, omissions,
unknown versions, expiry, tampering and interrupted packaging. Verify a completed
archive offline with no source adapters. Rerun a fake job and analytic comparison
using exported definitions, not implementation-mirroring assertions.

## 9. Scientific validity and reproducibility

An input hash proves identity of the stored bytes; it does not identify preprocessing
unless that transformation is recorded. A fixed seed alone does not establish
determinism. Record relevant hardware/libraries, known nondeterministic operations,
and justified tolerances; distinguish exact replay from scientific comparability.

Never overwrite raw observations or predicted structures with aligned/processed
versions. Record units, coordinate frames, confidence definitions, transformations
and sample/selection choices. Licenses for source annotations, coordinates, model
code, weights, MSA databases and auxiliary artifacts are separate. Review current
[RCSB usage terms](https://www.rcsb.org/pages/usage-policy), UniProt terms and exact
model-artifact notices; the repository license does not relicense them.

MVP uses public data, but provenance/logs can still reveal local paths or user
identifiers. Store full permitted scientific artifacts locally, emit reviewed
shareable metadata, and record any redaction as a derivative/omission rather than
silently altering the original. Never commit scientific outputs or real data to Git.

## 10. Risks and unresolved decisions

- **Schema migration:** start with `neurofold-research/1`; readers reject unknown
  major versions and tolerate documented optional additions only. Migration creates
  a new derived record linked to the original; it never rewrites history.
- **Retention:** proposed local cache/artifact cleanup is manual by default until
  an operator policy is configured. Active jobs/exports and referenced inputs
  cannot be deleted; expired export archives return 410 without deleting the
  immutable underlying scientific records. Record policy and deletion receipts.
- **Redistribution:** unresolved rights require explicit metadata-only omission
  or block complete export. Weight acquisition and MSA retention need review before
  real release; do not infer permission from a model's code license.
- **Size/performance:** set archive limits from measurement in M3. A future large
  dataset requirement may justify async packaging/storage adapters, not early
  deployment infrastructure.
