# NF-02 M4 acceptance evidence

Date: 2026-11-10. Scope: operational biological HTTP/UI integration, private
retained archive and bounded synchronous work in one API process. Implementing
agent review and local offline synthetic acceptance; no independent scientific
approval, live-provider compatibility, Linux execution or container execution
is claimed. [Integration/configuration decisions](../integration.md) describe the
supported profile and recovery semantics.

## Starting state and compatibility

The tree was clean at `c2a5a4c14c5bffe9e0d5a08d2f8613fd65c35ee9`
(`Complete NF-02 M3 experimental structure imports and residue mapping`). History
also confirms M1/M2. The exact starting revision was extracted to a private
baseline directory and its full suite rechecked with the locked default runtime:
**503 passed, 96.84% combined statement/branch coverage**. This confirms the
historical M3 evidence rather than treating its numbers as fixed targets. There
was no pre-existing uncommitted work to overwrite.

All frozen provider/biological/provenance/canonical fixtures, authored CIF,
biological/research v1 schema bytes and the M1 DTO definitions are unchanged.
The fixed M1 contract harness remains compatibility evidence. Only its historical
production-health-only assertion changes deliberately to assert the eleven
current paths (health, eight biological operations, two audit subresources).
Health body/status/media type, unsupported method and ordinary unknown-route
contracts remain covered. No LICENSE/attribution file was modified.

No dependency was added or version changed. `frontend/package.json` adds only
`test:integration`; both dependency lockfiles retain their M3 bytes. Application
version remains 0.1.0. The new independent HTTP audit projections are
`neurofold-reference-audit-http/1` and `neurofold-structure-audit-http/1`, documented
by `docs/schemas/neurofold-biological-integration-1.schema.json`. Their retained
canonical hash identifies the unchanged original audit; the view deliberately
allowlists headers and omits Set-Cookie/unreviewed headers. It does not pretend
to be the complete original stored record.

## Decisions and implemented behavior

The decision record was created before dependent route/UI work and updated with
the final projections and recovery choices. `api/composition.py` lazily builds
HTTPX, both catalogs, reference/structure services and the same filesystem graph.
The stateless `application/biological.py` service owns lookup, reference-bound
discovery and independently verified registered artifact reads. HTTP handlers
own transport validation, DTO conversion and headers; scientific parsing,
alignment and publication remain delegated. No process-global production test
switch is introduced. Core remains standard-library-only and scientific imports
remain lazy; isolated guarded startup verifies no Gemmi/Bio/NumPy import.

Four workers, zero waiting admissions and a 90-second HTTP await budget are
explicit settings, separate from existing two-slot provider gates and 15-second
network operation deadlines/retries. Request bodies are bounded at 16 KiB;
extra/duplicate/control query parameters and duplicate/excessively nested JSON
fail before composition. Blocking work, integrity checks and response DTO/JSON
serialization execute on admitted workers. Capacity is released only by actual
concurrent-future completion. Cancellation/disconnect/timeout cannot guarantee
thread/native-parser interruption or rollback. Shutdown closes admission and
drains accepted work. Late publication logs request ID and retained Location;
mutation timeout, IO/internal failure and client transport/contract failure
explain an uncertain outcome and never trigger automatic mutation retries.

The v1 request's omitted author chain is resolved from fresh authoritative
metadata in `StructureService.import_request`, then the unchanged complete M3
selection path performs another fresh inspection and validates metadata, CIF,
model/copy and final revision. No author chain, first model or operator is
invented. Unknown revision fails closed; expected sequence/revision changes are
409. Missing organism and incompatible reference/structure metadata have typed
422 causes. Authoritative RCSB 404s are typed separately from missing fields in
malformed 200 content, preserving candidate-specific partial discovery.

Default local archive is private ignored `data/archive` relative to backend
working directory; configured service paths should be absolute and durable.
The container mounts the named `biological-archive` volume at a precreated,
non-root-owned 0700 directory. Cache eviction never removes retained records.
This supports one trusted operator/API process; provider coordination, caches
and cursors remain process-local. Multi-worker coordination is not implemented.

