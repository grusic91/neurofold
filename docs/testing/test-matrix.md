# Test matrix

Status covers NF-09 M1, NF-02 M1–M4 integration and NF-03 M1–M3 domain,
immutable storage and HTTP integration, plus NF-04 M1 contracts and M2 durable orchestration/review hardening.
“Planned” means no implementation or acceptance evidence exists yet.
Mandatory PR CI uses locked installs, Python 3.12/3.13 and
Node 24. Backend coverage remains at least 90%; lint/types/build are additional
checks and never replace behavior tests.

| Layer / owner | Implemented now | Required additions / negative paths | Execution and gate |
| --- | --- | --- | --- |
| Pure core / NF-08 M1, NF-03 M1/M2 | Canonical byte/hash golden vectors, immutability, strict wire/schema versions, explicit absence, evidence/lineage, failed/cancelled skeletons; all core imports without site-packages; strict bounded substitutions, direct/codec invariants, entire reference alphabet/error precedence, exact one-change/hash construction, ordered zero/multiple differences and unequal-length rejection, full pinned numbering independent of structure; M2 four-field identity golden bytes/ID and strict persisted definition codecs | NF-06 selections; Executable synthetic adapter and polling at M3 | `uv run --locked pytest`; offline CPU; mandatory |
| API / NF-01, NF-02 M1 | `/health` body/headers/OpenAPI, 405, unknown-route 404; in-process ASGI under network guard; separate NF-02 harness for eight proposed operations, DTO/frozen schema, envelope/status shapes, 201/Location, placeholder bytes/checksums and response validation | M2 implements Python lookup/source-change/storage behavior; operational biological/variant/prediction routes and typed HTTP translation are implemented; M2 prediction idempotency/cancellation contracts are exercised; later executable-adapter behavior remains M3 | Backend pytest; mandatory as each API lands |
| Adapter contracts / NF-02 onward | Core catalog/repository protocols, authored provider-shaped JSON and NF-08 receipt/hash checks; M2 UniProt/storage implementations with fake transports/clocks and socket/DNS guards | M2 covers pagination, malformed upstream, retry/budget/size/concurrency, cache/304 and immutable offline pinning; M3 covers experimental-only RCSB/partial discovery, revisions/304, bounded CIF and residue mapping | Offline injected transports/temp files; backend pytest mandatory |
| Biological contracts / NF-02 M1 | Frozen reference/structure/map records; canonical/raw/sequence hash separation; strict versions; five mapping states, author/label distinctions, insertion/negative numbering, gaps/tags, alternate selection identity, missing maps/rights/metadata | M2 tests immutable full-reference snapshots; M3 covers actual-reference map consistency, experimental origin/import, author/label/coordinate identities and all five states; no biological inference from fixtures | Backend pytest; offline CPU; mandatory |
| Application/persistence / NF-03/04/08 | M2 reference service and immutable filesystem archive, atomic publication/conflict/interruption/corruption tests; M3 adds checksummed atomic descriptor/map/audit bundles and restart/offline integrity checks; NF-03 M2 adds pinned expected-hash precedence, exact reference-aware identity, complete derivation verification, synchronized thread/process duplicate publication, failed/abrupt writes/restarts, self-consistent tampering and missing/corrupt dependencies; NF-04 M2 SQLite/idempotency, isolated worker, cancellation/timeout/recovery, fenced publication and corruption regressions | Fake catalogs/repositories/clocks/dispatchers; temporary SQLite/filesystem, restart/fencing/races/cancel/timeout, atomic artifacts and corruption; preserve API → core ← adapters | Offline CPU; NF-03 M2 children explicitly deny sockets/DNS and run without site-packages; M3 variant production HTTP, strict DTO/OpenAPI/error contracts, real archive reopening/damage/publication I/O, barrier-synchronized concurrent HTTP duplicates, admitted serialization, timeout/cancellation and late publication/draining verified |
| Scientific numerics / NF-06 | M3 bounded Gemmi CIF parsing, affine Biopython alignment with all bounded optimal ties and an authored Cartesian fixture; no fitting/comparison engine | Known rigid transform, deformation, mirror, ambiguity/gaps; independent RMSD/coverage denominators, units/transforms, missing atoms and justified tolerances | Tiny analytic synthetic fixtures; planned M2; numerical correctness alone is not biology |
| Component / NF-01 | Checking/online/unavailable, HTTP/network/JSON/schema failures, five-second timeout, abort on unmount; transport guard regressions | NF-05/07 accessible forms, disambiguation, races, polling/cancel/resume/retry, synthetic badges, chain/sample/mutation selection, absent confidence; fake viewer controller | `npm run test`; Vitest/RTL/jsdom, no services; mandatory |
| Browser / NF-01 | Built status page and role-based assertions; native Chromium success/error/invalid contract; HTTP/WebSocket guard probes | Full UI/API/separate fake worker slice, export verification, recovery/integrity; planned NF-09 M3 | `npm run test:browser`; mocked HTTP; Chromium and Chromium with WebGL disabled; mandatory |
| Actual viewer / NF-05 | Not implemented: no Mol* dependency or viewer | Small separately scoped actual-Mol* suite with synthetic bytes; mapped selection/overlays, missing confidence, context loss and accessible no-WebGL recovery | Chromium software rendering in Linux CI to be validated with NF-05; current no-WebGL project only checks the scaffold, not viewer fallback |
| Containers / NF-01 | Existing CI builds non-root CPU services, checks both HTTP services and Vite `/api/health` proxy | Record current local availability; perform builds/smokes whenever daemon available | `docker compose config --quiet`, build/start/wait, health + page + proxy, cleanup; Linux CI mandatory |
| Live upstream diagnostics | Historical NF-02 opt-in public pair with retained original bytes | Broader named provider panels and independent mapping review; never ordinary PR fixtures | Historical operational evidence only; no new provider probes in M2 hardening |
| Real model / NF-04, NF-09 M4 | None; no Boltz-2 installation | Reviewed model/weights/licenses/MSA, measured limits, public panel and locked Linux/NVIDIA runtime; failures/absence/nondeterminism retained | Explicit opt-in separate GPU environment; required for real scientific MVP, never base API CI |

