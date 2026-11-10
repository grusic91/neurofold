# Biological source licensing and attribution inventory — NF-02 M1

Policy review date: 2026-11-10. This inventory records current primary-source
statements and obligations for future NF-02 clients. It is not a receipt for
retrieved research data or permission to relicense third-party content. The
repository LICENSE and attribution remain unchanged. No external biological
content is shipped in M1; all provider/contract fixtures are authored synthetic
examples under Apache-2.0.

| Source / scope | License / review basis | Attribution and preservation | Runtime decision |
| --- | --- | --- | --- |
| UniProtKB database content | CC-BY-4.0. The current [UniProt API documentation](https://www.uniprot.org/api-documentation/support-data) states that copyrightable database content uses CC BY 4.0; [UniProt's dataset declaration](https://sparql.uniprot.org/.well-known/void) independently identifies that license for the UniProt graph. The [help license page](https://www.uniprot.org/help/license) returned only a JavaScript fallback during this review. | Credit The UniProt Consortium; retain source/accession/version, license link, supplied notices and citations. Identify extraction/normalization/other changes, retain previous change notices and avoid implying endorsement, following the [CC BY 4.0 terms](https://creativecommons.org/licenses/by/4.0/). Recheck the help/citation pages before shipping the client/export. | No actual artifact reviewed or redistributed. Future artifact rights are decided from the applicable terms and retained attribution; they must not inherit Apache-2.0. |
| RCSB programmatic APIs and PDB archive files | CC0-1.0, explicitly stated for archive files and API data by the [RCSB usage policy](https://www.rcsb.org/pages/usage-policy). | Retain RCSB/wwPDB source, entry/entity/revision and primary structure citations when supplied. RCSB encourages credit to original structure authors; follow the [citation policy](https://www.rcsb.org/pages/policies). Do not fabricate missing citations. | No actual artifact reviewed or redistributed. Origin must still be validated as experimental; license openness does not make computed models experimental. |
| RCSB website articles, images and unrelated third-party resources | Scope-specific terms; no blanket CC0 assumption. The usage policy distinguishes website text and Molecule of the Month materials from API/archive data. | Retain each original notice and obtain separate applicable terms before reuse. | Outside NF-02 M1; rights unknown unless separately reviewed. |
| NeuroFold synthetic provider JSON, contract records and inline adversarial inputs | Apache-2.0, authored for this repository by NeuroFold contributors. No downloaded sequence/structure, model output or patient data. | Keep project LICENSE and attribution, fixture inventory and synthetic labels. No provider scientific citation exists for fictional records; mark not applicable with a reason. | Synthetic fixture descriptors record allowed redistribution with authorship basis. This permission applies only to these authored bytes. |

Future SourceReceipt records reuse NF-08 license/citation ReferenceCollections,
retrieval time, raw ArtifactDescriptor and exact-byte hashes. Each artifact's
ArtifactRights retains independent license and attribution Metadata,
redistribution (`allowed`, `prohibited` or `unknown`) and a nonblank decision
basis. This inventory is a review aid; adapters must populate actual received
notices, citations and source versions, and exports must respect each artifact's
rights. Missing terms/citations/versions stay unavailable with reasons rather
than being filled from an unrelated source. Unknown rights stay `unknown` until
a review establishes permission; an absent license cannot authorize export.

No parser, alignment, transport, model, weight or external dataset dependency is
added in M1. Review those artifacts independently when selected. Linked databases
and third-party annotations require their own scope/terms review. NF-08 export
work must retain source notices and transformation lineage, and explicitly list
omitted/prohibited/unknown-rights artifacts. A checksum is byte identity, not a
license or evidence of scientific validity.

## NF-02 M2 review (2026-11-10)

The source policy remains CC BY 4.0 for copyrightable UniProt database content,
as stated by the official API support documentation above. M2 receipts retain
the license URL, The UniProt Consortium attribution, source URL, exact raw bytes,
versions and any supplied copyright/citation cross-references. Extraction is
identified; original sequence text is unchanged. Missing citations/versions remain
explicit, and linked third-party annotations require their own review before
reuse beyond this retained source response. Synthetic test transport artifacts
are labeled synthetic; their authored fixture license does not grant rights to
real external content.

Production transport is now explicitly `httpx==0.28.1`, under
[BSD-3-Clause](https://github.com/encode/httpx/blob/0.28.1/LICENSE.md); preserve its
packaged notice. Its locked runtime additions are [httpcore (BSD-3-Clause)](https://github.com/encode/httpcore/blob/1.0.9/LICENSE.md) and
[certifi (MPL-2.0 certificate bundle)](https://github.com/certifi/python-certifi/blob/master/LICENSE), with their own packaged notices. No
parser/alignment/model/weight dependency was selected. UniProt help/license and
several help/API pages still exposed a JavaScript fallback on review; the API
support statement, dataset declaration and CC terms remain the policy basis.
No retrieved biological content is committed or exported by this milestone.
See [M2 behavior and bounds](uniprot-lookup.md).

## NF-02 M3 review (2026-11-10)

Rechecked [RCSB API/archive CC0 policy](https://www.rcsb.org/pages/usage-policy),
[Search documentation](https://search.rcsb.org/), [Data API](https://data.rcsb.org/)
and official entry/entity/instance schemas. These are documentation/schema reads,
not retrieval of biological records. Receipts retain wwPDB/RCSB attribution,
CC0 URL, exact source/query/revision and supplied primary DOI/PubMed identifiers;
full citation/entry/entity/instance annotations remain in immutable raw responses.
Unrelated linked third-party rights require separate review and remain unknown.
Fictional transport artifacts explicitly carry synthetic/Apache-2.0 rights.

New locked components: Gemmi 0.7.5 (selected MPL-2.0 option; packaged notice and
covered-source availability on binary redistribution), Biopython 1.88 (Biopython
License Agreement, with per-file BSD alternatives; retain copyright/permission
notices and do not imply endorsement), and transitive NumPy 2.5.4 (wheel metadata:
`BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`). Preserve all packaged notices,
including bundled code; no library source is modified or vendored. See the
[comparison and primary license links](structure-import.md#libraries-and-source-review).
The installed wheel license files were inspected separately from behavior tests.
The project LICENSE/attribution are unchanged. Larger exports/distribution still
need their own artifact-specific rights and notice review.


## NF-02 M4 attribution integration (2026-11-10)

No provider, model, weight, dataset or package dependency was added in M4; the
M2/M3 reviewed source policy and packaged-library obligations above remain the
basis. This milestone does not claim a new live-provider compatibility or legal
review. Operational HTTP/UI now expose each receipt's source, version, evidence,
license/attribution, supplied citations and absence reasons, plus exact original
registered downloads. Sources remain distinct from NeuroFold's Apache-2.0.
Synthetic UniProt compositions now explicitly use NeuroFold contributor and
Apache-2.0 rights (as RCSB synthetic compositions already did), rather than
attaching real UniProt rights to authored test bytes. Frozen examples are unchanged.
Audit HTTP projections omit unreviewed response headers; original checks and
bytes remain immutable in the private archive. See [integration](integration.md)
and [M4 evidence](testing/nf02-m4-evidence.md).
