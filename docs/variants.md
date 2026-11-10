# Protein substitutions and persisted variants — NF-03

## M2 identity decision

The persisted contract version is exactly `neurofold-variant/1`. Its variant ID
is `variant-` followed by the 64 lowercase hexadecimal SHA-256 digits of this
document encoded with NF-08 `neurofold-json/1` (no newline):

```json
{"reference_id":"<pinned ID>","reference_sequence_sha256":"<64 lowercase hex>","schema_version":"neurofold-variant/1","substitution":{"alternate_aa":"V","notation_version":"nf-substitution/1","position":4,"reference_aa":"A"}}
```

These are exactly the four identity fields; there is no outer identity envelope.
The substitution retains every validated M1 field. Sequence hashes use exact
`sequence-ascii/1` bytes. Different pinned IDs with equal sequences have equal
sequence hashes but different variant IDs. Archive bundle checksums and the
canonical hash of a complete definition are separate identities. Repeated metadata,
derived sequences, differences and interpretation are verified independently and
do not enter this identity document. M2 records no creation timestamp or receipt;
any future creation receipt must be append-only and separate from the definition.

M1 implements pure standard-library substitution logic in `core/variants.py`.
M2 adds immutable identity/storage through injected application repositories.
M3 adds strict offline HTTP integration below; frontend interaction and model
execution remain later work.

## Numbering and interpretation

Positions are **1-based against the complete pinned `reference.protein.sequence`**,
including its initial methionine. Structural coordinate counts, author/label
residue identifiers, mature peptides, publications and alignments never renumber
this sequence. Neither a structure nor a residue map is required. Missing or
unknown coordinates do not remove sequence positions. The independently authored
142-residue test reference is `M + ACDEFGHIKLMNPQRSTVWY * 7 + A`; position 142 is
valid even when a hypothetical structural polymer covers only 141 positions.

The result is a **sequence hypothesis**. It is not experimental/predicted
evidence, a disease-effect annotation or a claim of biological validity. Existing
source evidence/rights/provenance remain unchanged inside the pinned reference.

## Records and interfaces

- `Substitution(reference_aa, position, alternate_aa, notation_version)` is frozen,
  keyword-only, with default version `nf-substitution/1`. Its `notation` property
  gives compact NeuroFold notation, not full HGVS. A representable request can
  still be a no-op; reference-dependent validation rejects it in the order below.
- `parse_substitution(notation) -> Substitution` accepts only exact `str` values
  matching `([ACDEFGHIKLMNPQRSTVWY])([1-9][0-9]*)([ACDEFGHIKLMNPQRSTVWY])` using
  full-string matching. No stripping, uppercasing, coercion or reinterpretation.
  Position representation is 1 through **9007199254740991**, NF-08's maximum safe
  integer; bool is excluded. At most 18 notation characters (16 digits plus two
  residues) are allowed **before** integer conversion. Longer strings and shorter
  out-of-representation positions raise `INVALID_NOTATION`.
- `validate_substitution(reference, substitution) -> None` validates against an
  actual NF-02 `ReferenceSnapshot` and raises a typed failure without mutation.
- `apply_substitution(reference, substitution) -> SubstitutionResult` retains the
  **entire original snapshot** as `reference`, plus `substitution`, exact `sequence`,
  `sequence_hash` (`ContentHash`, `sequence-ascii/1`), immutable `differences` and
  `interpretation_kind="hypothesis"`. `sequence_length` is derived. Reference ID,
  accession/taxon, sequence hash, source receipt and versions are thus retained
  without inventing a second reference identity. Direct result construction also
  verifies the exact sequence, hash, one difference and interpretation.
- `sequence_difference(reference_sequence, alternate_sequence)` compares exact
  equal-length strings and returns a tuple of frozen `SequenceDifference` records
  (`position`, `reference_aa`, `alternate_aa`), ordered by increasing 1-based
  position. Identical sequences (including two empty strings) return `()`. Multiple
  differences are returned in full. Unequal lengths fail explicitly; no alignment
  or truncated `zip`. This comparison accepts noncanonical symbols and does not
  authorize variant creation. Strings must be representable in canonical UTF-8.

