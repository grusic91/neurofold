# Experimental structures — NF-02 M3

Current integration: [NF-02 M4](integration.md) now exposes production routes,
a frontend workflow and retained audit projections. Health-only statements below
describe the original milestone boundary. Frozen v1 records/schemas are unchanged;
new HTTP audit versions are documented separately in the integration guide.

Decision record, 2026-11-10, written before orchestration. M3 is opt-in Python
discovery/import/storage. Production remains `/health` only. M4 owns HTTP/UI;
NF-05/NF-06 own viewing, atom selection, fitting and comparisons. Synthetic
acceptance establishes software behavior, never biological accuracy or live API
compatibility.

## Libraries and source review

Choose **Gemmi 0.7.5** for CIF syntax and category tables and **Biopython 1.88**
for `Bio.Align.PairwiseAligner`; lock both and NumPy 2.5.4 transitively. Imports occur
inside the selected adapters, never core or API startup. CPU wheels support our
Python 3.12/3.13 environments; no model or GPU runtime is involved.

Compared [Gemmi CIF tables](https://gemmi.readthedocs.io/en/latest/cif.html) with
[Biopython MMCIF2Dict](https://biopython.org/docs/1.88/api/Bio.PDB.MMCIF2Dict.html):
Gemmi provides strict loop syntax/duplicate checks without building a hierarchy
that might select an author chain or hide alternate atoms. Read raw categories,
not Gemmi's normalized Structure hierarchy. MMCIF2Dict is a useful lightweight
dictionary but would need additional syntax validation. Compared
[Gemmi alignment](https://gemmi.readthedocs.io/en/latest/analysis.html) with
[Biopython alignment](https://biopython.org/docs/1.88/Tutorial/chapter_pairwise.html):
choose the latter's iterable optimal paths so ties can be preserved explicitly.
Do not use a one-path heuristic for repeated motifs.

Gemmi is used under [MPL-2.0](https://github.com/project-gemmi/gemmi/blob/v0.7.5/LICENSE.txt)
(its [README](https://github.com/project-gemmi/gemmi/blob/v0.7.5/README.md) also
offers LGPLv3). Preserve notices and source availability for the unmodified
covered component when distributing binaries; local NeuroFold files retain
Apache-2.0. Biopython's [license](https://github.com/biopython/biopython/blob/biopython-188/LICENSE.rst)
requires copyright/permission notices and disallows implied endorsement; some
files additionally offer BSD-3-Clause. NumPy uses
[BSD-3-Clause](https://github.com/numpy/numpy/blob/main/LICENSE.txt); preserve wheel
notices, including bundled libraries. No vendored or modified dependency code.
Packaged notices and exact resolved versions are reviewed with the lockfile.

[RCSB Search](https://search.rcsb.org/) supplies experimental-filtered instance
IDs; [Data REST](https://data.rcsb.org/) supplies entry/entity/instance metadata.
Independently require experimental methodology and reported experimental methods;
UniProt cross-references only narrow candidates. Require matching entity UniProt
accession and taxon, but do not infer sequence identity from those annotations.
[RCSB usage policy](https://www.rcsb.org/pages/usage-policy) covers API/archive
data with CC0; retain wwPDB/RCSB attribution and supplied citations. Unknown
third-party rights are not inferred from this policy. No research records are
downloaded during implementation or tests. Follow the
[PDBx/mmCIF guide](https://mmcif.wwpdb.org/docs/user-guide/guide.html) for numbering
and category meaning; this is a deliberately bounded protein import profile.

## Selection, revisions and receipts

Accept entry ID plus the existing explicit entity/label/auth chain, model and
assembly/operator selection, never client URLs. Build HTTPS URLs only for
`search.rcsb.org`, `data.rcsb.org`, and configured `files.rcsb.org`. Reject every
redirect, including same-host redirects; caller must inspect a new selection.
Legacy four-character PDB entry IDs are the supported profile; other identifier
schemes fail explicitly rather than being truncated or redirected.

Import requires a present expected revision `major.minor@revision-date`, a
present authoritative Data API revision before download, matching mmCIF revision,
and an authoritative entry check after parsing/mapping, immediately before
publication. Missing revision fails closed with `RevisionUnavailable`; changed
revision raises `StructureSourceChanged(expected, actual)` for later HTTP 409.
The provider does not offer a multi-endpoint transaction: receipts bracket the
import, not a guarantee against changes after the final check. Fresh entity and
instance metadata are validated too. Methods/entry/entity/instance/polymer/auth
chain must agree across metadata and coordinates.

Every 200 retains exact entity bytes (gzip if HTTP encoded), independent raw
SHA-256/size, receipt, rights and retrieval time. Decompression is a separately
described parsing step, never replacement of the original artifact. Conditional
304 checks retain the original receipt/body and add a distinct validation event
with check time/status/actual headers. No unsolicited or body-bearing 304 is
accepted. `neurofold-structure-import/1` is an additive audit/bundle record;
biological/research v1 fixtures and HTTP schema do not evolve incompatibly.
The audit retains all metadata receipt IDs, parsing/alignment library versions,
coverage counts, selected coordinate identifiers and available model/chain/
assembly/operator inventories. Missing optional metadata remains reasoned absence.

## Resource policy

| Resource | Hard limit / rationale |
| --- | --- |
| Transport | Existing HTTPX 0.28.1; connect ≤3s, total provider operation 15s including gates/retries, ≤2 retries for transport/429/502/503/504; Retry-After ≤5s; two active RCSB operations per process |
| Bytes | 2 MiB original compressed or plain entity, 8 MiB expanded, 16 KiB headers; bounded streaming and single gzip member, no trailing data |
| CIF parsing | One data block, no save frames; ≤1,000,000 table cells, ≤65,536 chars/token; 8 MiB input bounds parser allocation before table checks |
| Coordinates | ≤50,000 atoms, ≤10,000 distinct polymer positions across entities, ≤64 label chains, ≤20 models; reject whole input rather than extracting a fragment to fit |
| Assemblies | ≤32 assemblies, ≤128 operators, ≤256 generated chain copies and ≤200,000 expanded atom instances across declared assemblies; bounded range/product expansion |
| Alignment | Each sequence ≤10,000 residues and length product ≤4,000,000; at most 256 optimal paths; excess ties fail explicitly, no first-path fallback |
| Discovery | ≤100 instance candidates/page, ≤20 pages/session; opaque reference/hash/query/version/limit/order-bound cursor, anchored 1h expiry, 128-entry index; truncated sessions are partial |
| Cache/archive | Existing bounded 128-entry/32 MiB LRU, search 1h, metadata/coordinate 24h, actual 404 5m; no transient negatives/stale fallback; archive 8 MiB raw/16 MiB atomic bundle |

These conservative single-protein bounds limit CPU/memory, not provider data
quality. Parsing has bounded input/work but no preemptive CPU deadline; networking
has a real deadline. No assembly coordinates are expanded in M3. Declared
expansion is still bounded before selection so later consumers cannot accidentally
expand an unrestricted archive. Multi-process rate coordination and large complex
imports require separate work. Exact boundary and rejection tests accompany this
policy; sizes are not validated against real research workloads.

## Mapping and coordinate policy

Align pinned reference (target) and complete selected entity polymer (query).
Use affine semiglobal alignment: match +2, mismatch -1, gap open -10,
extension -0.5, a length-k gap costs `10 + 0.5*(k-1)`; free reference terminal
overhangs (query terminal deletions), other terminal gaps penalized identically
to internal gaps. Epsilon 1e-6; no implicit defaults/substitution matrix. Enumerate
all optimal paths within the cap. A polymer position is uniquely mapped only if
every path gives the same reference position and none gives a gap. Otherwise
retain sorted candidate positions and a reason, including gap alternatives.
Reference positions without a unique assignment receive explicit gap rows whose
reasons distinguish possible ambiguous coverage from absence in every path.
No score threshold establishes homology; cross-reference/taxon and actual
sequences are separately checked, and low identity remains visible.

Scheme author numbers can differ from coordinate numbering, as the
[wwPDB author-number definition](https://mmcif.wwpdb.org/dictionaries/mmcif_ma.dic/Items/_pdbx_poly_seq_scheme.auth_seq_num.html)
explicitly warns. Map `auth_seq_id` uses actual atom-site IDs or deposited scheme
`pdb_seq_num` for coordinate-absent positions; scheme `auth_seq_num` and
`pdb_seq_num` are retained independently in the parse audit. A discrepancy between
scheme PDB numbering and actual coordinates is an error. Missing optional
identifier columns have explicit unavailable reasons, never label-derived values.

Use `_entity_poly_seq`, `_pdbx_poly_seq_scheme`, `_struct_asym`, and `_atom_site`
directly: retain entity, label/auth chain, positive label sequence number, string
author number (including negative/zero), insertion code, component ID, model,
atom ID and alt ID. `?` is unavailable; `.` is not applicable, with context.
Never invent auth numbers from labels. Scheme rows retain unobserved residues;
an absent coordinate does not delete polymer positions. Missing scheme identifiers
stay explicit. Reject contradictory or microheterogeneous polymer identities
with an unsupported-selection error; raw bytes remain intact.

Standard amino acids map to their one-letter code. A modified component maps only
through an unambiguous local `_chem_comp.mon_nstd_parent_comp_id` standard parent;
record the component/parent transformation. Unknown/nonunique parents become X
and ambiguous rows, never exact matches (even X versus X). If that normalization
differs from the Data API canonical polymer, reject the inconsistency rather than
substituting either sequence. No CCD network calls.
Preserve all alternate atoms and models. Coordinate presence means at least one
finite atom with positive occupancy; it does not certify C-alpha/completeness.
Retain atom occupancy/alt IDs; no atom averaging or altloc selection occurs in M3.
Future NF-06 may select highest occupancy, then blank, then lexical alt ID as its
own recorded policy.

Maps select one explicit model/chain and optional assembly copy. Preserve all
available model/chains and assembly generation expressions/operators in the audit.
Expand only operator identifiers (ranges/products); products are named `1*2`,
applied rightmost first using deposited matrices. Validate selected copy membership.
Coordinates always remain **original deposited Cartesian angstroms**; assembly
matrices are recorded as *not applied*. Future viewer/comparison transforms must
be separately recorded and must never replace these raw bytes.

Existing five mapping states are preserved. Mismatches remain mismatch even when
coordinates are missing. Unique equal but coordinate-absent pairs are unobserved.
Tags/polymer insertions and reference gaps remain explicit. Reference coverage is
unique mapped reference positions / full pinned length; polymer coverage is unique
mapped polymer positions / full selected polymer length. Coordinate coverage and
aligned-pair identity have separate numerators/denominators in the audit; ambiguous
candidates are excluded. Never use atom counts as sequence coverage.

## Immutable publication and composition

Compose `RcsbCatalog` with existing injected transport/clock/artifact/source archive,
`StructureService` with core protocols and selected parser/mapper, and
`FilesystemStructures` with the existing `FilesystemStore`. No API wiring.
Publish source artifacts/receipts and reference dependencies before one atomic,
checksummed descriptor/map/audit bundle. Both map lookup and structure lookup
read that same committed bundle. Conflicts fail, identical repeat writes are
idempotent; interrupted staging can leave orphan dependencies but no visible
partial import. Reads verify actual pinned reference, map/selection/raw hashes,
receipt/artifact dependencies and audit identities. Restart/cache eviction/provider
outage cannot invalidate retained original bytes or maps. Atomic hard links/fsync
and a trusted private ignored filesystem root remain required.

## Python composition

An existing pinned reference is required; no live call occurs during construction:

```python
from pathlib import Path
from neurofold.adapters.biological.alignment import PolymerMapper
from neurofold.adapters.biological.mmcif import MmcifParser
from neurofold.adapters.biological.rcsb import RcsbCatalog
from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.adapters.biological.structure_storage import FilesystemStructures
from neurofold.adapters.biological.transport import HttpxTransport
from neurofold.application.structures import StructureService

archive = FilesystemStore(Path("data/biological"))
provider = RcsbCatalog(HttpxTransport(), archive.artifact_store, archive)
structures = FilesystemStructures(archive)
service = StructureService(provider, archive, MmcifParser(), PolymerMapper(), structures)
# provider.discover(archive.get(reference_id), limit=20)
# Inspect a candidate and explicitly choose model/assembly/operator.
# service.import_selected(reference_id, entry_id, selection, inspected_revision)
# service.get(structure_id) is an offline integrity-checked read.
```

Use the same archive containing reference dependencies, or retain those complete
dependencies in the configured archive first. Synchronous calls belong outside an
asyncio event loop. There is no startup registration, automatic refresh, export or
archive garbage collection. Original artifacts may be gzip HTTP entities; future
M4 artifact serving must expose the recorded media type and explicit decoding
semantics rather than pretending compressed bytes are plain CIF.

Source revision, selected identity and provider schema errors remain distinct from
complete empty discovery. Candidate-specific failures return partial pages with
warnings; search failure is unavailable, never complete empty. A 204 search retains
its actual empty entity receipt and is cached for one hour. Search pagination
shares its 15-second upstream deadline with metadata hydration on that page;
imports consist of separate bounded inspection, download and final-check calls.
Local parsing/mapping/serialization/fsync remain outside network deadlines.

Offline tests and exact local acceptance identities are in
[M3 evidence](testing/nf02-m3-evidence.md). The official entry/entity/instance
schemas were reviewed as documentation only at M3. The later
[operational probe](testing/nf02-operational-evidence.md) exercises one public pair;
independent scientific approval remains open. Current adapter/parser identities
are `rcsb-rest/2`, `neurofold-mmcif/2` and unchanged
`affine-semiglobal-consensus/1`. The parser accepts entries without the optional
CCD parent column, recording `component_parent_column` and per-modification
`component_parents` metadata explicitly. Missing parents never establish a known
residue or unique correspondence; existing `modified_residues` item fields remain
compatible. RCSB `chemical/x-cif` responses still undergo the full mmCIF identity,
revision and bounded parsing checks. Selected version/chemistry and
resource profiles intentionally reject unsupported cases; expanding support needs
new fixtures, reviewed policies and versioned method changes.