Frontend consumes health and biological workflow DTOs; prediction polling remains M3. It does not implement prediction/research manifest types or hashing. Cross-language NF-08 golden-vector and DTO/schema
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


| NF-04 M1 contract layer | Implemented acceptance | Limits / remaining gate |
| --- | --- | --- |
| Capabilities/inputs | Static unresolved Boltz-2 declaration; synthetic contract profile, exact strict parameters/defaults/limits, independently spelled spec/hash golden, full NF-02/03 reference/variant verification | No runtime probes, real capacity claims or network MSA execution |
| Lifecycle | All allowed/forbidden edges, version/attempt/fence, cancellation, terminal history, expiry, lease renewal, linked retries and competing proposals | Pure snapshots only; no transactional winner, database or supervisor |
| Outputs/provenance | All samples/ranks, predicted mapping/units, confidence definitions/absence, full conditional typed provenance, auxiliary capture, complete inventory/byte integrity | Supplied metadata/bytes only; no molecular parsing, fake execution or real runtime truth |
| Compatibility/architecture | Strict construction/codecs, required fields, four additive schemas, authored frozen fixture, safe errors, existing health/startup/core import and NF-08 skeleton rejection | Frozen NF-02/NF-03/NF-08 bytes preserved; scientific review remains required |

| NF-04 M2 layer | Implemented checks | Limits |
| --- | --- | --- |
| Durable SQLite | Separate connections, concurrent key convergence/reopening/conflicts, exactly one claim, version/owner/lease/fence checks, immutable terminal retries, busy/schema/corruption handling | Trusted local filesystem/operator; no distributed scheduling |
| Publication | Exact M1 graph, immutable ready registrations, final cancellation/expiry/version/deadline checks, real cancellation-success race, bad proposals, known retained damage, IO uncertainty and abrupt exits at five publication boundaries | fsync/process behavior does not simulate physical power loss or malicious external deletion |
| Supervisor | Real guarded children, parent-death EOF, graceful/forced termination, timeout, shutdown, heartbeat failure, cancellation and reaping, worker-loss fencing and stale publication rejection | Controlled copied proposals; no fake adapter, molecular parsing or inference |
| HTTP | Strict nulls/types/keys, concurrent submit, retained result/manifest/artifacts, versioned status sidecar, health/capability independence, admission/timeout/drain | No frontend prediction polling; all shipped profiles unavailable/contract-only |
| Linux containers | Non-root shared storage, API recreation/idempotency, independent worker, cancellation/timeout/shutdown/restart and process/storage crash suites | Execution outcomes and exact platform recorded separately in M2 evidence |