The records follow core's strict `to_dict`/`to_json`/`from_dict`/`from_json`
conventions, including explicit fields, exact types and rejection of unknown
fields/versions. The M1 records remain domain inspection/round-trip helpers, **not the persisted
`VariantDefinition`**. M2 adds the separate versioned definition below.
Sequence hashes remain distinct from canonical record hashes and variant IDs. Existing frozen NF-02/NF-08 schemas/fixtures are unchanged.

## Validation and deterministic failures

`VariantError(ValueError)` exposes a stable `VariantErrorCode` in `code`, a useful
message and a fresh `details` dictionary backed by immutable canonical data.
No HTTP status or envelope belongs here. Validation order is:

1. Parse/construct a representable substitution: exact canonical single residue
   symbols, exact positive safe integer and supported notation version. Invalid
   syntax/types/representation/codec inputs give `INVALID_NOTATION`.
2. Require exact reference/substitution domain types (`INVALID_VARIANT_INPUT`).
3. Inspect the **entire reference alphabet**, before position or residue checks.
   `UNSUPPORTED_REFERENCE_ALPHABET` details contain `affected_residues`, each
   `{position, symbol}` in increasing 1-based order, including repeats. Any residue
   outside `ACDEFGHIKLMNPQRSTVWY`, even away from the substitution, prevents creation.
   The original snapshot remains inspectable; nothing is replaced or normalized.
4. Require `position <= len(reference.protein.sequence)`;
   `POSITION_OUT_OF_RANGE` gives `position` and `reference_length`.
5. Require the requested `reference_aa` to match the actual pinned residue;
   `REFERENCE_MISMATCH` gives `position`, `requested_reference_aa`, and
   `actual_reference_aa`. Mismatch takes precedence over a no-op request.
6. Reject equal reference/alternate residues with `NO_OP_SUBSTITUTION`, including
   the position and both requested symbols in details.
7. Construct exactly `reference[:position-1] + alternate_aa + reference[position:]`.
   Verify unchanged length and exactly one requested difference, then use the
   existing `sequence_sha256` helper for the derived sequence hash.

Additional narrow failures: `INVALID_DIFFERENCE_INPUT` covers wrong comparison
types, invalid difference records and non-UTF-8 strings;
`SEQUENCE_LENGTH_MISMATCH` includes both lengths; `INVALID_VARIANT_RESULT` covers
inconsistent manually constructed/decoded result fields. Result validation first
validates field types and then the substitution/reference, before checking derived
fields. `REFERENCE_NOT_FOUND` and `REFERENCE_HASH_MISMATCH` belong to the M2 application
workflow below; they do not change M1 failures.

Synthetic `MACAG` / `A4V` yields `MACVG` and exactly
`SequenceDifference(position=4, reference_aa="A", alternate_aa="V")`.
See [M1 evidence](testing/nf03-m1-evidence.md) and the
[scientific release gates](testing/scientific-review.md) for checks and limits.


## M2 persisted contract and public interfaces

`core/variants.py` adds frozen, keyword-only `VariantDefinition`, with strict
`to_dict`/`to_json`/`from_dict`/`from_json` codecs. Every wire field is required,
including constructor defaults; unknown/missing fields, versions, invalid exact
types (including booleans used as integers), and internal invariants fail.
`SubstitutionResult` and the frozen NF-02/NF-08 v1 schemas/fixtures are unchanged.

| Definition fields | Meaning and verification |
| --- | --- |
| `schema_version`, `variant_id` | Version above and recomputed four-field identity |
| `reference_id`, `reference_sequence_sha256` | Actual retained pin and exact NF-08 sequence digest |
| `reference_content_hash` | NF-08 canonical hash of the complete snapshot, independently retaining all source metadata/provenance; outside variant identity |
| `reference_accession`, `reference_taxon_id` | Repeated accession and exact positive taxon integer from the snapshot |
| `reference_sequence_version`, `reference_entry_version` | Exact NF-08 Metadata from the pinned source receipt, including explicit absence |
| `substitution`, `notation` | All M1 structured fields and identical canonical compact notation |
| `sequence`, `sequence_hash`, `sequence_length` | Exact M1-derived sequence, `ContentHash` using `sequence-ascii/1`, exact integer length |
| `differences`, `interpretation_kind` | Exact immutable one-change tuple and literal `hypothesis` |

