# NF-03 — Protein Variant Management

Status: proposed. Parent: [NF-EPIC-001](../EPIC.md).

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

## 4. Proposed architecture and interfaces

Use frozen standard-library dataclasses in `core/variants.py` and pure functions
`parse_substitution(notation)`, `validate_substitution(reference, substitution)`,
`apply_substitution(reference, substitution)`, and `sequence_difference(...)`.
Return typed domain errors; no HTTP exceptions or source fetches in core.

An application `VariantService` loads the immutable reference through its
repository, validates and constructs the variant, then atomically writes a
content-addressed record through an injected `VariantRepository`. The filesystem
adapter stores records under ignored `data/`; fake repositories support tests.
API handlers perform schema conversion only. No new database or queue is needed.

## 5. Data models and API contracts

`Substitution`: `reference_aa`, `position` (integer), `alternate_aa`,
`notation_version="nf-substitution/1"`. Accept the twenty standard amino acids
`ACDEFGHIKLMNPQRSTVWY`. For this MVP, strict ASCII uppercase notation matches
`^([ACDEFGHIKLMNPQRSTVWY])([1-9][0-9]*)([ACDEFGHIKLMNPQRSTVWY])$`.
Reject whitespace, lowercase, leading zeros, signs, decimal positions and Unicode
lookalikes with actionable 422 errors. Do not silently reinterpret notation.

Validation order:

1. Parse syntax with a bounded notation length; reject noncanonical symbols.
2. Require `1 <= position <= len(reference.sequence)`.
3. Require reference residue at Python index `position - 1` to equal `reference_aa`.
4. Require `reference_aa != alternate_aa`.
5. Construct `reference[:position-1] + alternate_aa + reference[position:]`.
   Assert unchanged length and exactly one differing position before persisting.

Reference snapshots containing noncanonical residues remain inspectable, but MVP
variant creation returns `UNSUPPORTED_REFERENCE_ALPHABET` with affected positions;
it does not replace unknown residues. Document this conservative restriction.

`VariantDefinition` includes schema version, content-derived variant ID,
reference ID/accession/taxon/sequence version/hash, the structured substitution,
canonical notation, mutated sequence/hash, sequence length and interpretation kind
`hypothesis` for the proposed substitution. This interpretation is separate from
the shared `experimental`/`predicted`/`synthetic` evidence kinds of structure
artifacts. Creation time belongs in an append-only receipt, outside content
identity. It is not an annotation of clinical evidence.

Variant ID = SHA-256 of NF-08 canonical JSON containing `schema_version`,
`reference_id`, `reference_sequence_sha256`, and the structured substitution.
The mutated sequence is derived and independently hashed/verified on load. Two
reference records with identical sequences but different source identity may
produce different variant IDs. Sequence hashes permit content comparisons without
discarding source provenance. Repeating an identical create is idempotent.

Proposed routes:

| Method/path | Input | Result |
| --- | --- | --- |
| `POST /v1/variants` | `{reference_id, expected_reference_sha256, notation}` | 201 record and `Location` on first creation; 200 same record on duplicate |
| `GET /v1/variants/{variant_id}` | content ID | 200 immutable record and difference; 404 unknown |

Example request: `{ "reference_id": "ref-example", "expected_reference_sha256":
"<64 lowercase hex characters>", "notation": "A4V" }`. For the explicitly
synthetic reference `MACAG`, the mutated sequence is `MACVG`, and the difference
is `{position: 4, reference_aa: "A", alternate_aa: "V"}`. Placeholder hashes/IDs
are illustrative, not actual stored records.

Errors follow the epic envelope: 404 `REFERENCE_NOT_FOUND`; 409
`REFERENCE_HASH_MISMATCH`; 422 `INVALID_NOTATION`, `POSITION_OUT_OF_RANGE`,
`REFERENCE_MISMATCH`, `NO_OP_SUBSTITUTION`, or `UNSUPPORTED_REFERENCE_ALPHABET`.
Reference mismatch details include expected/observed residue and the 1-based
position. No `PATCH` endpoint: editing creates a new definition. Do not persist
invalid records, partially mutated sequences or silently refreshed references.

## 6. Implementation milestones

1. **M1 — Pure domain:** records, syntax/position/alphabet validation, construction,
   difference output, error codes and synthetic tests.
2. **M2 — Identity/storage:** canonical content identity, atomic immutable writes,
   integrity verification, duplicate semantics and reference linkage.
3. **M3 — HTTP integration:** request/response schemas, routes, OpenAPI examples,
   and frontend-ready difference records; document notation and indexing.

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
author numbering or processing event. A familiar disease-associated notation may
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
