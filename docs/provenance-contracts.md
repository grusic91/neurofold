# Shared provenance contracts — NF-08 M1

Current integration: [NF-02 M4](integration.md) now exposes production routes,
a frontend workflow and retained audit projections. Health-only statements below
describe the original milestone boundary. Frozen v1 records/schemas are unchanged;
new HTTP audit versions are documented separately in the integration guide.

The implemented foundation is `backend/src/neurofold/core/canonical.py` and
`core/provenance.py`, with a private strict wire codec in `core/_contracts.py`.
These standard-library-only contracts preserve **API → core ← adapters**. They
perform no retrieval, inference, job execution, filesystem writes, export, or
biological interpretation. NF-04 M1 now evolves the NF-01 records while preserving the synchronous worker
seam; the health API and frozen NF-08 contracts remain unchanged.

## M1 decisions and ambiguities

The [NF-08 specification](tasks/NF-08-reproducibility.md) calls JSON Schema a future
artifact in section 4 but requests it in M1. M1 publishes the
[version 1 JSON Schema](schemas/neurofold-research-1.schema.json) now. The
`jsonschema` development dependency validates fixtures; core does not import it.

The roadmap does not bound integers or define decimal spelling. V1 accepts
integers from −9007199254740991 through 9007199254740991, inclusive, so future
JavaScript consumers can preserve them exactly. Larger identifiers must be
strings. Booleans remain distinct from integers. Canonical decimal settings match
`-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?`, excluding `-0`: no exponent, plus sign,
leading zero, trailing fractional zero, whitespace, or rounding. Producers call
`canonical_decimal` for fields their schemas define as decimal settings. Arbitrary
strings are not automatically interpreted as numbers.

Execution/comparison producers do not exist yet. M1 defines a manifest skeleton
with explicit capture slots, rather than guessing their full schemas. Its status
is `recorded`, `incomplete`, `failed`, or `cancelled`; there is no `succeeded`.
A `subject_kind="prediction"` skeleton cannot be `recorded`. NF-04 must introduce
a versioned successful prediction contract and completeness validator before
publishing real or fake successes. Unknown required provenance must block real
success as specified by NF-08. M1 does not certify scientific completeness.

V1 has no documented optional wire additions. Readers reject all unknown fields,
unknown versions (including an unrecognized minor suffix), missing fields, wrong
types and unknown enums. A documented optional addition needs an explicitly
supported revision and reader tests; it cannot change v1 identity bytes. This
implements the roadmap's rule to tolerate *documented* optional additions only.
Migrations create derived records linked to originals and never rewrite history.

## Canonical bytes and identities

`canonical_json(value)` emits `neurofold-json/1`: UTF-8, lexicographically sorted
ASCII keys, compact separators, no trailing newline, Unicode preserved without
normalization, and only mandatory JSON escaping. Composed and decomposed Unicode
have different identities. Lone surrogates, non-ASCII keys, cycles, sets, bytes,
all floats, NaN/infinity, unsafe integers and implicit conversions are rejected.
Ordered arrays retain order; tuples serialize as arrays. This is not RFC 8785.

`parse_json` rejects duplicate keys at every nesting level, including escaped key
aliases, and unsupported values. Whitespace/key-order variation is accepted.
Integer `-0` canonicalizes to `0`; floating-point `-0.0` is rejected. Input must
be UTF-8 without a BOM. Never reconstruct a raw artifact checksum by parsing JSON.

`canonical_set` is an explicit producer opt-in for schema-defined unordered
collections: sort by canonical UTF-8 bytes and reject duplicate encodings. Do not
use it on preprocessing steps, atom pairs or meaningful scientific orders.
Source reference inventories and receipt ID lists require unique lexicographically
sorted strings. Artifact parents sort by `encoding + ":" + sha256`. Input/output
inventories and warnings preserve producer order; duplicate input/artifact IDs
are rejected.

`CanonicalObject.from_value` snapshots an object into immutable bytes. Mutating
the original or a returned `to_dict()` copy cannot change it. Domain records are
frozen, use tuples for collections, validate direct construction, and provide
`to_dict`, `to_json`, `from_dict` and `from_json`. Wire readers require every field,
including serialized constructor defaults; they do not inject defaults or coerce
strings, booleans, numbers or arrays.

| Identity | Exact bytes hashed with SHA-256 | Encoding descriptor |
| --- | --- | --- |
| Original/derived artifact | Stored bytes, including whitespace/newlines | `raw-bytes/1` |
| Stored sequence | Nonempty uppercase printable single-line ASCII, no whitespace/header/newline | `sequence-ascii/1` |
| Structured scientific input | Canonical JSON of versioned, fully resolved content | `neurofold-json/1` |