`variant_identity_document(reference_id=..., reference_sequence_sha256=...,
substitution=...) -> CanonicalObject` exposes the precise identity bytes.
`define_variant(reference, substitution) -> VariantDefinition` uses unchanged M1
validation/construction. Standalone definitions validate identity and internal
invariants; `definition.validate_reference(reference)` additionally derives and
compares **every field** against the actual snapshot. Standalone decoding alone
cannot certify a reference dependency.

`VariantRepository.get(variant_id) -> VariantDefinition` loads verified records;
`publish(definition) -> VariantPublication` validates the complete definition and
reference before writing. Frozen transient `VariantPublication(definition,
created)` reports whether this call won publication. It is never archived.
`application/variants.py::VariantService(references, variants)` accepts an injected
NF-02 `ReferenceRepository` and this narrow `VariantRepository`:

```python
outcome = service.create(reference_id, expected_reference_sha256, notation)
definition = outcome.definition
same = service.get(definition.variant_id)
```

`adapters/variant_storage.py::FilesystemVariants(store, references)` implements
the variant protocol over `FilesystemStore` and an injected reference repository.
Typical offline composition uses the same `FilesystemStore` for references and
variant bytes under ignored `data/`. No provider/catalog, clock or source refresh
is available to this service. The reference repository must return immutable,
verified snapshots. Retain dependencies for the lifetime of their variants.

## M2 creation precedence and failures

Creation has deterministic precedence, stopping without variant publication:

1. Exact nonblank UTF-8 `reference_id` string: `INVALID_VARIANT_INPUT`; no coercion.
2. Exact 64 lowercase hex `expected_reference_sha256` string:
   `INVALID_EXPECTED_REFERENCE_HASH`; no stripping, uppercasing or conversion.
3. M1 bounded notation parsing: `INVALID_NOTATION`.
4. Resolve the requested immutable reference: `REFERENCE_NOT_FOUND` with
   `reference_id` details only for an absent pin. Known reference/archive damage
   propagates as `ArchiveIntegrityError`, never absence. A repository returning
   another ID is also an integrity failure.
5. Compare expected hash against `reference.protein.sequence_hash`:
   `REFERENCE_HASH_MISMATCH` details name `expected_reference_sha256` and
   `actual_reference_sha256` unambiguously.
6. Apply M1 alphabet → bounds → reference residue → no-op checks with unchanged
   codes/details and full pinned numbering, then derive/validate the definition.
7. Publish through the variant repository. Duplicates return the retained record
   and `created=False`; the winning write returns `created=True`.

New definition/identity invariant failures use `VariantError` with
`INVALID_VARIANT_DEFINITION`. Storage reads translate codec/derivation violations
to existing `ArchiveIntegrityError`. Existing `ArchiveConflict` means a valid
identifier is already bound to different content (including a hypothetical digest
collision). Corrupt targets fail integrity before duplicate/conflict success.
`ArchivePublicationError(OSError)` identifies failed publication I/O; its cause is
retained. There are no HTTP status decisions in these interfaces.

## M2 archive atomicity and integrity

A variant uses the existing hashed-filename archive convention:
`variant-<SHA-256 of UTF-8 variant ID>.json`. The complete canonical bundle is
`{"record": <definition>, "sha256": <SHA-256 of canonical definition JSON>}`.
This checksum is neither the variant ID nor a checksum of the raw bundle bytes.
Raw artifact byte hashes, canonical record hashes and variant identities remain
separate; the four-field identity is never wrapped before hashing.

Publication validates the complete contract and actual reference first, writes
and flushes a private same-directory stage, fsyncs it, atomically hard-links it
to the final name without clobbering, and fsyncs the directory. The existing
private `_publish` primitive now returns a winner boolean; NF-02 public methods,
contracts and archive bytes are unchanged. Racing writers cannot replace a
retained record. Identical contenders converge on one definition and exactly one
winner. Race losers and sequential duplicates fully verify the retained record;
no checksum alone authorizes success. Different valid content raises conflict;
corrupt content raises integrity. Neither is overwritten or repaired.

Before the atomic link, failed writes expose no partial final record. Ordinary
exceptions remove their stage. Abrupt process exit can leave an orphan stage,
which is never read as a variant, even after reopening. M2 neither deletes these
stages nor implements garbage collection. A failure/exit **after** the link,
including directory fsync failure, can leave a complete visible record while the
caller receives an error/no response. Reopen and verify the ID to determine the
outcome; never delete or overwrite it to retry. Successful retry is idempotent.

