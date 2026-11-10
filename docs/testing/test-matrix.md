# Test matrix

Status covers NF-09 M1, NF-02 M1–M4 integration and NF-03 M1/M2 pure domain
and immutable storage.
“Planned” means no implementation or acceptance evidence exists yet.
Mandatory PR CI uses locked installs, Python 3.12/3.13 and
Node 24. Backend coverage remains at least 90%; lint/types/build are additional
checks and never replace behavior tests.

| Layer / owner | Implemented now | Required additions / negative paths | Execution and gate |
| --- | --- | --- | --- |
| Pure core / NF-08 M1, NF-03 M1/M2 | Canonical byte/hash golden vectors, immutability, strict wire/schema versions, explicit absence, evidence/lineage, failed/cancelled skeletons; all core imports without site-packages; strict bounded substitutions, direct/codec invariants, entire reference alphabet/error precedence, exact one-change/hash construction, ordered zero/multiple differences and unequal-length rejection, full pinned numbering independent of structure; M2 four-field identity golden bytes/ID and strict persisted definition codecs | NF-03 M3 HTTP contracts; NF-04 lifecycle; NF-06 selections | `uv run --locked pytest`; offline CPU; mandatory |
| API / NF-01, NF-02 M1 | `/health` body/headers/OpenAPI, 405, unknown-route 404; in-process ASGI under network guard; separate NF-02 harness for eight proposed operations, DTO/frozen schema, envelope/status shapes, 201/Location, placeholder bytes/checksums and response validation | M2 implements Python lookup/source-change/storage behavior; operational `/v1` routes, HTTP translation and streaming remain M4; M3 imports are Python services; later idempotency/cancellation conflicts | Backend pytest; mandatory as each API lands |
| Adapter contracts / NF-02 onward | Core catalog/repository protocols, authored provider-shaped JSON and NF-08 receipt/hash checks; M2 UniProt/storage implementations with fake transports/clocks and socket/DNS guards | M2 covers pagination, malformed upstream, retry/budget/size/concurrency, cache/304 and immutable offline pinning; M3 covers experimental-only RCSB/partial discovery, revisions/304, bounded CIF and residue mapping | Offline injected transports/temp files; backend pytest mandatory |
| Biological contracts / NF-02 M1 | Frozen reference/structure/map records; canonical/raw/sequence hash separation; strict versions; five mapping states, author/label distinctions, insertion/negative numbering, gaps/tags, alternate selection identity, missing maps/rights/metadata | M2 tests immutable full-reference snapshots; M3 covers actual-reference map consistency, experimental origin/import, author/label/coordinate identities and all five states; no biological inference from fixtures | Backend pytest; offline CPU; mandatory |
| Application/persistence / NF-03/04/08 | M2 reference service and immutable filesystem archive, atomic publication/conflict/interruption/corruption tests; M3 adds checksummed atomic descriptor/map/audit bundles and restart/offline integrity checks; NF-03 M2 adds pinned expected-hash precedence, exact reference-aware identity, complete derivation verification, synchronized thread/process duplicate publication, failed/abrupt writes/restarts, self-consistent tampering and missing/corrupt dependencies; no database/worker | Fake catalogs/repositories/clocks/dispatchers; temporary SQLite/filesystem, restart/fencing/races/cancel/timeout, atomic artifacts and corruption; preserve API → core ← adapters | Offline CPU; NF-03 M2 children explicitly deny sockets/DNS and run without site-packages; M3 variant HTTP planned |
| Scientific numerics / NF-06 | M3 bounded Gemmi CIF parsing, affine Biopython alignment with all bounded optimal ties and an authored Cartesian fixture; no fitting/comparison engine | Known rigid transform, deformation, mirror, ambiguity/gaps; independent RMSD/coverage denominators, units/transforms, missing atoms and justified tolerances | Tiny analytic synthetic fixtures; planned M2; numerical correctness alone is not biology |
| Component / NF-01 | Checking/online/unavailable, HTTP/network/JSON/schema failures, five-second timeout, abort on unmount; transport guard regressions | NF-05/07 accessible forms, disambiguation, races, polling/cancel/resume/retry, synthetic badges, chain/sample/mutation selection, absent confidence; fake viewer controller | `npm run test`; Vitest/RTL/jsdom, no services; mandatory |
| Browser / NF-01 | Built status page and role-based assertions; native Chromium success/error/invalid contract; HTTP/WebSocket guard probes | Full UI/API/separate fake worker slice, export verification, recovery/integrity; planned NF-09 M3 | `npm run test:browser`; mocked HTTP; Chromium and Chromium with WebGL disabled; mandatory |
| Actual viewer / NF-05 | Not implemented: no Mol* dependency or viewer | Small separately scoped actual-Mol* suite with synthetic bytes; mapped selection/overlays, missing confidence, context loss and accessible no-WebGL recovery | Chromium software rendering in Linux CI to be validated with NF-05; current no-WebGL project only checks the scaffold, not viewer fallback |
| Containers / NF-01 | Existing CI builds non-root CPU services, checks both HTTP services and Vite `/api/health` proxy | Record current local availability; perform builds/smokes whenever daemon available | `docker compose config --quiet`, build/start/wait, health + page + proxy, cleanup; Linux CI mandatory |
| Live upstream diagnostics | None | Separate opt-in probes of pinned/provider contracts, never default PR fixtures or authoritative contract acceptance | Planned; no live calls in ordinary tests |
| Real model / NF-04, NF-09 M4 | None; no Boltz-2 installation | Reviewed model/weights/licenses/MSA, measured limits, public panel and locked Linux/NVIDIA runtime; failures/absence/nondeterminism retained | Explicit opt-in separate GPU environment; required for real scientific MVP, never base API CI |

