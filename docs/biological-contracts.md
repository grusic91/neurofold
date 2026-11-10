# Biological contracts — NF-02 M1 (frozen)

Implemented: immutable standard-library records in `core/biological.py`, HTTP
DTOs in `api/biological.py`, a frozen [HTTP JSON Schema](schemas/neurofold-biological-http-1.schema.json),
synthetic fixtures and offline contract tests. `neurofold-biological/1` is a new
strict version; nested NF-08 records retain `neurofold-research/1` unchanged.
Unknown fields/versions and omitted fields fail; no migration or silent defaults
are applied to scientific records. Query defaults are explicitly limit 20 and
no cursor/taxon filter. Package/API application version remains 0.1.0.

The production application still exposes only `/health`. The eight proposed
operations in [NF-02](tasks/NF-02-biological-data.md#5-data-models-and-api-contracts)
are exercised in a **test-only ASGI harness** with fixed responses. The harness
remains fixed-response contract evidence.
[M2](uniprot-lookup.md) now implements Python lookup/pinning/storage separately;
[M3](structure-import.md) implements structures and M4 owns operational routes.
M1 fixtures and HTTP schema remain unchanged; M2 introduces a separate pin-audit record for 304 checks, and
M3 adds a separate import bundle/audit without changing v1 wire fields.

## Records and identity

| Record | Contract decision |
| --- | --- |
| ProteinSummary | Accession, canonical/isoform identity, gene inventory, organism/taxon/reviewed metadata, length and receipt ID. Missing metadata has an NF-08 state/reason. A reviewed flag is not a quality or clinical judgment. |
| ProteinRecord | Summary, exact sequence, `sequence-ascii/1` hash, full NF-08 receipt and nonblank normalization description. Sequence length/hash and known receipt identity must agree. No normalization is performed by the record. |
| ReferenceSnapshot | Opaque immutable ID, ProteinRecord and explicit UTC capture time. Versions, raw bytes, receipt time, source and rights are retained inside its receipt. Pinning requires a known positive taxon and canonical selection. |
| ExperimentalStructureSummary | Entry/entity/label/auth chain, reported methods and one resolution-or-absence per method, revision/date, assemblies, polymer sequence, reference coverage, citations and receipt. Origin must be experimental; synthetic receipts label examples. Computed/predicted receipts are rejected. |
| StructureDescriptor | Opaque ID, original mmCIF ArtifactDescriptor (ID/raw hash/size/rights), evidence, selected instance, source summary and mapping content reference or explicit absence. Predicted structures are outside NF-02. |
| ResidueMap | Opaque mapping ID, reference/structure/selection identity, reference length, method/version and ordered immutable rows. Canonical content hash covers every field. |

All biological records expose a canonical JSON content hash, distinct from their
opaque IDs, exact sequence hash and raw artifact hash. Full-record hashes include
receipts; they are not accession IDs or timestamp-free scientific input hashes.
Equal sequences can have different snapshots/receipts. Later refreshes create new
records. Reuse NF-08 ArtifactStore rather than introducing another artifact seam.

`ProteinCatalog`, `ExperimentalStructureCatalog`, `ReferenceRepository` and
`StructureRepository` are synchronous protocols only. Catalog transport failures
must remain failures; `KeyError` denotes absence and `ValueError` invalid input
or immutable-publication conflicts. StructureRepository publication must validate
descriptor/map cross-identities and publish them atomically; storage, publication
integrity and transport exception translation are M2–M4 work.

## Numbering and mapping states

Each row carries a MappingIdentity: reference ID plus **sequence hash**, structure
ID plus **raw coordinate artifact hash**, entity, label/auth chain, model,
assembly and operator. The descriptor points to the map's ID/canonical hash.
Maps do not hash descriptors: this avoids a circular identity. Different models,
assemblies or operators remain different selections. No transformation is applied.
A map reference is not a raw structure checksum.

Reference and label sequence positions are positive 1-based integers. Author
residue identifiers are strings, preserving `-2`, `0` and nonnumeric identifiers.
Insertion codes have independent Metadata states; no author number or chain is
invented from a label. Following the [PDBx/mmCIF guide](https://mmcif.wwpdb.org/docs/user-guide/guide.html),
future parsers must distinguish `?` (unknown) from `.` (inapplicable/intentionally
omitted) with context and reasons, retaining original bytes. M1 parses no mmCIF;
[M3](structure-import.md) now provides the bounded parser.

| Status | Meaning and invariant |
| --- | --- |
| exact | One reference/polymer correspondence with equal one-letter residues and coordinates; no reason required or accepted. |
| mismatch | Resolved correspondence with different residues, explicit reason; coordinate presence remains independent (a substitution may also be unresolved experimentally). |
| unobserved | Resolved, equal polymer/reference residues without coordinates, with reason. It does not mean the residue is absent from the protein. |
| unmapped | Explicit gap: either a known reference position/residue without a polymer position, or a polymer position/tag without a reference assignment. No candidate assignments; reason required. |
| ambiguous | No asserted reference position/residue. Optional sorted unique candidate reference positions, possibly empty if unknown; reason required. No candidate is silently selected. |

Coordinate presence does not imply complete atoms, an alignment or biological
validity. ResidueMap rejects duplicate resolved reference positions, duplicate
polymer positions in the selected instance, inconsistent row identities and
out-of-bounds candidates/positions. It is not an alignment implementation or a
completeness certificate. Future producers/repositories must check residues and
length against the actual pinned reference, preserve gaps for every relevant
position, validate source origin/methods and verify actual artifact bytes.

Mapped coverage uses `unique-reference-positions/1`: count distinct exact,
mismatch and unobserved reference positions divided by the pinned reference
length. Unmapped gaps and ambiguous candidates are excluded. This is neither
coordinate nor atom coverage. Unknown coverage uses Metadata, never zero. Method
resolution uses positive canonical decimal strings with unit `angstrom`, or
reasoned absence; methods are not ranked by a universal scalar resolution.

## HTTP boundary

DTOs explicitly translate to/from core via the NF-08 strict codec. Pydantic stays
in `api/`. JSON Schema documents exchange shapes; core additionally checks hashes,
lineage and conditional invariants. All response fields are required, including
nulls inside absence envelopes. Responses include the biological schema version.
No TypeScript contracts are added before the frontend consumes them.

Requests reject extra fields and arbitrary URLs/paths. ReferenceRequest accepts
only canonical UniProtKB accessions and an inspected lowercase sequence SHA-256;
it rejects suffix stripping and unsupported isoform pinning. StructureRequest
includes explicit model, assembly/operator states and expected source revision.
Unknown revision is retained as absence; safe fresh-selection/revalidation policy
must be implemented in M3 before import, not inferred from this schema.
IDs in HTTP paths use at most 128 ASCII letters/digits/`.`/`_`/`:`/`-`, starting
with a letter/digit. No source URL is accepted as an artifact identifier.

Search accepts a single nonblank gene token (at most 128 characters), optional
positive safe-integer taxon, bounded nonempty cursor (at most 2048 characters),
and integer limit 1–100. Decimal query strings are explicitly decoded; JSON body
numbers and booleans are not coerced. M2 implements opaque server-side cursors,
expiry, provider/query/order binding
and rejection with restart hints. Accession syntax validation never proves an
accession exists; M2 validates source identity and rejects obsolete/substituted IDs.

Pages retain items, source receipts, next-cursor Metadata, availability and
warnings. Complete-empty results differ from unavailable-empty results;
partial/unavailable require warnings. Unavailable cannot assert items. Partial
can preserve usable items; transport errors must never become complete-empty.
A missing map is represented both in the descriptor and response with matching
absence state/reason, not an invented zero-length map.

The harness verifies all proposed success bodies, 201/Location, checksum/ETag,
media type, content length and original placeholder bytes; invalid requests,
response validation, query defaults/bounds, schema versions and the epic error
envelope. It demonstrates envelope shapes at 400/404/409/413/422/429/502/503/504.
It does **not** implement source-change detection, retries, missing-record lookup
or failure translation. Those scenarios require real orchestration in M2–M4.
Artifact HTTP contract: registered ID, exact bytes/media type/Content-Length,
`X-Checksum-SHA256` and quoted raw SHA-256 ETag. Real streaming/integrity checks
and missing-artifact behavior remain future work.

## Fixtures, rights and remaining gates

[Fixture inventory](testing/fixtures.json) records raw sizes/hashes, authorship,
evidence and construction. Provider examples are tiny **authored synthetic JSON**,
not downloaded provider responses. Identifiers, organisms and sequences are
fictional examples even where syntactically valid; no lookup is made. The frozen
biological fixture connects real fixture raw bytes to synthetic receipts. Its
mmCIF descriptor names a 44-byte diagnostic placeholder served only by the test
harness: it is not a molecular file, parsed structure or imported artifact.
The six-row map is hand-specified, not computed from that placeholder.

[Source inventory](source-licensing.md) separates external terms from the
Apache-2.0 fixtures and project license. Rights remain per artifact, with unknown
rights explicit. M2 must recheck source terms on client shipment and upstream
changes; M3 must review parser/alignment licenses and define resource limits.
M2 now tests atomic reference storage and full sequence/source consistency with
synthetic inputs. Real provider compatibility, structure discovery/imports and
biological validity remain unverified.
See [M1 acceptance evidence](testing/nf02-m1-evidence.md) for checks and gaps.

M2 implementation/status supersedes the future-tense M2 work above; see its
[guide](uniprot-lookup.md) and [acceptance evidence](testing/nf02-m2-evidence.md).

## Additive M3 producer and repository

The v1 records above remain frozen. `core/structures.py` adds a strict
`neurofold-structure-import/1` envelope, source validation checks and adapter
protocols. Its producer validates every mapped residue against the actual pinned
reference and selected entity polymer, retains reference and polymer gap rows,
and fills typed imported reference coverage. Additional polymer/coordinate/identity
counts and all scoring/tie policies are in the audit. Models, chains, components,
alternate locations and assembly operators remain identifiable in retained bytes
and parse inventory. Unknown component parents produce ambiguous rows.

The filesystem repository validates cross-record IDs/hashes, reference dependencies,
original artifacts/receipts and final authoritative revision. It publishes a single
checksummed descriptor/map/audit bundle. `StructureRepository.publish` supports
identical repeats of an already complete import; initial publication uses the
additive `publish_import` protocol so an unaudited pair cannot become visible.
Missing revision fails closed, and source changes raise `StructureSourceChanged`.
Operational HTTP translation remains M4. See [M3 policy](structure-import.md).