These guarantees use local filesystem hard-link/fsync semantics and the existing
private archive root assumptions. Process restart tests do not prove power-loss
durability or correctness on network filesystems. There is no transaction with
external reference deletion, no distributed storage support and no automatic
repair. References must remain immutable and retained. Storage failures do not
roll back or modify source bytes, receipts or snapshots.

Every load strictly verifies envelope shape/checksum and contract version/types,
recomputes the prescribed identity and requested ID, resolves the actual retained
reference (including its source receipt, pin audit and raw artifact through the
reference repository), then independently repeats M1 and compares all retained
metadata, canonical notation, exact sequence, length, hashes, differences and
hypothesis interpretation. Missing top-level variants raise `KeyError`; missing
retained reference dependencies and damaged records raise `ArchiveIntegrityError`.
Invalid/truncated/oversized bundles, symlinks, unreadable final records and
self-consistent checksum tampering fail explicitly. Nothing is normalized,
rewritten or repaired on read.

See [M2 evidence](testing/nf03-m2-evidence.md) for storage checks and
[M3 evidence](testing/nf03-m3-evidence.md) for HTTP acceptance. M3 adds strict
DTOs/routes, 201/200 and Location behavior, typed errors and OpenAPI examples.
UI, predictions, comparisons and exports are later milestones. Independent biological review, reviewed model/weight/data
licenses, complete execution provenance, measured Linux/NVIDIA limits and
independent scientific/export validation remain open release gates. A stored
sequence hypothesis establishes no disease effect or prediction accuracy.

## M3 HTTP contract

`POST /v1/variants` accepts exactly three required strict strings:
`reference_id` (existing opaque ID convention, 1–128 ASCII identifier characters),
`expected_reference_sha256` (64 lowercase hexadecimal characters), and `notation`
(verbatim text). Unknown fields and coercion are rejected. HTTP representation
validation runs first; it returns 422 `INVALID_INPUT`, including malformed JSON,
invalid path IDs, duplicate JSON keys and missing fields. No normalization occurs.
Once admitted, service validation retains M2 precedence: ID/hash representation,
notation syntax, reference resolution, expected hash, then M1 alphabet, bounds,
reference residue and no-op. Reached typed domain codes/details remain intact.

The success body is a faithful strict projection of every `VariantDefinition`
field in the table above, with JSON arrays for differences. There is no HTTP
wrapper or new schema version. All fields, including nested versions and explicit
metadata absence, are required. Conversion, core invariants and serialization are
validated inside the admitted worker. Persisted bytes/identity remain unchanged.
Only `VariantPublication.created=True` returns 201; verified duplicates return
200 with the identical definition. Both return `Location: /v1/variants/{variant_id}`.
`GET` of this relative resource returns 200 after full repository verification on
every call, including reference dependencies and exact derivation. Clients using
a proxy resolve this path against their configured API base. No update endpoint
exists: unsupported methods return 405 `HTTP_ERROR` with `Allow`.

| Status | Code | Meaning/details |
| --- | --- | --- |
| 400 | INVALID_QUERY | Unknown/duplicate query parameters |
| 404 | REFERENCE_NOT_FOUND | Creation's pinned reference is absent; `reference_id` |
| 404 | NOT_FOUND | Requested variant itself is absent |
| 409 | REFERENCE_HASH_MISMATCH | `expected_reference_sha256`, `actual_reference_sha256` |
| 409 | ARCHIVE_CONFLICT | Valid immutable content conflict; no overwrite |
| 413 | SIZE_LIMIT | Existing 16 KiB request boundary |
| 422 | INVALID_INPUT | HTTP schema/JSON/path validation, before domain work |
| 422 | VariantErrorCode | Reached M1/M2 errors (all codes listed above); safe domain details preserved |
| 429 | ADMISSION_LIMIT | Zero-queue worker admission; retryable, Retry-After: 1 |
| 500 | ARCHIVE_INTEGRITY | Damaged known records or missing/corrupt dependencies |
| 500 | INTERNAL_ERROR | Unexpected failure or invalid outgoing DTO; sanitized |
| 503 | ARCHIVE_PUBLICATION_FAILED | Publication I/O failure; uncertain outcome, no automatic retry |
| 503 | ARCHIVE_UNAVAILABLE / CONFIGURATION_ERROR | Existing archive/configuration failures |
| 504 | OPERATION_TIMEOUT | Response budget expired; underlying work may continue |

