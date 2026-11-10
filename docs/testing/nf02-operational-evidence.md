# NF-02 operational compatibility evidence

Date: 2026-11-10. Implementing-agent execution, starting from clean
`0ec20f5cdc6b6836d49bde1202a4a48b26855bfd` (NF-02 M4 integration).
This supplements the historical [M4 evidence](nf02-m4-evidence.md); it does not
retroactively change that record's unexecuted environment gates.
**Pass for the bounded operational scope below. Independent scientific validation
is incomplete.** No biological accuracy, prediction, comparison or clinical claim.

## Identity and retained evidence

Local evidence root (ignored, private; real records must stay outside git):
`outputs/nf02-ops-20261110-gx3nfm0e/`.
It contains original live responses, published archives, all failed attempts,
synthetic regression logs, Linux/build/smoke logs, source snapshots, image/runtime
metadata and SHA-256 inventories. Retain this directory with the evidence record.

- Executed source snapshot: `source-02.tar`, 139 files; archive SHA-256
  `2eb8273f5ab50530609f70ec1966d3c6739b01c7e95442a1c8e15c5c0501f48d`.
  `source-02.json` records every file size/hash and base revision; tree identity
  `c0adf186fda9df6d1567387403431227f26862f46687187c6548a65136711dd4`.
  All current production Python, probe, runner, smoke and fixture-inventory bytes
  were compared with this tested snapshot and match. Later edits are documentation.
- Review change identity: **`47d397662b0458bbf539fd30fd8572be86dc77681d63047bf5de7f50317d9bfb`**.
  `reviewed-change-manifest.json` hashes the sorted JSON array of current
  repository `{path, sha256, byte_size}` entries, including untracked implementation
  files and excluding this evidence file to avoid a circular identity. It also
  records the base revision and tracked binary-diff hash. This identifies the
  uncommitted review state, not a nonexistent commit.
- Retained evidence inventory SHA-256: **`8a2d4a8ebe58d06d563a38fcad498cc3089ea5d0dce89e6f6e9e745d14967ba1`**;
  `inventory.json` lists all retained files except itself. Attempt inventories
  similarly exclude themselves. This evidence file is outside that artifact tree.

No dependency/lock, LICENSE, frozen v1 provider/molecular/schema fixture or core
contract was changed. Source-backed fixture inventory hashes were refreshed.
Application version remains 0.1.0. Compatibility corrections deliberately identify
`uniprot-rest/3`, `rcsb-rest/2`, `neurofold-mmcif/2`; alignment remains
`affine-semiglobal-consensus/1`. Existing retained audit payloads are not rewritten.

## Locked checks and container execution

| Executed check | Outcome |
| --- | --- |
| Linux ARM64 Python 3.12.16 | Locked sync, Ruff check/format, strict mypy including probe/infra scripts: pass; **560 pytest tests**, **96.75%** combined coverage |
| Linux ARM64 Python 3.13.18 | Same checks: pass; **560 pytest tests**, **96.75%** coverage |
| Linux ARM64 frontend | `npm ci`, lint, typecheck, build: pass; **36** component tests, **12** Chromium browser tests (normal/no-WebGL), **1** actual local synthetic API/Vite-proxy browser workflow |
| macOS ARM64 Python 3.12.16 | Ruff check/format, strict mypy and **560 tests**, **96.75%** coverage: pass |
| Development containers | Both locked images built; normal backend health, HTML and `/api/health` all HTTP 200; synthetic biological workflow, audits and exact original-byte downloads passed through proxy |
| Retention | Forced backend recreation changed container `29c9198d672a` → `2fb1227da237`; same retained reference/structure payloads and original bytes passed afterward |
| Compose validation | Normal and synthetic override configurations pass |

Linux runner: kernel `6.8.0-100-generic`, aarch64, Debian-based Node image,
uv **0.13.7**, Node **24.22.2**, npm **11.19.1**. Runner image:
`sha256:987d9fd64f8aa0e23e27b1639642fdc5d5f1ed1828fcdd4738d497164431f1ad`.
This is local Linux execution in the native ARM64 Colima VM, not a GitHub Actions
run or x86-64 validation. CI remains configured for Python 3.12/3.13, Node 24 and
container checks. Base tags are mutable; exact inspected images are retained.

Docker client **29.5.2**, server **29.2.1** (`linux/arm64`). Isolated project
`neurofold-ops-20261110`, loopback ports backend **18000**, frontend **15173**.
Final image identities:

- Backend: `sha256:8fecd83234ca2f6a9528c209f51931281af4cd0c0cb9a12c3a1803e7a995d711`.
- Frontend: `sha256:b11a4018a2ad067f5bfb534c107dc70aa7293080f002e046bd7c484d69793614`.

Backend ran as uid/gid **999**, archive `/app/data/archive` mode **0700**, owner
**999:999**, named volume `neurofold-ops-20261110_biological-archive`.
`container-records-final.json`, before/after container metadata, image inspect and
volume/permission records retain the exact IDs and runtime evidence. Services and
project network were removed with `down` **without** deleting the volume. The
task-started ARM64 VM was returned to stopped; active Docker context stayed
`colima`. Restart profile `arm64` to inspect retained images/volume.

## Live upstream probe and failure-first regressions