`sha256_bytes` returns 64 lowercase hexadecimal characters. `ContentHash` records
`algorithm="sha256"` and the encoding version. Domains remain distinguishable even
if their hashes coincide; no hidden prefix changes the SHA-256 input bytes.
`sequence_sha256` never uppercases, strips or substitutes symbols. Noncanonical
letters and printable symbols such as `X`, `U`, `*`, `-`, `?` are retained. This
is identity validation, not biological alphabet validation. NF-02 records source
extraction/normalization separately; NF-03/04 reject unsupported alphabets without
rewriting snapshots.

`ScientificInput` is a reusable envelope with `schema_version`, `record_kind`,
`canonicalization_version`, a producer-owned `input_schema`, and immutable
`payload`. Its `content_hash` hashes the whole serialized envelope. Producers
validate the payload, resolve **all** defaults, and exclude receipt timestamps,
display settings and local paths before construction. M1 cannot infer defaults
for future schemas. Tasks specifying their own identity document, such as NF-03's
variant ID, can hash that document with `canonical_json` directly. Do not silently
wrap it and change the prescribed identity. Include the task's schema version
and relevant immutable snapshot IDs/hashes exactly as specified.

Opaque snapshot, receipt, registry and manifest IDs remain separate from hashes.
Equal content does not erase separate retrieval receipts. A checksum proves byte
identity, not authenticity, scientific truth or redistribution permission.

## Records and explicit absence

| Contract | Meaning |
| --- | --- |
| `Metadata` | State, value and reason for scalar or immutable structured information |
| `ReferenceCollection` | License/citation inventory with explicit absence semantics |
| `ContentReference` | Opaque immutable record ID plus content hash |
| `ArtifactRights` | Independent license, attribution, redistribution decision and basis |
| `ArtifactDescriptor` | Versioned registered ID, raw hash, size, media type, evidence, rights, parents and transformation |
| `SourceReceipt` | Retrieval identity/provider/query/UTC time, raw artifact, accession/isoform/taxon/versions, release/date, HTTP validators and rights/citation references |
| `ProvenanceSections` | Explicit preprocessing, model, execution, environment, comparison, interpretation and rights/privacy slots |
| `ProvenanceRecord` | Versioned skeleton header, evidence/status, inputs, receipts, output artifacts, sections and warnings |

`Metadata.state` is `present`, `unavailable` or `not_applicable`. Present metadata
requires a non-null value and null reason. Both absence states require null value
and a nonblank reason. Zero, false and empty text are distinct present values;
a missing metric is never zero. Structured values require `CanonicalObject`.
Producers own field-specific definitions, units, requiredness and internal schemas.
Source text/version/taxon fields have additional type checks; present licenses
and attributions must be nonblank textual references. Reference collections need
nonempty sorted identifiers when present, or an empty tuple and absence reason.

```python
from neurofold.core.provenance import Metadata, MetadataState

resolution = Metadata(
    state=MetadataState.UNAVAILABLE,
    value=None,
    reason="The source did not report a resolution for this method.",
)
```

Timestamps are valid UTC `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`, with up to six fractional
digits. No clock, timezone conversion or local time is implicit. Sizes are
nonnegative safe integers; media types omit parameters. Descriptors contain
registry IDs, never host paths. Derivatives need parent hashes and present
transformation metadata: method/version, ordered steps, units and conventions
belong in its payload. Originals explicitly mark transformation not applicable.
Self-parenting and duplicate parents fail. Parent existence and actual byte
integrity require NF-08 M2 storage; M1 has no repository to check them against.

Evidence is exactly `experimental`, `predicted` or `synthetic`. Hypotheses are
interpretations, not another evidence category. Every output of a synthetic
manifest must be synthetic. Experimental context belongs in input references or
source receipts. Downstream views/exports must retain fake labels. A contract
validates a declared label; it cannot independently verify origin.

Unknown redistribution rights are explicit. `allowed` requires an identified
license and decision basis, but does not perform legal review. Sources, models,
weights, databases and derivatives need independent review. Redaction,
normalization and alignment produce new artifacts without overwriting originals.
Producers must allowlist runtime metadata and review queries/logs for secrets;
contracts do not sanitize arbitrary text automatically.

## Ownership by downstream tasks

