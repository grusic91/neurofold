# NF-03 M1 — Pure substitution domain evidence

Date: 2026-11-10. Implementing-agent software validation against initially clean
`5f60e2a1d09429949e212500e75fc9b7bad329cc` (NF-02 operational validation).
**M1 complete for pure domain logic. M2/M3 and independent scientific acceptance
remain incomplete.** Changes are uncommitted for review.

## Implemented scope and decisions

`core/variants.py` adds frozen keyword-only `Substitution`, `SequenceDifference`
and `SubstitutionResult` records and pure `parse_substitution`,
`validate_substitution`, `apply_substitution` and `sequence_difference` functions.
[The domain guide](../variants.md) documents signatures, result fields, strict
codecs and the deterministic validation/error precedence before dependent use.

Strict `nf-substitution/1` parsing accepts twenty uppercase ASCII residues and
positive decimal positions without normalization. An 18-character bound precedes
integer conversion; positions are exact positive safe integers through
9007199254740991, consistent with NF-08. Direct construction and strict codecs
reject booleans, coercions, unsupported versions and invalid representations.
No-op requests are representable but fail reference-dependent validation after
alphabet, bounds and mismatch checks.

Whole-reference alphabet rejection precedes position bounds, reference mismatch
and no-op validation. `VariantError(ValueError)` exposes stable codes and copied
structured details. Required failures are `INVALID_NOTATION`,
`POSITION_OUT_OF_RANGE`, `REFERENCE_MISMATCH`, `NO_OP_SUBSTITUTION` and
`UNSUPPORTED_REFERENCE_ALPHABET`. Narrow additional codes cover invalid domain
arguments, difference inputs/unequal lengths and inconsistent result records.
Mismatch names the requested and actual pinned residues and 1-based position;
unsupported-alphabet details list every affected position/symbol in sequence order.

The result retains the original full `ReferenceSnapshot` object, using
`reference.protein.sequence` and its existing source/hash identities. The exact
slice substitution preserves length and yields exactly one requested difference.
Derived hashes use existing `sequence_sha256` / `sequence-ascii/1`, separate from
canonical record hashes and future variant IDs. A result is a sequence hypothesis;
the original reference's evidence/provenance is preserved without relabeling.
M1's round-trip helpers do not freeze M2's persisted `VariantDefinition` schema.

## Synthetic behavioral evidence

`tests/test_variants.py` adds **559 tests** under unchanged socket/DNS guards:

- Independently specified `MACAG` / `A4V` / `MACVG` and position-4 difference;
  exact independent byte hashes, reference-object linkage, frozen records,
  strict round trips and unchanged original reference/provenance bytes/hash.
- First/last positions; all **380** unequal canonical residue pairs; **78**
  requested changes across deterministically authored lengths 1–12, preserving
  exact surrounding residues, length, one-change positions and hashes.
- Malformed/empty/oversized notation, trailing newlines, whitespace, lowercase,
  leading zeros, signs, decimals, multiple edits, indels, stops, Unicode digits/
  lookalikes/surrogates and non-string inputs. Includes a 5,000-digit position,
  safe-integer boundary, structured bool/float/string/null/zero/negative/oversized
  positions, invalid symbols/versions and adversarial codec inputs.
- Alphabet failures at and away from the selected position, complete repeated
  symbol details, alphabet-before-bounds/mismatch/no-op precedence, mismatch-
  before-no-op, bounds-before-no-op, and invalid domain argument types.
- Immutable ordered zero/one/multiple difference records, empty equal inputs,
  exact noncanonical/Unicode comparisons, explicit unequal-length rejection,
  invalid difference/result constructors and decoded inconsistent derived fields.
- An independently authored `M + ACDEFGHIKLMNPQRSTVWY * 7 + A` reference has 142
  residues; hypothetical structural coverage has 141. `A142V` succeeds without
  passing any structure/map, and position 1 includes the initial methionine.

