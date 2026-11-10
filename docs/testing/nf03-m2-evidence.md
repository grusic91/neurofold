# NF-03 M2 — Identity/storage evidence

Date: 2026-11-10. Implementing-agent software validation on macOS ARM64,
Python 3.12.16, uv 0.13.7, Node 24.5.0 and npm 11.5.1. Initial working tree was
clean at `20e00e93eb5e24d5052614b3238cc920ad981634`, with M1 already present.
**M1/M2 complete for offline substitution/identity/storage software; M3 HTTP and
independent scientific acceptance remain incomplete.** All changes remain
uncommitted for review.

## Implemented contract and boundaries

[The domain/storage guide](../variants.md) records the exact identity decision,
persisted fields, public signatures, deterministic failures, archive verification,
concurrent duplicates, atomicity limits and future receipt policy. The identity
section was written before dependent implementation.

- `core/variants.py`: additive frozen `VariantDefinition` with strict version
  `neurofold-variant/1`, `variant_identity_document`, `define_variant`, transient
  `VariantPublication(definition, created)` and narrow `VariantRepository`.
  M1 parsing/validation/application/difference behavior and records are preserved.
- `application/variants.py::VariantService(references, variants)`:
  `create(reference_id, expected_reference_sha256, notation)` and
  `get(variant_id)`, using injected retained repositories only. No catalog,
  source refresh, HTTP translation, clock or inference is introduced.
- `adapters/variant_storage.py::FilesystemVariants(store, references)`:
  strict checksummed bundles, complete derivation/reference validation, immutable
  atomic publication and explicit duplicate/integrity/conflict/I/O outcomes.
- Existing archive `_publish` now returns whether its atomic no-clobber link
  won. Existing NF-02 callers ignore this private additive return; their public
  contracts, archive encoding and publication mechanism are unchanged.

The variant ID is exactly `variant-` plus lowercase hexadecimal SHA-256 of NF-08
canonical JSON containing only `schema_version`, `reference_id`,
`reference_sequence_sha256` and every structured M1 substitution field, including
`notation_version="nf-substitution/1"`. No ScientificInput/other identity envelope
is added. The independent inline golden document uses the synthetic pinned ID
`synthetic-variant-reference`, exact `MACAG` sequence hash
`c88582ee0f845de56779787b8447097ae3330a816d1656b2808e0d439206226e`, and `A4V`.
Its independently calculated expected variant ID is
`variant-4f0a7366f1a3a152596ba4337b0f2050b7b06e70640cc77ef54aafa84143f165`.

Exact `sequence-ascii/1` content hashes remain separate from reference-aware
variant IDs, canonical definition checksums and raw bundle/artifact byte hashes.
The definition also retains the full snapshot's canonical hash and repeated
accession/taxon/sequence and entry versions, independently checked against the
resolved snapshot; these fields do not enter the four-field variant identity.
M2 stores no creation timestamps/receipts. Any future creation receipt must be
separate and append-only; duplicate requests never mutate a definition.

Creation precedence is ID representation → expected-hash representation → M1
notation syntax → reference resolution → expected-hash equality → unchanged M1
alphabet/bounds/reference-residue/no-op checks → publication. The additive typed
codes include `INVALID_EXPECTED_REFERENCE_HASH`, `REFERENCE_NOT_FOUND`,
`REFERENCE_HASH_MISMATCH` and `INVALID_VARIANT_DEFINITION`. Mismatch details name
`expected_reference_sha256` and `actual_reference_sha256`. No malformed/stale
request publishes a variant. Known corruption/unreadable retained dependencies
fail `ArchiveIntegrityError`; unknown variant IDs alone use repository `KeyError`.
A different valid retained definition raises `ArchiveConflict`; failed publication
I/O raises `ArchivePublicationError`. None of these interfaces assigns HTTP status.

## Offline synthetic behavior evidence

The final full suite includes **105 new M2 cases** in
`tests/test_variant_storage.py` and all **559 unchanged M1 cases**:

- Authored `MACAG` / `A4V` / `MACVG`, exact independent canonical identity bytes
  and expected ID, sequence/hash/length/difference/interpretation and strict
  definition round trips, frozen records and byte-identical original source,
  receipt, audit and snapshot preservation.
- Equal sequences under different pinned IDs retain equal sequence hashes but
  distinct variant IDs. Different substitutions/reference sequences change IDs.
  Independent repositories with different snapshot capture times demonstrate
  that capture metadata stays outside variant identity; creation time/receipts
  are absent from the strict persisted contract.
- Input representation/error precedence, malformed hash types/strings, unknown
  references and stale expected hashes without publication; unchanged M1 error
  codes/details; injected repository conflict/integrity failures propagate.
- Sequential duplicate identity and retained offline reopening. Four independent
  repository instances synchronize at `os.link` using a barrier; exactly one
  wins. Two independent Python processes both report fully staged records before
  the parent releases either link; exactly one reports `created=True`. No
  timing-only race assertion is used. Children deny sockets/DNS and use `-I -S`.