Frontend currently consumes only the health DTO. It does not implement research
manifest types or hashing. Cross-language NF-08 golden-vector and DTO/schema
version tests become mandatory when frontend identities/manifest consumption are
introduced; M1 does not duplicate unconsumed contracts into TypeScript.

Fixture inventory/hash checks run in backend pytest. Synthetic health responses
exercise UI behavior, not proxy integration; the container smoke layer owns the
real proxy check. An integrated fake prediction/export preview remains M3 and
cannot be inferred from these status-page tests. Real scientific acceptance
remains a separate M4/M5 gate even after the synthetic workflow passes.


| M4 layer | Implemented acceptance | Limits |
| --- | --- | --- |
| Production API/application | Actual injected UniProt/RCSB routes, authoritative pin/import, strict validation/errors/cursors/Location, typed causes, partial providers, retained offline restart, audit projections, corruption/publication conflicts, exact plain/gzip originals | Authored synthetic providers; no live compatibility/scientific validation |
| Blocking execution | Responsive health, zero-queue admission, timeout/cancellation accounting, eventual recovery/drain, mutation uncertainty and completion logging | Work-count limits; threads/native parsing cannot be preempted; one process |
| Frontend/backend contract | Guarded Python child produces actual route/service/parser/archive responses consumed by TypeScript runtime readers and UI tests | In-process backend; no listening server/proxy in this layer |
| Component/browser | Explicit disambiguation and pagination, inspected hash/revision, model/assembly entry, partial/unavailable/error recovery, retained IDs, stale aborts, ambiguity/missingness, coordinate text and original downloads | Browser HTTP is mocked; no viewer/WebGL rendering or scientific claims |
| Actual local browser/API | Unmocked Chromium -> real Vite proxy -> production routes -> injected synthetic services/parser/archive; original gzip headers/bytes/hash and retained reopening | Passed on macOS and Linux ARM64; no live providers or scientific claim |
| Containers/proxy | Non-root Linux ARM64 service builds, health/page/proxy, biological/original-byte smoke and named-volume reads after forced backend recreation | Passed on isolated development stack; no production or other-architecture claim |
| Explicit live probe | Public P69905 / 1A3N entity 1, chain A, model 1, asymmetric unit; lookup/pin/discovery/import/audits/original and provider-forbidden retained reopening | Opt-in separate command; one source pair and page, not biological accuracy or general compatibility |

The earlier rows describe historical foundation ownership. M4 supersedes the
health-only/operational-route/UI gaps in those rows; NF-05/NF-06, real inference,
broader live compatibility, complete scientific manifests/exports and independent scientific
release gates remain open. Frontend performs no scientific canonical hashing.
See [operational commands](operational-checks.md) and
[executed evidence](nf02-operational-evidence.md) for versions, artifacts and limits.
