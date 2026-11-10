# Protein substitutions — NF-03 M1

M1 implements pure standard-library domain logic in `core/variants.py`. M2
identity/storage and M3 HTTP integration remain proposed. No variant routes,
service, repository, model runtime or frontend interaction are introduced.

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
fields/versions. These are domain inspection/round-trip helpers, **not an archive
schema or frozen persisted `VariantDefinition`**. M2 must define that versioned
contract, content-derived ID, persistence, duplicate semantics and archive
verification. Sequence hashes remain distinct from canonical record hashes and
future variant IDs. Existing frozen NF-02/NF-08 schemas/fixtures are unchanged.

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
fields. `REFERENCE_NOT_FOUND` and `REFERENCE_HASH_MISMATCH` are future storage/
transport workflows, not M1 failures.

Synthetic `MACAG` / `A4V` yields `MACVG` and exactly
`SequenceDifference(position=4, reference_aa="A", alternate_aa="V")`.
See [M1 evidence](testing/nf03-m1-evidence.md) and the
[scientific release gates](testing/scientific-review.md) for checks and limits.