Every error uses `{error: {code, message, retryable, details, request_id}}` and a
matching `X-Request-ID`. Raw exception text, paths and sequences are excluded.
An unknown variant is distinct from a retained variant whose reference is gone:
the latter returns 500 integrity. A missing top-level reference during creation
is 404; damage within a known reference's graph is 500. Corruption is never repaired
or accepted as a duplicate. Typed failures precede generic exception handling.

Publication I/O failure may occur after the atomic link. Its response is
nonretryable with `publication_may_complete: true`, `automatic_retry: false` and
recovery instructions. The application attaches the already derived variant ID
as transient error context, allowing a recovery ID/URL without changing archived
bytes or claiming verification succeeded. A mutating timeout has the same
uncertainty, but no ID/URL is invented. A cancelled/disconnected caller may receive
no envelope. Capacity stays occupied until the worker finishes; completion/failure
is observed and logged safely with request correlation. Verify a known ID using
GET or deliberately repeat the identical request under the idempotency contract.
There is no rollback, guaranteed absence, deletion or automatic retry.

Variant services are lazily composed against the shared archive/reference
repository. Create/get call no providers, even when unrelated catalogs are
configured. The existing executor admits all archive work, verification, DTO
conversion and serialization; no additional pool/queue is introduced. Health and
startup do no archive readiness/scientific work. Shutdown drains actual workers.

These fields are frontend-ready; mutation entry, confirmation and highlighting
remain NF-07 work. Prediction, comparison, export and independent scientific
acceptance remain separate gates. The synthetic OpenAPI example MACAG/A4V/MACVG
is a sequence hypothesis using complete-reference 1-based numbering.

### Exact authored synthetic HTTP example

This example assumes the authored M1/M2 `synthetic-variant-reference` has been
retained in the test archive. It is not a public provider record; IDs and hashes
are exact for that fixture. OpenAPI publishes and tests this same complete body.

```http
POST /v1/variants
Content-Type: application/json

{
  "expected_reference_sha256": "c88582ee0f845de56779787b8447097ae3330a816d1656b2808e0d439206226e",
  "notation": "A4V",
  "reference_id": "synthetic-variant-reference"
}
```

The winner returns 201 and a verified identical repeat returns 200. Both use
`Content-Type: application/json`, a request correlation `X-Request-ID`, and:

```http
Location: /v1/variants/variant-4f0a7366f1a3a152596ba4337b0f2050b7b06e70640cc77ef54aafa84143f165
```

Both success bodies, and a verified GET of that Location, are exactly:

```json
{
  "differences": [
    {
      "alternate_aa": "V",
      "position": 4,
      "reference_aa": "A"
    }
  ],
  "interpretation_kind": "hypothesis",
  "notation": "A4V",
  "reference_accession": "P00001",
  "reference_content_hash": {
    "algorithm": "sha256",
    "encoding": "neurofold-json/1",
    "sha256": "a36dc032d7baa24bf2d1a3a30f67491826fb4f702626b308df6d80c685a77bdb"
  },
  "reference_entry_version": {
    "reason": null,
    "state": "present",
    "value": 2
  },
  "reference_id": "synthetic-variant-reference",
  "reference_sequence_sha256": "c88582ee0f845de56779787b8447097ae3330a816d1656b2808e0d439206226e",
  "reference_sequence_version": {
    "reason": null,
    "state": "present",
    "value": 1
  },
  "reference_taxon_id": 1,
  "schema_version": "neurofold-variant/1",
  "sequence": "MACVG",
  "sequence_hash": {
    "algorithm": "sha256",
    "encoding": "sequence-ascii/1",
    "sha256": "938b2b382d01f18f15d8d909f926f1b02c94bd5ad7527a057a91733787060315"
  },
  "sequence_length": 5,
  "substitution": {
    "alternate_aa": "V",
    "notation_version": "nf-substitution/1",
    "position": 4,
    "reference_aa": "A"
  },
  "variant_id": "variant-4f0a7366f1a3a152596ba4337b0f2050b7b06e70640cc77ef54aafa84143f165"
}
```
