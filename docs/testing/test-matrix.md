# Test matrix

Status is scoped to NF-09 M1. “Planned” means no implementation or acceptance
evidence exists yet. Mandatory PR CI uses locked installs, Python 3.12/3.13 and
Node 24. Backend coverage remains at least 90%; lint/types/build are additional
checks and never replace behavior tests.

| Layer / owner | Implemented now | Required additions / negative paths | Execution and gate |
| --- | --- | --- | --- |
| Pure core / NF-08 M1 | Canonical byte/hash golden vectors, immutability, strict wire/schema versions, explicit absence, evidence/lineage, failed/cancelled skeletons; all core imports without site-packages | NF-03 substitution syntax, bounds, reference mismatch, exact one-change/hash invariants; NF-04 lifecycle; NF-06 selections | `uv run --locked pytest`; offline CPU; mandatory |
| API / NF-01 | `/health` body/headers/OpenAPI, 405, unknown-route 404; in-process ASGI under network guard | NF-02 onward `/v1` DTO/OpenAPI versions, stable error/status envelope, response validation, artifact bytes/headers, idempotency/cancellation conflicts; retain health behavior | Backend pytest; mandatory as each API lands |
| Adapter contracts / NF-02 onward | No biological/model/storage adapters; socket and DNS guard regression tests only | Transport fakes for pagination, malformed upstream, timeout, rate limit, retry, cache/stale IDs and partial discovery; immutable snapshot bytes | Offline injected transports/temp files; planned NF-09 M2 |
| Application/persistence / NF-03/04/08 | No application service, database, worker or storage | Fake catalogs/repositories/clocks/dispatchers; temporary SQLite/filesystem, restart/fencing/races/cancel/timeout, atomic artifacts and corruption; preserve API → core ← adapters | Offline CPU; future child workers explicitly guarded; planned M2/M3 |
| Scientific numerics / NF-06 | No parser/alignment engine or coordinate fixtures | Known rigid transform, deformation, mirror, ambiguity/gaps; independent RMSD/coverage denominators, units/transforms, missing atoms and justified tolerances | Tiny analytic synthetic fixtures; planned M2; numerical correctness alone is not biology |
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