| Consumer | Required use and remaining producer work |
| --- | --- |
| NF-02 | M1 reuses receipts, rights, absence and hash domains in [biological records/DTOs](biological-contracts.md). Actual source capture, adapters, imports and storage remain M2–M4. |
| NF-03 | Hash the specified substitution document; keep creation receipts outside identity; verify mutated sequence hashes. Hypothesis interpretation stays separate from evidence. |
| NF-04 | Resolve spec defaults; identify exact auxiliary artifacts or reasoned absence; define complete execution/model/weight/environment schemas and successful publication validation. Synthetic model/weights/GPU are not applicable with reasons, while fake adapter/software identity remains required. |
| NF-05 | Consume registered bytes/evidence; expose absent confidence/mappings; viewing never changes scientific identity or raw coordinates. |
| NF-06 | Preserve ordered inputs, selections, pairs and transforms; hash versioned comparison definitions; retain numerical results as exact raw artifacts with precision/tolerances, not browser-reserialized identities. |
| NF-07 | Translate HTTP DTOs at the API boundary and expose provenance/evidence/absence. Any future frontend identity computation must pass the shared golden vectors; none is introduced now. |
| NF-08 M2–M4 | Implement atomic storage/capture, dependency resolution, integrity checks, complete manifests, license-aware bounded exports, offline verification, migrations and replay. |

`ArtifactStore` and `ManifestRepository` are protocols only: opaque ID lookup and
immutable publication, `KeyError` for unknown IDs, `ValueError` for conflicts or
integrity failures. Artifact reads/publication use binary streams without HTTP
paths. Future adapters verify bytes/sizes, stage and atomically publish under
configured ignored roots. No database or storage implementation is introduced.

## Compatibility and tests

The checked-in Draft 2020-12 schema has ID `urn:neurofold:research:1`. It covers
inputs, descriptors, receipts and skeletons. Schema validation checks exchange
shape; core additionally enforces sorted collections, hash domains, lineage,
evidence and prediction publication rules. JSON Schema cannot detect duplicate
keys after parsing, distinguish JSON `1.0` mathematically from an integer, or
check canonical byte spelling. Use the strict reader too. API schemas/frontend
DTOs remain task-owned translations, not core dependencies.

`backend/tests/fixtures/contracts-v1.json` is a frozen synthetic compatibility
baseline. `canonical-v1.json` publishes independently specified expected bytes
and SHA-256 vectors. Tests cover Unicode, types, ordering, explicit defaults,
decimal spellings, duplicate keys, nonfinite values, immutable snapshots, exact
sequence/raw bytes, required fields, absence reasons, unsupported nested schemas,
evidence, derivatives and failed/cancelled attempts. Architecture tests import
all core modules with site-packages disabled.

Use the existing commands from `backend/`; tests need no network, GPU, weights,
services or research data:

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests
uv run --locked pytest
```

Schema changes require deliberate compatibility decisions and fixtures. Export
root inventories/sidecar checksums remain M3. The skeleton never embeds its own
checksum, avoiding circular identity.

## NF-02 M2 capture implementation

[UniProt lookup](uniprot-lookup.md) now produces real retrieval receipts and exact
raw artifacts through the existing protocols. The opt-in filesystem store
implements ArtifactStore; immutable references retain receipts independently of
metadata caches. A separately versioned `neurofold-reference-pin/1` audit links
a pin's authoritative 200/304 check to the original source receipt without changing
NF-08 v1 identities. Full scientific manifests, exports and replay remain future
NF-08 milestones.

## NF-02 M3 capture

M3 preserves frozen research/biological v1 bytes and adds
`neurofold-structure-import/1`: an atomic descriptor/map/audit with authoritative
200/304 checks, original receipt IDs, raw source artifacts, parsing/normalization
and alignment parameters/versions, selection inventories and coverage counts.
304 check time/headers never replace original retrieval bytes or receipt metadata.
Compressed entity bytes retain their own raw hash; decoding is separately recorded.
Coordinates remain deposited Cartesian angstroms; assembly operators are retained
as not applied. This is source/import lineage, not a complete prediction manifest
or scientific validation. See [M3 decisions](structure-import.md).

## NF-04 M1 complete prediction contracts

[Prediction contracts](prediction-contracts.md) introduce the separate
`neurofold-prediction-provenance/1` successful schema, required typed model/weights,
software/environment/locks, execution, preprocessing and captured auxiliary inputs,
full samples/raw artifacts, nondeterminism and interpretation declarations.
Synthetic inapplicability differs from unavailable required real provenance.
`validate_completeness` and `validate_publication` check supplied records and
injected byte identities; they perform no storage/transaction, runtime inspection,
scientific review or molecular parsing. Real unknown required sections prevent
publication. License declarations do not independently approve rights; unknown
redistribution still blocks any later unreviewed export, not merely a byte check.

The manifest identifies the result by ID only; the result references the canonical
manifest hash. No self checksum or checksum cycle exists. Specs use the NF-08
canonical and exact sequence domains; operational IDs/times/retries are excluded
from spec identity. The frozen skeleton remains unchanged and cannot certify
success. NF-08 M2 capture/storage and M3/M4 export/audit remain open.
