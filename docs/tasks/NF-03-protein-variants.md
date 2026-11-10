# NF-03 — Protein Variant Management

Status: **M1, M2 and M3 implemented**; frontend interaction and scientific
acceptance remain separate gates.
Parent: [NF-EPIC-001](../EPIC.md). See [domain/storage decisions](../variants.md),
[M1 evidence](../testing/nf03-m1-evidence.md),
[M2 evidence](../testing/nf03-m2-evidence.md) and
[M3 executed evidence](../testing/nf03-m3-evidence.md).

## 1. Objective and scientific motivation

Define an amino acid substitution against an immutable reference sequence and
produce an exact mutated sequence for downstream prediction. A notation such as
`A4V` is meaningful only with a particular sequence and numbering convention;
validation prevents accidentally studying a different residue or isoform.

## 2. Scope and non-goals

Support one canonical amino acid substitution per variant, notation parsing,
1-based reference-position validation, deterministic sequence construction,
reference/variant sequence comparison and immutable storage. Retain the original
reference and display the single changed position.

Exclude indels, stop-gains, synonymous changes, ambiguous amino acids, multiple
substitutions, genomic/transcript coordinate conversion, isoform editing, HGVS
conversion, population/clinical annotation and pathogenicity interpretation.
`A4V` is NeuroFold's compact protein notation; do not advertise full HGVS compliance.

## 3. Dependencies

- [NF-02](NF-02-biological-data.md) supplies pinned `ReferenceSnapshot` records.
- [NF-08 M1](NF-08-reproducibility.md) supplies canonical encoding/hash contracts.
- NF-04 consumes the constructed sequence; NF-05/06 use the same reference
  positions. This task must not depend on prediction or a molecular viewer.

## 4. Architecture and interfaces

Use frozen standard-library dataclasses in `core/variants.py` and pure functions
`parse_substitution(notation)`, `validate_substitution(reference, substitution)`,
`apply_substitution(reference, substitution)`, and `sequence_difference(...)`.
Return typed domain errors; no HTTP exceptions or source fetches in core.

In M2, the application `VariantService` loads the immutable reference through
its repository, validates and constructs the variant, then atomically writes a
content-addressed record through an injected `VariantRepository`. The filesystem
adapter stores records under ignored `data/`; fake repositories support tests.
API handlers perform schema conversion only. No new database or queue is needed.

## 5. Data models and API contracts

`Substitution`: `reference_aa`, `position` (integer), `alternate_aa`,
`notation_version="nf-substitution/1"`. Accept the twenty standard amino acids
`ACDEFGHIKLMNPQRSTVWY`. For this MVP, strict ASCII uppercase notation matches
`^([ACDEFGHIKLMNPQRSTVWY])([1-9][0-9]*)([ACDEFGHIKLMNPQRSTVWY])$`.
Reject whitespace, lowercase, leading zeros, signs, decimal positions and Unicode
lookalikes. M1 raises typed domain errors; M3 translates them to actionable
422 responses. Do not silently reinterpret notation. Use full-string matching,
including rejection of trailing newlines. Bound input to 18 characters before
integer conversion; positions must be exact positive integers through NF-08's
maximum safe integer, 9007199254740991. Bool and implicit conversions are rejected
by direct construction and supported codecs as well as notation parsing.

Validation order:

1. Parse syntax with a bounded notation length; reject noncanonical symbols.
2. Check the entire pinned `reference.protein.sequence` for noncanonical residues.
   Unsupported alphabet takes precedence over bounds, mismatch and no-op checks;
   report every affected 1-based position/symbol in increasing order.
3. Require `1 <= position <= len(reference.protein.sequence)`.
4. Require reference residue at Python index `position - 1` to equal `reference_aa`.
5. Require `reference_aa != alternate_aa` (mismatch takes precedence over no-op).
6. Construct `reference[:position-1] + alternate_aa + reference[position:]`.
   Assert unchanged length and exactly one differing position before persisting.