The [M2 hardening evidence](nf04-m2-hardening-evidence.md) records fresh execution
and independent-review regressions: retained database validation/concurrent init,
worker contention and corrupt-row parking, special/oversized output rejection,
consistent snapshots, immutable reads during publication contention, cancellation/
capacity recovery, profile evidence, retry-parent conflicts, variant publication,
owned output IDs and truthful operational failure extensions. Schema reproducibility
compares generated documents in memory; tests never rewrite checked-in schemas.
Tagged/truncated mapping correctness (H1) and reference ambiguity handling remain
open before scientific use of mappings; existing synthetic coverage does not resolve them.


The [second-pass checkpoint](nf04-m2-hardening-pass2-evidence.md) adds mapping-parent
lineage remapping, decoded-output contention classification, failure-extension
checksum/binding/missing/immutability guards, all linkage prechecks, observable
prelaunch cancellation, operation retry recovery, attachment/no-store and running
cancel 202 assertions, and bounded interruptible controlled-child startup. Current
platform results are distinct from the historical first pass and pending remote CI.


### Post-closure timing sensitivity (2026-11-12)

| Test | Current treatment | Trigger |
| --- | --- | --- |
| cleanup outcome SQLite contention | Stop assertion and writer release occur inside the first-BUSY hook, before retry resumes; observer timing does not control outcome. | Retain deterministic sequencing when changing retry code. |
| publication reservation early release | Writer release occurs in the renewal/stage BUSY hook, before retry resumes. | Retain sequencing when changing publication ownership. |
| real child copy/succeeded | Retains real profile/handshake wall-clock budgets; does not test a timeout and can still be timing-sensitive on an overloaded host. No timeout was widened to hide it. | Hosted CI flake; revisit supervision-clock injection rather than extending a functional limit. |
| controlled entrypoint startup and recording exhaustion | Only outer hang guards were enlarged, with inline justification; production retry/execution bounds are unchanged. | Re-measure on a new emulator/runtime, independently of behavior budgets. |
| concurrent HTTP submissions | Fixed in round 7: bounded retries only for 503/PREDICTION_BUSY, respecting Retry-After and reusing the identical key/body. Only the initial four calls enter the barrier. Final 202 responses, one job ID and durable reopening remain asserted. | No deferral; retain retry limits and the final uniqueness assertions. |
| concurrent durable submissions | Round 8 restores the submit race: each thread finishes independent repository initialization with bounded PREDICTION_BUSY retries, then all eight rendezvous before submitting with separate bounded retries. Reopening, conflicts and exact specs remain asserted. A submit-only deferred-BEGIN mutant must fail. Raw SQLite exceptions are not retried. | Retain the post-initialization barrier and transaction sensitivity; do not let initialization's flock serialize the submissions. |
| slow-publication lease reservation | Fixed in round 7: an already-finished child isolates the publication/lease invariant from subprocess startup. Clock advancement, recovery rejection and successful publication remain asserted; removing lease reservation still fails the test. | No deferral; real child lifecycle/timeout coverage remains in process/worker tests. |
| Darwin EPERM retry bound | The current 100 ms retry bound is pinned by portable fake-clock boundary cases; Darwin helper probes cover real exit behavior. | M4, before enabling the first macOS runtime child that spawns helpers: re-measure under representative CPU/IO load, update boundary tests if changed, and recompute shutdown margin. |

Only the named test families run during their respective CPU-saturation batches:
five L4 families in round 6, the three repaired cases in round 7, and the restored
durable submit race in round 8. Full suites run separately while the host is
otherwise idle. Round-7 hosted CI
43257968940 passed and is recorded in the checkpoint. Round 8 runs no full
emulated Linux suite; its separately authorized feature-branch push at d7bd884
passed hosted CI 43280081847, including Linux 3.12/3.13 and both container smokes.
Main is not a target.
The [new checkpoint](nf04-m2-post-closure-evidence.md) records repetition counts.