Registered originals verify bounded bytes before success, then deliver exact
raw SHA-256, Content-Length, descriptor media type, ETag, attachment filename,
X-Artifact-Encoding and private/no-transform cache semantics. Gzip is a compressed
registered entity, with **no Content-Encoding**. No decoded HTTP artifact is
substituted. Browser downloads reject redirects, verify headers/size/raw SHA-256,
and save a temporary Blob containing the same bytes; failed downloads leave
retained results visible. Blob URLs/timers and pending requests are cleaned up.

The accessible UI uses HTTP only: canonical lookup, exact gene/taxon search,
explicit paginated candidate inspection, inspected-hash pinning, complete/partial/
unavailable discovery, explicit model/asymmetric-unit or assembly/operator import,
retained-ID reopening, receipts/rights/citations and original downloads. Typed
runtime readers reject incompatible versions, shapes, metadata/absence states,
unsafe links and mapping inconsistencies. Links resolve through configured
browser API base; absolute response URLs are never followed. Failed/stale work
cannot replace newer selections; pages remain bound to their query/reference.

Deposited Cartesian angstrom coordinates remain unchanged. Selecting an assembly
retains unapplied operators/matrices, not generated transformed coordinates.
Reference/polymer/coordinate-author/insertion identifiers are displayed; the audit
also exposes separate scheme-author/PDB and atom-site identifiers, alternate
atoms/occupancies, modifications, models/chains, scoring/ties and all coverage
numerators/denominators. All five map states remain textual, including ambiguous
candidate positions and reasons. Missing coordinates do not delete polymer
residues or imply zero coverage. No viewer, numerical fitting/comparison, variant,
inference, database, authentication, job system or export was added.

## Acceptance layers and checks

Required backend tests retain the ordinary socket/DNS guards, injected clocks/
transports and tiny synthetic fixtures/private temporary archives. The Python
response-exchange child has its own socket/DNS guards. The separate local HTTP
synthetic server permits incoming HTTP but denies outbound connect/connect_ex/
sendto and DNS; a subprocess regression proves rejection. Browser tests reject
unmatched external HTTP/WebSocket traffic.

| Layer | Observed acceptance |
| --- | --- |
| Actual production ASGI/application | Real routes/OpenAPI, injected services, strict requests, typed status/code/retryability/details/request IDs, usable 201 Location, opaque cursor binding/restart, sequence/revision/selection conflicts, unavailable revisions and provider 404s |
| Cross-provider/offline retained graph | Pin/import then fresh application/store/cache loss with provider access forbidden; reference/structure/map/audit/original reads; UniProt outage does not prevent retained-reference discovery; RCSB outage does not invalidate references; usable partial candidates survive |
| Integrity/publication | Missing dependencies become archive integrity failures, not ordinary 404; corrupt original bytes cannot commit success; independently bad injected streams fail; publication IO/conflicting immutable IDs never overwrite retained records |
| Blocking/admission | Controlled blocking fakes prove responsive event loop/health, immediate 429/Retry-After, capacity held after await timeout/cancellation, eventual recovery/drain and uncertain mutation outcome |
| Original representations | Exact plain/gzip bytes, media types, raw hashes, lengths, ETags, no Content-Encoding, explicit local decoding semantics; original 200 receipts remain distinct from later authoritative 304 checks |
| TypeScript/backend exchange | Actual route -> application -> Gemmi/Biopython -> archive responses are produced in a guarded Python child and consumed by strict TypeScript readers and UI tests; no frozen response snapshot is substituted |
| Mocked component/static-browser HTTP | Disambiguation, pagination/restart/empty, inspected hash/revision, explicit copy choice, loading/validation/conflict/admission/provider recovery, stale abort/unmount, retained IDs, all five states, coordinate/numbering text and download success/failure |
| Unmocked local browser/API/proxy | Native Chromium -> real Vite proxy -> production routes -> explicit synthetic providers/parser/archive; pin/import/audit/reopening, exact original gzip download with independent checksum and decoded-CIF comparison; no route.fulfill API mocks in this layer |
| Container profile in process | The explicit synthetic container composition is exercised locally with real routes/parser/store, independently of a Docker daemon |
| Linux/container services/volume | Compose and test override validate; CI now builds both services, probes normal health/proxy, then performs synthetic biological/original-byte checks and force-recreates the backend before verifying retained IDs/bytes. Not executed locally: no daemon available |

