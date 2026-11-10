# NF-02 — Biological Data Integration

Status: proposed; implementation has not started. Parent: [NF-EPIC-001](../EPIC.md).

## 1. Objective and scientific motivation

Resolve researcher-selected public proteins through UniProtKB and discover
experimental structures through RCSB PDB. Preserve exact sequence/source snapshots
so a later substitution refers to an identifiable biological record rather than
an accession whose content may have changed. Missing structures are a valid
scientific outcome, not a reason to invent coordinates.

## 2. Scope and non-goals

Include accession lookup; exact gene-name search with optional NCBI taxonomy
filter; organism IDs; canonical reference sequences; experimental entry/entity/
chain metadata; selected mmCIF downloads; initial reference-to-structure residue
maps; source receipts; bounded caching; and upstream failure handling.

Search can return multiple organisms or entries, and the user must select one.
Show reviewed status without implying unreviewed records are incorrect. Only
canonical UniProtKB references are editable in the MVP. Display isoform identifiers
where returned, but reject unsupported isoform reference creation explicitly;
never strip a suffix and silently substitute the canonical sequence.

Exclude model packages, inference, exhaustive database mirroring, arbitrary URL
fetching, private sequence upload, cross-database clinical interpretation and
homology-based automatic reference replacement. No database or broker is needed.

## 3. Dependencies

- NF-01 application factory, HTTP/core separation, locked tooling and tests.
- [NF-08 M1](NF-08-reproducibility.md): source receipt, hash, artifact and evidence
  contracts. Pin these before writing persisted records.
- NF-03 consumes snapshots; NF-05 consumes imported structures and residue maps.
  NF-06 extends the mapping contract without introducing a second numbering model.

## 4. Proposed architecture and interfaces

Add frozen records and `ProteinCatalog`, `ExperimentalStructureCatalog`,
`ReferenceRepository`, `StructureRepository`, and `ArtifactStore` protocols in
`core/`. Application services implement search, reference pinning and structure
import by composing these protocols. API routes translate HTTP into those calls.

Implement UniProt and RCSB clients in `adapters/biological/`; inject a bounded HTTP
transport, clock and retry policy. Choose and lock a production HTTP dependency
during implementation; do not rely implicitly on the current test-only HTTP client.
Use an ignored filesystem repository for immutable snapshots and artifacts.
Cache indexes are replaceable; scientific source receipts are append-only.