Reference snapshots containing noncanonical residues remain inspectable, but MVP
variant creation returns `UNSUPPORTED_REFERENCE_ALPHABET` with affected positions;
it does not replace unknown residues. Document this conservative restriction.

M1 returns a frozen `SubstitutionResult` retaining the complete pinned snapshot,
substitution, exact sequence and its NF-08 sequence hash, an ordered immutable
difference tuple and `interpretation_kind="hypothesis"`. It has no variant ID or
persisted schema. `sequence_difference` returns zero/all exact differences for
equal-length strings and fails explicitly on unequal lengths; applying a
substitution separately enforces exactly one requested change. See the
[domain guide](../variants.md) for signatures, strict codecs and additional narrow
input/difference/result failure codes.

The implemented M2 `VariantDefinition` includes schema version, content-derived
variant ID, reference ID/accession/taxon/sequence version/hash, the substitution,
canonical notation, mutated sequence/hash, sequence length and interpretation kind
`hypothesis` for the proposed substitution. This interpretation is separate from
the shared `experimental`/`predicted`/`synthetic` evidence kinds of structure
artifacts. M2 records no creation time; any future creation time belongs in an
append-only receipt, outside content identity. It is not an annotation of clinical evidence.

Variant ID = SHA-256 of NF-08 canonical JSON containing `schema_version`,
`reference_id`, `reference_sequence_sha256`, and the structured substitution.
The mutated sequence is derived and independently hashed/verified on load. Two
reference records with identical sequences but different source identity may
produce different variant IDs. Sequence hashes permit content comparisons without
discarding source provenance. Repeating an identical create is idempotent.

M2 uses schema version `neurofold-variant/1` and ID `variant-<64 lowercase hex>`.
The [domain/storage guide](../variants.md) specifies exact canonical bytes,
retained fields, injected public interfaces, input/hash/reference/M1 error
precedence, concurrency outcomes, archive verification and interruption limits.
M2 added no HTTP contract or migration of frozen NF-02/NF-08 v1 records.
M3 now projects the complete versioned definition without changing persisted bytes.

Implemented M3 routes:

| Method/path | Input | Result |
| --- | --- | --- |
| `POST /v1/variants` | `{reference_id, expected_reference_sha256, notation}` | 201 record and `Location` on first creation; 200 same record on duplicate |
| `GET /v1/variants/{variant_id}` | content ID | 200 immutable record and difference; 404 unknown |