Environment: macOS 27.0.1 (26A434), Darwin arm64 CPU-only; default Python
3.12.16 and separate Python 3.13.2 environment `/private/tmp/neurofold-m4-py313`;
uv 0.13.7, Node 24.5.0, npm 11.5.1, pinned Playwright 1.65.0/Chromium.
Commands used `UV_CACHE_DIR=/private/tmp/neurofold-uv-cache` for sandbox-compatible
cache access. The separate 3.13 run used `UV_PROJECT_ENVIRONMENT` and `--python`;
`.python-version` and the default 3.12 environment remain unchanged. Coverage
files for concurrent version checks were separated.

| Command / environment | Result |
| --- | --- |
| `uv sync --locked` (3.12 and separate 3.13) | pass; 45 locked packages resolved, 43 installed checked |
| `uv run --locked ruff check .` | pass |
| `uv run --locked ruff format --check .` | pass; 47 backend files |
| `uv run --locked mypy src tests` | pass; 47 backend source/test files |
| Extra Ruff/format/mypy including `../infra/testing` (3.12/3.13) | pass; 50 files; CI enforces these extra checks too |
| `uv run --locked pytest` (Python 3.12.16) | **552 passed; 96.75%** combined coverage; unchanged ≥90% gate |
| Separate locked Python 3.13.2 full pytest | **552 passed; 96.75%** combined coverage |
| `npm ci` | pass; dependency lock unchanged |
| `npm run lint` / `npm run typecheck` / `npm run build` | pass |
| `npm run test` | **36 passed** |
| `npm run test:browser` | **12 passed**, built app in Chromium and no-WebGL Chromium; mocked API HTTP |
| `npm run test:integration` | **1 passed**, unmocked local app/proxy/API with guarded synthetic providers and original gzip |
| Normal and offline-override `docker compose config --quiet` | pass |
| Docker context `colima` | unavailable; default Colima daemon socket missing |
| Docker context `colima-arm64` | unavailable; arm64 Colima daemon socket missing |
| Docker context `default` | unavailable; `/var/run/docker.sock` missing |
| Container builds/service/proxy/volume-recreation smoke | not run locally; all configured daemons unavailable |
| Full tracked/new-file review, fixture/frozen identities, local Markdown links and `git diff --check` | pass |

Browser preview initially could not bind loopback (EPERM) under the filesystem/
network sandbox; the same offline commands passed with local-listener permission.
An initial native download mock was canceled when Chromium bypassed interception
for a download-attribute navigation; the final managed fetch/verified Blob flow
passes both mocked and actual proxy downloads and preserves error recovery.
Full verification caught a synthetic-attribution change dropping a supplied
notice; it was fixed without weakening the existing notice test. Early path/
format/type/inventory and fixture-ETag issues were corrected; the final results
above include the corrections. No frozen fixture/schema expectation was rewritten.

Fixture inventory now has **23 entries**. Existing authored CIF bytes remain
2,913 bytes. New source-backed fixtures use existing tiny authored inputs and
inline failure/selection mutations, all under 64 KiB, with NeuroFold contributor/
Apache-2.0/synthetic labels. Gzip/adversarial bytes are generated in memory.
No real protein record/sequence/structure, dataset, patient/private data, weight
or model output was fetched or committed. Checksums and synthetic software tests
establish byte/software semantics, not biological accuracy or clinical meaning.

## Exact identities and review

Both dependency locks, both frozen schemas and all standalone frozen fixtures
were compared against the starting commit. Their identities include:

| Preserved file | Raw SHA-256 |
| --- | --- |
| `backend/uv.lock` | `50a0889ee54acca7108e15eba7772b9402ed17a634872a8c132a8504abf5bdad` |
| `frontend/package-lock.json` | `895d5c748dd378082bbf7860dc545fe14b734cf7d248e17081315b07cfc585de` |
| `docs/schemas/neurofold-biological-http-1.schema.json` | `acde8893ea3997650d7dffeb198596b177442f81db53b29ac94677ba0f9bd71c` |
| `docs/schemas/neurofold-research-1.schema.json` | `1046eb7bd6cf809f078138e189ebfeeb55e95e8085f466e288aadb692f30fcba` |
| `backend/tests/fixtures/structure-synthetic-v1.cif` | `5cab5e1e7834c06363f4d4d259ad71acaeabeecc32d1cd1054fd64e13ef07282` |

Working-tree change identity: **60 changed/new files excluding this evidence**,
SHA-256 **`76f71db2a42a0f5e0e0c61fd1b1283ec1de586208e2ff5f01e3ba2aa4c02271b`**. This hashes compact sorted-key UTF-8 JSON of the
path-sorted array `{"path": relative_path, "sha256": raw_file_sha256}` for
modified/untracked nonignored files relative to the starting revision. Excluding
this evidence avoids circularity. It identifies local bytes, not a commit,
release, remote CI run or independent attestation. Exact constituent identities:

| Changed/new path | Raw SHA-256 |
| --- | --- |
| `.env.example` | `21bcecefd1a97e8eaeff34866554fce7ce9488e77594bd2577493dda4510444a` |
| `.github/workflows/ci.yml` | `3ac5534ea2c8f19023891e50c0bed75f6cf16362914e9cc5f2129af0f6e7b990` |
| `README.md` | `44965278aba15e45fa09804fb4a6c9cf5a04d6a59369e4bdcf0fb3839690f4f6` |
| `backend/.env.example` | `d895a3de72b0667e616217ea70b0a861d5c16c12ddb48ae8c59706ec918ef269` |
| `backend/src/neurofold/adapters/biological/alignment.py` | `1e1f9b6ce941038dd8d871528f2c37f65c2be3a117d5f77e243e9c2ec4fcb510` |
| `backend/src/neurofold/adapters/biological/mmcif.py` | `26244824381026ba1a4672319378441ae7fce1cb8eb7d01ae0ae9aefd301ffa9` |
| `backend/src/neurofold/adapters/biological/rcsb.py` | `d32f1ec707cdcdd5e7f62d6253f1d7e303b73ac754caaf96d7cdf3de75bff983` |
| `backend/src/neurofold/adapters/biological/storage.py` | `9a80d744d2ab7fd6396b297c04938790a186f768a9edd83de60fba5cb3ae55b8` |
| `backend/src/neurofold/adapters/biological/structure_storage.py` | `2b42755d0ba32162a79609b61a1d8232dee908c294b67b20ed5c0c6281d6b5c7` |
| `backend/src/neurofold/adapters/biological/transport.py` | `793c223eac2c1042edc1948de602cc62395ebbd5ebf217cf60b74751da985a72` |
| `backend/src/neurofold/adapters/biological/uniprot.py` | `a830954d009630df744b86ed0584d799eeda535cb1008b48813339679e7b795b` |
| `backend/src/neurofold/api/composition.py` | `39b22545df424b33e12b0dd6b7b3306ffa8a8aec8498cbf1f8dee5f2e90d928b` |
| `backend/src/neurofold/api/configuration.py` | `2e45d4d3044ce1e4061ac1cff17f20cd94f3fc017cd2766d53dcb47474eca89f` |
| `backend/src/neurofold/api/errors.py` | `445c2edb06d2c3510905b1620f5046b2388f8d8d730280e64ecbb8f9770a0cbe` |
| `backend/src/neurofold/api/execution.py` | `cbe9e33c8b3057fc7dcfb48925c11c85faa59c2be03e1eb511abe393a250f780` |
| `backend/src/neurofold/api/main.py` | `2b355ed4bdd3fab4aec0d577f13ba4c0f50318fbe8f636945623ceb2baa18d6b` |
| `backend/src/neurofold/api/routes.py` | `e78b34dcbb0c2969fcc43d910e0666cf7a2ac30b423e29d9dabf10e80ff99adc` |
| `backend/src/neurofold/application/biological.py` | `05409132fc20e928cc8ab61cbb053899ab761e92c2a0fbfea05c594151cace47` |
| `backend/src/neurofold/application/references.py` | `5a775c25b8f79fcf7aeebbce790767b336fda26feac5399dfc739cc038105837` |
| `backend/src/neurofold/application/structures.py` | `f383cc8b7acc040cfac4429317d8899a9fd700d94ff4339b43e69f0e368ce0e0` |
| `backend/src/neurofold/core/errors.py` | `149ba3002f6d0f8ca2999c0a1fb3b06c5eaf7890f259e0d5c899713f070d6ac8` |
| `backend/src/neurofold/core/lookup.py` | `6cbd42749eac1e3c9eff7e701c15e9896dba40c7cec72cc5e78fdde1da2084cc` |
| `backend/tests/contract_exchange.py` | `4a089b2031606225d8fd65d3f7b3df4c36848e9ca839e2f2211a141ea67b5cfd` |
| `backend/tests/test_biological_api.py` | `0051b9459bd6f8ab106b06443be8f30953df7db3fef1dcad8df8ed62e543a688` |
| `backend/tests/test_container_profile.py` | `c3fa5f56fa72bc002b8fba79bf559971341db00efbcbb1da2100e7588ee526be` |
| `backend/tests/test_integration.py` | `b4ffd07bcc470d0e76a32c26f7bf537fc3793f2a6f258d1ea8015d204cf1b04b` |
| `compose.offline.yaml` | `cfc6f104a0f49fd7a2ad31c38e5032a391ce3d0327124038d3d9eb78e69888eb` |
| `compose.yaml` | `cee00f62b0bb7a43355c14b69b78eb6dba1c8e03ec53fd183b1f64114329c808` |
| `docs/EPIC.md` | `6788da80e191992885eabd16e46c0e92907b9cdf275241a9b224b69d75c74fe3` |
| `docs/architecture.md` | `5845b3ed0a3e1887d673b23fa2a1b3b0c58f08368510e23f2a037114d3204d3b` |
| `docs/biological-contracts.md` | `e7d98593bc4a09a8e3060cfb04eb936a2e52b3c98ee5761fb9a18b0fbcb7fbfe` |
| `docs/integration.md` | `b6f9cb328c4a9b42da2db38c2e66b2b068f1bb43c5c124b6b6aa0d63a244022a` |
| `docs/provenance-contracts.md` | `11126ec8a110007ec9bab2344aea885cabb06bc44ab1452e2735cc1106d11b0b` |
| `docs/schemas/neurofold-biological-integration-1.schema.json` | `a869d6c2983a2b6c78a183f858148773a900ee845d1807b3f8d9e006b5c2308c` |
| `docs/source-licensing.md` | `d54163e7e9e6d02e12bc5ea572902aaca6a0db8330cb2b94dd4c08165cce4031` |
| `docs/structure-import.md` | `2027a512c146ac982f847310b47cf0b6c41aa53d702edfbfab20ddafd936d095` |
| `docs/tasks/NF-02-biological-data.md` | `de7e114d47007c5c7039dce7cbd78429c98156cb99c341da736cf71f445bf2dd` |
| `docs/testing/README.md` | `98ac8580cdfa91edf42f44cf0df2eafaa26b2123d4976395b91220b9eb6bc2aa` |
| `docs/testing/fixtures.json` | `913b8a2fd553f8cb0196e729e8929be189e5f91afcbc162a90b9ed43830d2052` |
| `docs/testing/test-matrix.md` | `7ee66414e627a8be1e7fc7f5f08c7264898936992b0e0a8554c2f25ed2bc7e28` |
| `docs/uniprot-lookup.md` | `73c942aa540bc7c367ed199ad4fd9608c5e7f48af2340b3a5ac3ed9299fab600` |
| `frontend/.env.example` | `814b0b9f1e865c55c36a669c0f8cce8e793f8934513853d9ecda3fb586de2379` |
| `frontend/README.md` | `3082710fbb6285984837aca30921a1847fbd296e8f1853499a5cf949496b63f6` |
| `frontend/package.json` | `67effb3d53c95eabead7abf6f97462d7d8f16b395cea4570e806052623ade3a3` |
| `frontend/playwright.integration.config.ts` | `057e2b5399443e40e19c7ee56a513efe1c96f1b1250233595ebe2fa1949bae7f` |
| `frontend/src/App.tsx` | `16f6b41b76491e50241235e938ec0d07a4864a316fa70e7c0138177e3af7ede9` |
| `frontend/src/Workflow.test.tsx` | `acbc509d4a19fcef80cbcfb8f6ca67ded52eca6e2f3a630076b0501b30bd2623` |
| `frontend/src/Workflow.tsx` | `2e84025251a364671c49a0055e05006a2479d6f37d3655619ff334b7599b96c4` |
| `frontend/src/api.test.ts` | `f88c0d738b8a6e8d5d51693f2fad7509fd1f3e494af029c2b5cafa79f81d19e1` |
| `frontend/src/api.ts` | `7654d7b8aab1518b9396a5301a5518b93f431ac3f6265af63a05c988fdbd249a` |
| `frontend/src/index.css` | `f050a494220df5c11056cc896d3dfa9e622b64e0e4b9e5958d2ec0c69fd992ff` |
| `frontend/src/test/exchange.ts` | `c29d55784616fe99151c192a7c84f87f1e428b121ff5bd42da54df091d320f40` |
| `frontend/tests/browser/workflow.spec.ts` | `67ef557fe7bf1726f47dd08ec7da693310d61ae188ad82e5eadca9762528c52a` |
| `frontend/tests/integration/workflow.spec.ts` | `5c1d4458a3831c495afe038d89d6836d05c46881a364adae784db7fd838e2a74` |
| `frontend/tsconfig.node.json` | `3c6fa5a5714129715ebeb94bc86fbdd9b342d1e4f8160af18e2ec76b7fc4974b` |
| `infra/README.md` | `3a94502044481f8f63a3e82f07ce45905177e3fc9bfcb6b79bb0c510e28a29fa` |
| `infra/docker/backend.Dockerfile` | `abc105ace9f96397435413a1eefee032cd660606c614cb99f4a2d79c0cf59309` |
| `infra/testing/offline_app.py` | `1558e6b61ba08a5b35faaa62b862d7d503cd1560728de161d0bdda68157b8704` |
| `infra/testing/offline_server.py` | `f0327c4ec989be138e0206d872df79c86e1d58f19f647217b997d02378a5c807` |
| `infra/testing/smoke.py` | `c9289c5b6eb65f2f90bf0640890f78fe6f71209b226f57f59ae9383d4414abd9` |


## Remaining independent gates

**M4 acceptance: pass for this local offline synthetic, single-operator/process
profile.** Linux/container execution, live-provider schema/behavior compatibility,
independent domain review and scientific validation remain open. Mac local
HTTP/proxy acceptance does not close Linux/volume acceptance. CI is configured
but has no remote run ID because no push occurred. Conservative limits are not
calibrated against real research workloads. Parsing threads are not preemptible;
provider coordination is not distributed; archive retention/backups/administration
remain operator responsibilities.

NF-05 molecular rendering, NF-06 fitting/comparison, variants, inference/Boltz-2,
complete NF-08 manifests/exports and independent scientific release gates remain
unimplemented/open. No scientific validity, pathogenicity, causality or clinical
claim is made. No commit, push, publication, deployment or PR was performed.