The source-backed fixture entry `variants-inline` in [fixtures.json](fixtures.json)
records authorship, license, exact source size/hash and expected invariants. It
reuses frozen synthetic metadata with a separate inline sequence-byte receipt;
it contains no downloaded source data. Existing frozen v1 fixture/schema bytes
remain unchanged. No ignored live artifacts were read.

## Executed checks

Local macOS ARM64, Python **3.12.16**, uv **0.13.7**, Node **24.5.0**, npm **11.5.1**.

| Check | Actual result |
| --- | --- |
| `uv sync --locked` | Pass; 45 packages resolved, 43 checked |
| `uv run --locked ruff check . ../infra/testing` | Pass |
| `uv run --locked ruff format --check . ../infra/testing` | Pass; 55 files already formatted |
| `uv run --locked mypy src tests scripts ../infra/testing` | Pass; 55 source files, including new tests |
| Focused `pytest tests/test_variants.py tests/test_architecture.py --no-cov -q` through locked uv | **560 pass** (559 new behavior cases plus existing import isolation) |
| `uv run --locked pytest` | **1,119 pass**, 20.37 seconds; **96.89%** overall branch-enabled coverage, above required 90%; `core/variants.py` **100%** statement/branch coverage |
| Core import isolation | Pass in existing `python -I -S` subprocess discovering every core module without site-packages |
| `npm ci --offline --cache /private/tmp/neurofold-npm-cache` | Pass; 268 packages installed from cached locked artifacts |
| `npm run lint` / `npm run typecheck` / `npm run build` | All pass; production bundle built |
| `git diff --check` | Pass |
| Compatibility diff | Existing manifests/locks, LICENSE, frozen v1 fixtures and JSON Schemas unchanged |

Backend commands use `UV_CACHE_DIR=/private/tmp/neurofold-uv-cache` because the
default cache is not writable in this sandbox. An initial npm offline install
found an empty temporary cache; copying the existing global package cache into
that temporary location allowed the locked offline install to pass. No dependency
change or provider request was needed. Existing CI already runs the same checks
with locked installs (Python 3.12/3.13, Node 24); no CI edits were needed. No hosted
CI execution or new Python 3.13/platform validation is claimed here.

## Compatibility, deferred work and scientific gates

This is additive core behavior. Frozen NF-02/NF-08 v1 contracts, schemas and
fixture bytes retain their identity; application version remains 0.1.0. M1
clarifies the proposed NF-03 alphabet-check precedence, integer representation and
explicit mismatch detail names. There is no existing variant API/archive to
migrate. No new dependency, HTTP surface, application service, adapter, storage,
database, queue or model package was introduced.

- **M2:** versioned persisted `VariantDefinition`, content-derived IDs, reference
  resolution/linkage, repository/service orchestration, immutable atomic writes,
  duplicates and load-time archive/derived-sequence integrity verification.
- **M3:** HTTP DTOs/routes, status/envelope translation and OpenAPI contracts.
  `REFERENCE_NOT_FOUND` and `REFERENCE_HASH_MISMATCH` remain later workflows.
- Frontend interaction, molecular viewers, inference, comparisons and exports
  remain later work. No prediction/model execution or biological effect is tested.

Per the authorized M1 boundary, no live provider probes, browser/container
investigations or infrastructure changes were performed; these were not required
for this pure domain milestone. Frontend behavior suites were not rerun for this
unchanged frontend. Historical x86-64, live browser/container and broader-provider
limits remain as recorded in [NF-02 operational evidence](nf02-operational-evidence.md).
[Scientific release gates](scientific-review.md) remain open: independent domain
review/panel approval, model/weight/data licenses, complete prediction provenance,
measured Linux/NVIDIA limits, numerical tolerances/replicates and independently
verified exports. Synthetic software correctness supplies no scientific sign-off.
No commit, push, publication or PR was performed.