The [HTTP contract guide](../variants.md#m3-http-contract) documents strict field
schemas, full exact authored MACAG/A4V/MACVG request/response examples and accurate
IDs/hashes. Every response field is required. Both POST outcomes provide the same
usable GET Location; conversion/serialization runs inside the admitted worker.
HTTP schema validation precedes unchanged deterministic M2/M1 validation.

M3 errors follow the epic envelope: 404 `REFERENCE_NOT_FOUND`; 409
`REFERENCE_HASH_MISMATCH`; 422 `INVALID_NOTATION`, `POSITION_OUT_OF_RANGE`,
`REFERENCE_MISMATCH`, `NO_OP_SUBSTITUTION`, or `UNSUPPORTED_REFERENCE_ALPHABET`.
M1 reference mismatch details explicitly name `requested_reference_aa`,
`actual_reference_aa` and the 1-based `position`; M3 owns HTTP translation.
Unknown variants use 404 `NOT_FOUND`; missing/corrupt dependencies of retained
variants use 500 `ARCHIVE_INTEGRITY`. Publication conflict is 409
`ARCHIVE_CONFLICT`; publication I/O failure is nonretryable 503
`ARCHIVE_PUBLICATION_FAILED`, with uncertain-outcome details and an already known
recovery ID/URL. Mutating 504 timeout and caller cancellation may leave work
running and publication can finish later. Never claim rollback/absence or retry
automatically: verify a known ID or deliberately repeat the identical request.
Existing 429 admission, 16 KiB boundary, request IDs and error envelopes apply.
See the guide for the complete mapping and precedence.
No `PATCH` endpoint: unsupported methods return 405 `HTTP_ERROR` with `Allow`.
Editing creates a new definition. Do not persist
invalid records, partially mutated sequences or silently refreshed references.

## 6. Implementation milestones

1. **M1 — Pure domain (complete):** records, syntax/position/alphabet validation,
   construction, difference output, error codes and synthetic tests.
2. **M2 — Identity/storage (complete):** canonical content identity, atomic
   immutable writes, integrity verification, duplicate semantics and reference linkage.
3. **M3 — HTTP integration (complete):** request/response schemas, routes, OpenAPI examples,
   and frontend-ready difference records; document notation and indexing. Lazy
   shared archive composition and existing bounded-worker accounting are verified
   with production offline routes, deterministic concurrent publication, integrity
   damage, I/O phases, timeout/cancellation, late recovery and shutdown draining.
   Python 3.12/3.13 full checkpoints are executed in the linked M3 evidence.
   NF-07 interaction, prediction/comparison/export and scientific acceptance remain open.

## 7. Acceptance criteria

- `A4V` applied to synthetic `MACAG` yields `MACVG` with one exact difference.
- First/last valid positions work; zero, overflow and wrong reference residues
  fail without writing records. The reference object and source bytes are unchanged.
- Every accepted variant is tied to a resolvable immutable reference and exact
  source/mutated sequence hashes. Duplicate creation has documented stable identity.
- Loading a variant verifies its derived sequence/hash and reports integrity
  failure rather than correcting or hiding corrupt data.
- Public schemas distinguish user notation, structured substitution and numbering;
  frontend consumers need not infer a position from a human-readable string.

## 8. Automated testing requirements

Table-driven pure tests cover each standard residue, boundary positions, all
validation failures, empty/oversized strings, illegal amino acid symbols,
lowercase/whitespace, leading zeros, Unicode and noninteger payloads. Test exact
one-change/length invariants across small generated synthetic sequences without
adding a property-testing dependency unless justified.

Repository tests cover stable identity, differing references, duplicate requests,
concurrent duplicate writes, corruption and failed writes. API tests assert
201/200/404/409/422 contracts, `Location`, error details, rejected unknown fields
and unsupported update methods. No network, GPU or source-database dependency.
Core still imports without third-party packages. NF-07 supplies interaction tests
for preview/error display and confirmation of the inspected reference.

## 9. Scientific validity and reproducibility

Number positions against the entire pinned canonical sequence, including its
initial methionine. Do not renumber to match a publication, mature peptide, PDB
author/label numbering, coordinate count, alignment or processing event. No
structure/map is required; unknown/absent coordinates do not remove reference
positions. A familiar disease-associated notation may
use a different convention: the UI must show the actual reference residue and
nearby sequence, and explain a mismatch rather than force acceptance.

A variant definition is a sequence hypothesis, not evidence of disease effect.
Keep source sequence versions and original reference intact; record preprocessing
and normalization in NF-08. Coordinate highlighting later requires NF-02/06 maps;
sequence position alone cannot locate an atom in an experimental structure.

## 10. Risks and unresolved decisions

- **Historical naming:** publication variants may not align to canonical
  numbering. MVP requires explicit correction against the selected reference;
  future alias support needs a separate traceable mapping feature.
- **Nonstandard residues:** MVP rejects variant creation for references outside
  the twenty-letter alphabet; later model-specific support requires capability
  negotiation and new validation tests.
- **Content evolution:** a future multi-substitution or isoform schema needs a
  new version and migration policy. Existing definitions must remain unchanged.
- **Record retention:** references cannot be removed while variants/jobs/export
  records depend on them; NF-08 defines the operator-facing retention policy.
