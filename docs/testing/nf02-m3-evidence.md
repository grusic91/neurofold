# NF-02 M3 acceptance evidence

Date: 2026-11-10. Scope: opt-in Python experimental discovery, selected mmCIF
import and immutable residue maps. Implementing-agent review of source,
documentation and local offline results; no independent scientific/domain approval
or live-provider compatibility is claimed. [M3 decisions, behavior and limits](../structure-import.md)
are authoritative. M4 routes/frontend integration remain open.

## Baseline and compatibility

The working tree was clean at `3014e5b2bc21a78bb02f2f0a2e8cb67b28127cd6`
(`Complete NF-02 M2 UniProt lookup and reference pinning`). History confirms
NF-01, NF-08 M1, NF-09 M1 and NF-02 M1/M2. M2 source/evidence was inspected and
its baseline full suite rerun: **351 passed, 96.96% combined coverage**. There was
no uncommitted work to overwrite. No commit, push, publication, deployment or PR
was performed. LICENSE and attribution are unchanged.

Application/package version remains 0.1.0. Existing biological/research/canonical
versions, all twelve previous fixture inventory entries and bytes, HTTP DTOs and
both JSON Schemas are unchanged. M3 adds `neurofold-structure-import/1`,
`rcsb-rest/1`, `neurofold-mmcif/1` and `affine-semiglobal-consensus/1`; the new
bundle/audit composes existing v1 descriptors/maps rather than changing them.
Gemmi 0.7.5 and Biopython 1.88 are explicit locked CPU dependencies, with NumPy
2.5.4 transitive. Every existing dependency resolution is retained. HTTPX 0.28.1
remains the production transport; httpx2 remains test-only.

| Exact file identity | Raw SHA-256 |
| --- | --- |
| `backend/uv.lock` | `50a0889ee54acca7108e15eba7772b9402ed17a634872a8c132a8504abf5bdad` |
| `frontend/package-lock.json` | `895d5c748dd378082bbf7860dc545fe14b734cf7d248e17081315b07cfc585de` |
| `docs/testing/fixtures.json` | `268abc8abca351f3a9042c22f7de73846a6b89553c56a6b73f1cbdb9fd5863a8` |
| `docs/schemas/neurofold-biological-http-1.schema.json` | `acde8893ea3997650d7dffeb198596b177442f81db53b29ac94677ba0f9bd71c` |
| `docs/schemas/neurofold-research-1.schema.json` | `1046eb7bd6cf809f078138e189ebfeeb55e95e8085f466e288aadb692f30fcba` |
| `backend/tests/fixtures/structure-synthetic-v1.cif` | `5cab5e1e7834c06363f4d4d259ad71acaeabeecc32d1cd1054fd64e13ef07282` |
| `backend/tests/test_structures.py` | `69265f753df1a9450ae4054531cbcd1927892bdd7b73a9576a79d07cda868cbd` |

Working-tree change identity (**22 changed/new files, excluding this evidence**):
`3cf0b84ade1ef13b7e689186bc763ecfdb6a62239050b35566cc97565ffec141`.
This is SHA-256 of compact sorted-key UTF-8 JSON containing the path-sorted array
of `{"path": relative_path, "sha256": raw_file_sha256}` for modified and
untracked nonignored files relative to the baseline. The evidence file is excluded
to avoid circularity; recompute after edits. This identifies local bytes, not a
commit, release, CI run or independent attestation.

## Decisions and acceptance