UniProt entry retrieval and search use its REST API. RCSB discovery uses the
Search API with a UniProt reference-identifier filter and experimental-content
restriction; the Data API retrieves entry, polymer entity and instance details.
Do not rely solely on a UniProt PDB cross-reference to assert matching coverage.
The [RCSB Data API](https://data.rcsb.org/) exposes computed models too, so validate
experimental origin explicitly. Retrieve mmCIF only from configured RCSB download
hosts and revalidate redirects; clients cannot supply fetch URLs.

Resolve source sequences against polymer sequences and mmCIF residue identifiers
before assigning coordinates to reference positions. Place any third-party parser
or alignment dependency behind an adapter. Ambiguous alignments remain ambiguous.

## 5. Data models and API contracts

| Record | Required fields |
| --- | --- |
| `ProteinSummary` | accession, canonical/isoform indicator, gene names, organism name/taxon ID, reviewed flag, sequence length, source receipt ID |
| `ReferenceSnapshot` | opaque reference ID, accession, taxon, exact normalized sequence, sequence SHA-256, source sequence/entry versions, source receipt, captured time, schema version |
| `SourceReceipt` | provider, query/URL without secrets, retrieval UTC, release/date if supplied, ETag/Last-Modified if supplied, raw response SHA-256, raw artifact ID, license/citation references |
| `ExperimentalStructureSummary` | PDB entry/entity IDs, label/auth chain IDs, experimental method, resolution with method/unit or unavailable reason, revision/date, assembly choices, polymer sequence, mapped coverage, citations, receipt |
| `StructureDescriptor` | structure ID, raw mmCIF artifact ID/hash, evidence=`experimental`, selected entity/chain/model/assembly/operator, source metadata, mapping ID |
| `ResidueMapRow` | reference ID/hash and 1-based position, structure ID, model, entity, label/auth chain, label sequence ID, auth sequence ID as string, insertion code, assembly operator, observed residue, coordinate-present flag, status/reason |

Mapping statuses include `exact`, `mismatch`, `unobserved`, `unmapped`, and
`ambiguous`. A polymer residue may map to the reference while lacking coordinates.
Store missing label/auth identifiers explicitly; do not manufacture integer author
numbers. mmCIF numbering and coordinate conventions follow the
[wwPDB guide](https://mmcif.wwpdb.org/docs/user-guide/guide.html).

Proposed backend routes (see epic for error envelope and browser prefix):

| Method/path | Input | Success and relevant errors |
| --- | --- | --- |
| `GET /v1/proteins` | `gene`, optional `taxon_id`, `cursor`, `limit` (default 20, maximum 100) | 200 `{items, next_cursor, availability, warnings}`; 400 invalid query/cursor |
| `GET /v1/proteins/{accession}` | validated accession | 200 metadata, sequence/hash and receipt; 404 absent; 422 unsupported identifier |
| `POST /v1/references` | `{accession, expected_sequence_sha256}` from the inspected record | 201 immutable snapshot, `Location`; 409 source changed; 422 unsupported isoform |
| `GET /v1/references/{reference_id}` | opaque ID | 200 pinned snapshot; 404 unknown |
| `GET /v1/references/{reference_id}/structures` | bounded cursor/limit | 200 summaries plus source receipt, `availability=complete\|partial\|unavailable`, warnings; 404 unknown reference |
| `POST /v1/structures` | `{reference_id, entry_id, entity_id, label_asym_id, model_id, assembly_id, operator_id, expected_source_revision}` | 201 imported descriptor/map, `Location`; 409 changed revision; 422 incompatible/ambiguous selection |
| `GET /v1/structures/{structure_id}` | opaque ID | 200 descriptor/map and artifact link; 404 unknown |
| `GET /v1/artifacts/{artifact_id}` | registered content ID | 200 original bytes with checksum, media type and size; 404 missing; no arbitrary paths |

Every paginated response has a bounded opaque cursor tied to its query, ordering
and provider. An expired/mismatched cursor returns 400 and a restart hint. Snapshot
creation revalidates/fetches a fresh entry, rather than trusting a stale search
cache, then compares the expected sequence hash. Persist all scientific metadata
from the actual pinned receipt. A later refresh creates a new snapshot.

Initial configurable resilience defaults: connect timeout 3 seconds; whole-call
budget 15 seconds; at most two retries for transport errors, 429 and 502/503/504,
with jitter and `Retry-After` bounded by that budget. Do not retry validation/404.
Cap downloaded compressed and expanded sizes and coordinate counts before parsing;
select and document concrete limits in M2. Limit provider concurrency to two.

Cache normalized query plus provider/schema version: search TTL 1 hour, accession
and structure metadata TTL 24 hours, negative 404 TTL 5 minutes. Never cache
transient errors as empty results. Conditional revalidation may use provider
validators. An explicitly marked stale metadata response is allowed on transient
failure for at most seven days; it cannot create a fresh scientific snapshot.
Retained immutable snapshots are not subject to cache TTL eviction.

## 6. Implementation milestones

1. **M1 — Contracts:** finalize records, mapping statuses, HTTP schemas and source
   licensing inventory; add tiny synthetic provider fixtures and API contracts.
2. **M2 — Lookup:** implement clients, encoded queries, pagination, transport
   limits, cache/revalidation and reference pinning; document resource limits.
3. **M3 — Structures:** discover only experimental candidates, import selected
   mmCIF, preserve revisions and create explicit sequence/residue maps. Show
   construct mismatches, fragments and missing coordinates.
4. **M4 — Integration:** expose routes, test partial failures and offline pinned
   reads; document configuration, source attribution and refresh semantics.

## 7. Acceptance criteria

- Accession lookup and gene/taxon search return validated identifiers, organisms,
  sequences and provenance. Ambiguous searches never auto-select a reference.
- The same pinned reference remains readable after provider changes or outage;
  fresh source changes trigger 409 when the inspected hash differs.
- Structures include origin, methods, revisions and coverage; computed models
  cannot appear in an experimental-only list. Empty and unavailable differ.
- Mapping distinguishes reference, polymer, author and coordinate numbering,
  including insertion codes, construct mutations and unresolved residues.
- One provider's failure preserves usable data from the other with explicit
  warnings. No network request occurs during API startup or `/health`.
- All new errors follow the epic contract; resource and retry bounds are tested.

## 8. Automated testing requirements

Unit tests use injected transports, clocks and synthetic JSON/mmCIF only: exact
and multi-hit lookup; taxon filtering; invalid/obsolete/redirected accession;
unsupported isoform; version change; pagination; escaping; cache hit/expiry/304;
404 versus timeout/429/5xx; exhausted retry budget; malformed or truncated data;
size/decompression bounds; forbidden redirects; complete/partial discovery.

Contract tests cover every route, error envelope, `Location`, pagination and raw
artifact bytes. Mapping fixtures cover chain label/auth differences, insertion
codes, negative author numbering, gaps, tags, alternate models, assemblies and
unobserved residues. Repository tests verify immutable writes and atomic
publication. Core import tests still run without site-packages.

Optional scheduled live provider probes may detect schema drift but do not replace
offline tests or block ordinary CI on external availability. Refresh fixtures only
after review; never snapshot real research data into unit fixtures.

## 9. Scientific validity and reproducibility

The [UniProt API paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC12230682/) documents
release headers and pagination. Record received release metadata; missing provider
versions must be explicit and accompanied by receipt time and raw-byte hashes.
Do not equate accession stability with sequence identity.

An experimental structure can contain engineered substitutions, truncations,
different oligomeric states or ligands. Discovery is not proof that it represents
the selected reference in vivo. Record these differences before comparison.
Do not rank methods using a universal resolution field or confuse absence of
coordinates with absence of residues in the protein.

Retain source terms and citations independently. RCSB documents CC0 for archive
and programmatic data in its [usage policy](https://www.rcsb.org/pages/usage-policy);
that does not license unrelated website text or third-party data. Verify current
UniProt terms and attribution requirements before shipping its client/export.

## 10. Risks and unresolved decisions

- **Parser/alignment selection:** review an optional library's license, Python
  support and ability to preserve identifiers before M3; numerical imports stay
  out of core. Identity mapping alone cannot handle real constructs.
- **Upstream drift/rate limits:** version the adapter and cache schema; tune the
  proposed bounds against provider policies without unbounded fallback requests.
- **Identity scope:** canonical-only editing is the MVP default. Isoform support
  needs new explicit reference selection and tests, not silent normalization.
- **Structure size and assembly complexity:** set measured parse/download limits
  in M2; fail explicitly rather than silently extracting a convenient fragment.
- **Source licensing:** persist reviewed license identifiers/notices in M1 and
  recheck on upstream changes. No claim here relicenses UniProt content.