- Valid conflicting content is exercised with an explicitly injected synthetic
  digest collision; bytes remain unchanged. Both valid and corrupt racing
  targets are classified without clobbering; corrupt duplicates never succeed.
- Injected stage creation, partial stage write, file fsync, link and directory
  fsync failures. Abrupt subprocess exits immediately before/after link leave
  only an ignored stage or a complete independently verifiable final record.
  Restart/retry succeeds idempotently and never treats a stage as a variant.
- Truncation, invalid UTF-8/JSON, duplicate keys, invalid envelopes/checksums,
  missing/unknown fields, unknown versions, wrong types/IDs and oversized,
  symlink/directory records. Deliberate checksum-recomputed tampering covers
  reference IDs/hashes/accession/taxon/versions, notation/substitution, sequence,
  length/hash, differences and interpretation. Recomputed sequence checksum and
  recomputed substitution identity still cannot evade exact M1 derivation and
  actual reference residue checks.
- Missing, malformed and unreadable retained reference, pin, source receipt and
  raw artifact dependencies fail integrity; archives are never repaired.
  Existing core import-isolation coverage discovers every core module in a
  `python -I -S` subprocess without site-packages.

[Fixture inventory](fixtures.json) adds `variant-storage-inline`, with authorship,
Apache-2.0 license, synthetic designation, construction, units/coordinate absence,
source size/hash and expected invariants. Existing source-backed M1 fixture and
frozen NF-02/NF-08 fixture bytes are unchanged. No live artifacts were read.

Atomicity relies on the existing private local filesystem root and same-directory
hard-link/fsync semantics. Before the link no partial final exists; ordinary
failures clean stages, while abrupt exits may leave ignored orphan stages. After
the link an error/exit may leave a complete record despite caller uncertainty;
reopen and verify, never overwrite/delete to retry. These are process-interruption
checks, not power-loss, network filesystem or distributed transaction evidence.
References must remain immutable and retained; M2 adds no garbage collection or
repair policy.

## Executed checks

| Check | Actual result |
| --- | --- |
| `uv sync --locked` | Pass; 45 packages resolved, 43 checked |
| `uv run --locked ruff check . ../infra/testing` | Pass; includes required backend check and existing CI script scope |
| `uv run --locked ruff format --check . ../infra/testing` | Pass; 58 files already formatted |
| `uv run --locked mypy src tests scripts ../infra/testing` | Pass; 58 source files including all new tests; strict configuration unchanged |
| `uv run --locked pytest` | **1,224 passed**, 24.38 seconds; **97.06%** total branch-enabled coverage, above 90% gate |
| New code coverage | `core/variants.py`, `application/variants.py` and `adapters/variant_storage.py`: **100%** statement/branch coverage |
| Core import isolation | Pass through full-suite `test_architecture.py`; every core module imported without site-packages |
| `npm ci --offline --cache /private/tmp/neurofold-npm-cache` | Pass; 268 packages installed from locked cached artifacts |
| `npm run lint` / `npm run typecheck` / `npm run build` | All pass; production bundle built |
| `git diff --check` | Pass |
| Compatibility diff | LICENSE, manifests/locks, frozen fixture/schema bytes and existing M1 test source unchanged |

Backend commands used `UV_CACHE_DIR=/private/tmp/neurofold-uv-cache`, preserving
the locked environment and the default Python 3.12 runtime. Existing CI already
runs these checks with locked installs (Python 3.12/3.13 and Node 24), discovering
the new tests automatically; no CI or dependency changes were required. No
hosted CI execution, new Python 3.13 run or additional platform acceptance is
claimed. All required checks for this milestone were available and passed.

## Compatibility and remaining gates

This is additive M2 behavior with no existing variant archive/API to migrate.
Application version remains 0.1.0; NF-02/NF-08 frozen v1 records/schemas and
Apache-2.0 attribution remain intact. No new dependency, HTTP schema/route,
frontend behavior, database, queue, model package or runtime was added.

M3 remains proposed: strict HTTP request/response DTOs, create/get routes,
201/200/Location duplicate behavior, error/status translation and OpenAPI
contracts. NF-07 interaction, viewer, prediction, comparison and exports remain
later work. No live-provider, browser or container investigation was repeated:
M2 stays offline and crosses none of those integration boundaries. Infrastructure
is unchanged; container configuration/build/smoke checks were outside this change.
Frontend behavior/browser suites were not rerun for the unchanged frontend.
Prior Linux ARM64 operational evidence and x86-64/broader-provider limitations
remain as recorded in [NF-02 operational evidence](nf02-operational-evidence.md).

[Scientific release gates](scientific-review.md) remain open: independent domain
review and panel approval; reviewed model/weight/data licenses; complete execution
provenance; measured Linux/NVIDIA limits, tolerances, replicates and known
nondeterminism; independent comparison/export verification. Synthetic storage and
sequence-hypothesis correctness establish no biological validity, disease effect,
prediction accuracy or scientific sign-off. No commit, push, publication or PR
was performed.