Explicitly authorized public sample: canonical **UniProt P69905**, taxon **9606**;
**PDB 1A3N**, entity **1**, label/author chain **A**, model **1**, explicit asymmetric
unit, no assembly/operator applied. The discovery page size was **1**; it returned
`1A00/A`, while the predeclared `1A3N/A` was inspected independently, not selected
as the first discovery hit. All attempts used the production HTTPX transport,
services/parser/mapper and actual production routes via ASGI on macOS.

| Attempt | Retained outcome and action |
| --- | --- |
| `live-01` | Lookup 502 after one provider request: a 200 response declared one gzip layer but contained two. Original bytes/headers retained. Authored nested-gzip/negotiation regression failed before the fix. Diagnostic public identity-encoding requests returned valid JSON. Request identity encoding rather than recursively guessing undeclared layers; strict malformed-gzip rejection remains tested. |
| `live-02` | Lookup/pin/discovery succeeded; import 502. Retained-coordinate diagnostics also exposed the parser's incorrect requirement for an optional CCD parent column. Authored entry-style synthetic CIF regression failed before making the column optional. Missing parent metadata remains explicit; unknown residues remain ambiguous. |
| `live-03` | Import still 502. Offline replay of the retained transport trace isolated RCSB `chemical/x-cif` rejection. Authored compressed-CIF regression failed before adding that media type to the coordinate-response allowlist. Full bounded mmCIF identity/revision validation still applies. |
| `live-04` | **Pass**, 17 provider requests; 2026-11-10 **15:39:09.873255Z–15:39:18.988164Z**. Lookup 200, pin 201, discovery 200, import 201, both audits/original 200. New composition with provider access forbidden reopened reference, structure, audits and identical original bytes. |

The first Linux run also caught an audit dictionary compatibility error introduced
during the optional-parent change (558 pass/1 fail). The correction preserves
existing `modified_residues` fields and exposes explicit parent metadata separately
under parser profile 2. The unchanged historical modified-residue test and new
ambiguity regression both pass. Final focused regressions/probe tests: **9 pass**.
All original failure and correction logs are retained; no downloaded bytes became
synthetic fixtures. Five authored compatibility tests and three probe tests account
for the increase from 552 to 560 backend tests.

Successful source identities: UniProt release **2026_04**, entry version **220**,
sequence version **2**, canonical length **142**; sequence SHA-256
`14725a10598943a7aa719eed7d24c7fee599192a6c63c75b051ee6f156341242`.
RCSB revision **1.4@2026-08-12T00:00:00.000+00:00**.
Pin revalidation and all five recorded structure checks returned **200** (no
claim that conditional 304 was observed on this live path). Receipts retain exact
source/version/license/citation metadata and original response identities.

Imported **141** selected polymer residues; mapping **141 exact, 1 unmapped**,
reference/coordinate-reference coverage **141/142**, polymer and unique aligned-pair
identity **141/141**, one optimal path. Original deposited Cartesian coordinates
remain in angstroms, no transform applied; parser counted **4,997** atoms across
the entry. These are observed software mapping outcomes, not independently reviewed
biological conclusions. The original compressed entity is **136,330 bytes**,
SHA-256 `fecbe79436b0513d9be4ab57fe5d05d81271978cc3247daa273b98ae4b29da93`;
download preserves `application/gzip` bytes and has no Content-Encoding.

Live runtime: macOS **27.0.1 ARM64**, Python **3.12.16**; FastAPI **0.162.2**,
Pydantic **2.14.3**, HTTPX **0.28.1**, Gemmi **0.7.5**, Biopython **1.88**,
NumPy **2.5.4**, Uvicorn **0.54.0**. Full package/lock/runtime and request/response
metadata are in each report. Lock SHA-256 identities:
backend `50a0889ee54acca7108e15eba7772b9402ed17a634872a8c132a8504abf5bdad`;
frontend `895d5c748dd378082bbf7860dc545fe14b734cf7d248e17081315b07cfc585de`.
`live-04/report.json` SHA-256
`31980cf0720ed8d53b42ac53dc58344d87fef377597dc5d8b21365812f4c4d27`;
attempt inventory `af66b1d062af5ba5ae49f8c8ec047bfe5596506cfb3e5f4f3563690917a3630c`.

## Scope, primary references and remaining gates

The [reproduction guide](operational-checks.md) keeps opt-in live execution separate
from normal offline tests. These results establish deployment and upstream
compatibility only for the recorded platform/sample/time. No live browser or
live-provider-from-container workflow was run. One discovery page does not test
all search paths, record types, assemblies, provider failures or future releases.
The gzip observation concerns the end-to-end network path; its origin is not
attributed to UniProt alone. No independent domain reviewer has signed off.

Primary references reviewed for the fixes/sample:
[wwPDB optional parent item](https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/Items/_chem_comp.mon_nstd_parent_comp_id.html),
[IUCr CIF MIME types](https://journals.iucr.org/services/filetypes.html),
[RCSB 1A3N](https://www.rcsb.org/structure/1A3N),
[RCSB archive CC0 policy](https://www.rcsb.org/pages/usage-policy).
Retained source rights remain separate from Apache-2.0; this is not a new legal
review or authorization to redistribute original source records.

The [scientific review plan](scientific-review.md#release-gates-and-current-plan)
now identifies foundation, NF-04 prediction, NF-06 comparison and NF-08/NF-09
release gates, required independent review evidence and reopening conditions.
Operator/reviewer assignments, panel approval and numerical tolerances remain
incomplete. These gates must close before accepting real prediction/comparison
results. NF-03 pure domain logic may proceed independently. No commit, push, PR,
publication or deployment was performed.