The decision guide was written before orchestration. Gemmi CIF tables were chosen
over hierarchy normalization/MMCIF2Dict for syntax validation and exact identifier
access; Biopython optimal-path enumeration was chosen for explicit tie handling.
Official library documentation/licenses and installed wheel license metadata/files
were reviewed. Gemmi uses the MPL-2.0 option; Biopython retains its permission/
copyright notices and per-file BSD alternatives; NumPy's wheel declares
`BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`. Preserve packaged notices
and covered-source availability obligations on distribution; nothing is vendored.
See the [source review](../source-licensing.md#nf-02-m3-review-2026-11-10).

| M3 requirement | Evidence / result |
| --- | --- |
| Experimental discovery | Search API explicit experimental content filter and bounded instance pagination; Data API independently validates entry methodology/methods plus entity/instance/accession/taxon; computed, inconsistent and unsupported IDs rejected; multiple candidates, complete empty, partial and unavailable remain distinct |
| Fresh import | Explicit entity/label/auth chain/model/assembly/operator selection; no client URLs; known expected revision required; fresh entry/entity/instance metadata, matching CIF revision and authoritative entry revalidation after parsing/mapping and before publication; missing versions fail closed and changed versions expose typed expected/actual conflict |
| Transport/cache | Existing HTTPX streaming/deadline seam; injected transport/UTC+monotonic clock/sleep/jitter/IDs; two process-wide RCSB request slots; 15-second upstream operation budget, ≤2 retries for selected transient failures, capped Retry-After; redirects always rejected; bounded LRU/cursors and no stale fallback or transient negatives |
| Original bytes and 304 | Exact original entity bytes/hash/size and rights retained, including HTTP gzip; separate decompression/parse audit; 304 check events refer to unchanged original 200 receipt/body/retrieval metadata and record actual check time/headers; unsolicited/body-bearing 304s rejected |
| CIF identifiers | Gemmi category tables preserve entity, label/auth chain, label sequence, scheme author/PDB number, atom-site auth number, insertion, component, model, atom/alt ID and occupancy; `?`, `.`, absent identifier columns and coordinate-absent residues remain explicit |
| Mapping | Actual pinned reference and selected polymer verified; independent expected maps for unique fragments/tags/substitutions/internal gaps and repeated domains; all bounded optimal paths contribute candidates, including gap alternatives; excess ties fail rather than choosing a first path; all five v1 states preserved |
| Chemistry/coordinates | Unambiguous local standard modified-residue parent normalization is recorded; unknown parents become X/ambiguous only when source polymer agrees, otherwise reject; all alternates/models retained, no averaging; positive-occupancy finite atoms define coordinate presence, independently of sequence mismatch |
| Assemblies/limits | Original deposited Cartesian angstrom frame preserved; assembly expressions/operator paths/matrices retained as not applied; bounded products/ranges and copy membership checked; byte/header/gzip, cells/token, atom/residue/chain/model, assembly/operator/expansion and alignment limits tested with exact small boundaries and lowered configurations |
| Persistence/offline | Existing archive reused; dependencies retained before checksummed atomic descriptor/map/audit bundle; identical/concurrent writes idempotent, conflicts rejected; interruption leaves no visible structure; integrity/missing-dependency failures explicit; reopened store reads original references/receipts/artifacts/maps after cache loss without provider access |
| Architecture/scope | Core standard-library-only test passes on both Python versions; application imports core protocols; scientific libraries imported lazily inside adapters; production `/health` and OpenAPI unchanged; no operational `/v1`, frontend lookup, viewer/comparison engine, model/inference/database/auth/jobs |

Fixture inventory now has **14 entries**. The new authored CIF is **2,913 bytes**;
new inline fixture/test source is **52,819 bytes**, both under 64 KiB. The fictional
six-residue construct, two models/chains, alternate atoms and assembly operators
were authored locally. No protein record, sequence, downloaded structure, research
dataset, weights or generated prediction was fetched. Large/bad inputs are generated
in memory. Existing socket/DNS guards apply to every backend test. Tests establish
software semantics and explicit uncertainty, never biological accuracy or causality.

## Environment and validation

macOS 27.0.1 (26A434), Darwin arm64 CPU-only; Python 3.12.16 default environment,
Python 3.13.2 in `/private/tmp/neurofold-m3-py313`; uv 0.13.7; Node 24.5.0,
npm 11.5.1, existing pinned Playwright 1.65.0/Chromium. Commands used
`UV_CACHE_DIR=/private/tmp/neurofold-uv-cache`. Python 3.13 used
`UV_PROJECT_ENVIRONMENT` and `--python /private/tmp/neurofold-m2-py313/bin/python`;
default `.python-version` and the 3.12 environment were preserved.

| Command / environment | Result |
| --- | --- |
| `uv sync --locked` (backend, default 3.12) | pass; 45 packages resolved, 43 installed checked |
| `uv run --locked ruff check .` | pass |
| `uv run --locked ruff format --check .` | pass; 37 files |
| `uv run --locked mypy src tests` | pass; 37 files |
| `uv run --locked pytest` (3.12.16) | **503 passed**, including 152 new M3 cases; **96.84%** combined statement/branch coverage; existing ≥90% gate unchanged |
| Separate locked 3.13 sync, Ruff/format/mypy and full pytest | pass; **503 passed**, **96.84%** combined coverage; includes standard-library-only core import |
| `npm ci` | pass; lockfile unchanged |
| `npm run lint` / `npm run typecheck` / `npm run build` | pass |
| `npm run test` | 12 passed |
| `npm run test:browser` | 8 passed, Chromium and WebGL-disabled Chromium |
| `docker compose config --quiet` | pass |
| Docker `colima` | unavailable; `/Users/gasperus/.colima/default/docker.sock` missing |
| Docker `colima-arm64` | unavailable; `/Users/gasperus/.colima/arm64/docker.sock` missing |
| Docker `default` | unavailable; `/var/run/docker.sock` missing |
| Container builds/service/proxy smoke and Linux execution | not run; no daemon across all configured contexts |
| Complete tracked/new source diff, frozen identities, local documentation links and `git diff --check` | reviewed/pass |

Initial package/3.13-wheel resolution under restricted DNS failed; permissioned
registry access succeeded with the same selected lock. Browser preview initially
failed binding loopback (EPERM), then all eight offline tests passed with local
preview permission. Initial lint commands from root could not locate backend tools;
all required final commands were run from their prescribed directories. New tests
caught fixture inventory omission, an incorrect CanonicalObject accessor, and an
overly narrow test error expectation during audit validation; these were corrected.
No frozen fixture/expectation was rewritten and no test gate was relaxed.

Final review distinguished scheme author numbers from coordinate IDs using the
wwPDB dictionary and added an independent regression. It also checked absent
identifier columns, metadata citations against official integer PubMed schema,
source revision errors, complete coverage and bundle checksums. The final suites
above include these changes. CI already runs the same locked checks on Python
3.12/3.13 and Node 24 plus Linux container smoke; no workflow change was needed.
No CI run ID exists because no push was performed.

## Remaining gates

**M3 acceptance: pass for the documented offline Python profile.** No live-provider
schema/behavior probe, independent domain/scientific validation, Linux execution or
container acceptance is claimed. Official RCSB Search/Data/entry/entity/instance
schemas, source policy and library documents were read without fetching biological
records. Some direct dictionary item URLs timed out; accessible official dictionary
pages supplied the numbering distinction, and compatibility is still unproven.

Unsupported extended PDB IDs, microheterogeneous polymers, excessive alignment
ties, larger complexes and unreviewed chemistry fail explicitly. Bounds are
conservative rather than calibrated on real research workloads. Parsing is bounded
by input/work counts, not a preemptive CPU timeout. Assembly matrices are retained
without transformed coordinate output; future NF-05/NF-06 own rendering/atom
selection/fitting and separately recorded transformations. M4 owns routes, HTTP
status/error translation and frontend integration. Full scientific manifests,
exports, retention/backup administration, multi-process rate coordination and
scientific release approval remain future work. Storage requires atomic hard links/
fsync under one trusted local OS account; it is not a multi-user database.
