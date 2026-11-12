# Test foundation — NF-09 M1

Implemented scope: NF-01 health/status behavior and NF-08 M1 shared contracts,
plus offline guards, fixture integrity and frontend test infrastructure. NF-02
M1 adds [biological contracts](../biological-contracts.md), synthetic provider
examples and a separate ASGI HTTP-contract harness; no operational lookup/import
or live provider compatibility is claimed by that harness.
[NF-02 M2](../uniprot-lookup.md) separately adds offline UniProt transport, lookup,
cache/cursor, pinning and filesystem behavior tests. [M3](../structure-import.md)
adds experimental discovery/import, CIF/alignment and immutable map tests. A
passing foundation is neither an integrated synthetic preview nor a real scientific MVP. [The matrix](test-matrix.md) separates implemented
coverage from planned work; [scientific review](scientific-review.md) and the
[evidence template](evidence-template.md) define later acceptance.
The [M1 acceptance record](nf09-m1-evidence.md) records local results and gaps.

[NF-03 M1](../variants.md) adds pure substitution/difference behavior under the
same offline guards. [Its evidence](nf03-m1-evidence.md) covers strict notation,
constructor/codec types, all twenty residues, generated exact one-change cases,
whole-reference alphabet/error precedence, immutable reference/hash consistency,
and a separately authored 142-residue numbering example with shorter hypothetical
structural coverage. No live artifacts, structure/map, provider or model runtime
is required. [M2 evidence](nf03-m2-evidence.md) adds independently specified
identity bytes/ID, expected-hash/reference resolution precedence, offline archive
round trips, synchronized thread/process duplicates, failed/abrupt publication,
strict codecs, dependency damage and self-consistent checksum tampering with
independent M1 derivation checks. Child processes deny sockets/DNS and run without
site-packages. [M3 evidence](nf03-m3-evidence.md) adds production POST/GET
acceptance with real temporary archives, exact strict DTOs/OpenAPI, stable errors,
offline reopening, deterministic overlapping duplicate publications, damaged
dependencies, publication I/O phases and timeout/cancellation recovery. Worker
admission, late outcomes, safe logging, serialization and shutdown draining are
exercised under unchanged socket/DNS guards.

## Commands and compatibility

From `backend/`, using Python 3.12 (CI also uses 3.13):

```sh
uv sync --locked
uv run --locked ruff check . ../infra/testing
uv run --locked ruff format --check . ../infra/testing
uv run --locked mypy src tests scripts ../infra/testing
uv run --locked pytest
```

From `frontend/`, using Node 24:

```sh
npm ci
npm run lint
npm run typecheck
npm run build
npm run test
npm run test:browser:install
npm run test:browser
npm run test:integration
```

Installation downloads dependencies/browser binaries and needs network access.
After installation, required behavior tests use no external services. On Linux,
install browser OS dependencies with
`npm run test:browser:install -- --with-deps` as CI does. Browser installation is
explicit; `test:browser` never downloads browsers. It builds current sources and
launches its own static Vite preview on `127.0.0.1:4173`, failing if occupied.
It does not launch or require a listening API or worker. M4 frontend tests now
invoke `uv run --locked python tests/contract_exchange.py` in `backend/` to
produce real offline application/service/parser/archive responses. Run the
backend locked sync first. The Python child explicitly enables socket/DNS
guards; browser HTTP remains mocked and unmatched traffic still fails. CI's
frontend job installs that same locked Python environment. Reports/traces stay ignored in
`frontend/test-results/` and `frontend/playwright-report/`; review for sensitive
content before sharing future feature traces.

Exact direct test versions are recorded in `package.json` and the npm lock:
Vitest 5.1.0, React Testing Library 16.3.3, DOM Testing Library 10.4.2,
jest-dom 7.0.1, jsdom 27.4.0 and Playwright 1.65.0. npm metadata was reviewed
2026-11-10: Vitest accepts Vite 8 and Node 24, RTL accepts React 19, and jsdom
27.4 accepts Node 24.0+. jsdom 31 requires Node 24.15+, so it is not selected for
the existing Node 24.5 development runtime. Test-only Node types are isolated in
`tsconfig.test.json`; application code retains browser types.
[Vitest setup files](https://vitest.dev/config/setupfiles),
[RTL installation](https://testing-library.com/docs/react-testing-library/intro/)
and [Playwright web servers](https://playwright.dev/docs/test-webserver) describe
the integration points. Recheck engines/peers and run every layer on upgrades.

## Offline transport policy

Backend `pytest-socket` is development-only and enabled by default through
`--disable-socket --allow-unix-socket`. IPv4/IPv6 TCP/UDP creation is blocked,
including loopback. Unix sockets support asyncio's local wakeup mechanism;
FastAPI TestClient uses in-process ASGI, not a listening server. Autouse DNS
guards also block the four standard host/address resolver entry points. Tests
prove socket, DNS, synchronous HTTP and async connection attempts fail.
See [pytest-socket](https://github.com/miketheman/pytest-socket).

Component tests start with failing `fetch`, XHR, WebSocket, EventSource, beacon,
Node TCP/UDP and common DNS entry points. jsdom's default resource loading is
disabled; do not enable external resources. Explicit per-test `mockHealth`
matches only `/api/health` with an abort signal and rejects other requests.
Each test restores mocks and globals, cleans React mounts and restores timers.
Future adapters should inject transports/controllers instead of expanding a
global URL allowlist. Timeouts are advanced deterministically in component
tests; the real browser tests exercise native fetch and abort-signal support.

Playwright uses a fresh context per test, blocks service workers and routes
every HTTP request. Only GETs for the exact local preview origin's `/`,
`/assets/*` and favicon reach a server; each health call must be explicitly
fulfilled by the test. Every unmatched request is aborted **and fails the test
at teardown**, even if application code catches the error. All WebSockets are
intercepted without connecting to a server. A guard regression test deliberately
consumes its expected external HTTP/WebSocket violations. These policies follow
[Playwright routing](https://playwright.dev/docs/network) and
[service-worker guidance](https://playwright.dev/docs/service-workers).

These are test transport guards, not an OS security sandbox. They do not cover
native libraries, child processes, all alternate resolver APIs or Playwright's
Node-side APIRequestContext. Do not use those as network escapes. Required tests
must use explicit fakes; future child workers need their own guard or isolated
network environment. The existing core-import subprocess runs only standard
library imports with `-I -S`. Container smoke tests intentionally use local
service networking and remain a separate layer. No live/GPU opt-out marker,
provider probe or scientific runtime is added at M1.

## Fixture policy and inventory

[`fixtures.json`](fixtures.json) inventories the two existing frozen NF-08 JSON
files, NF-02 synthetic provider/biological files and source files containing
inline synthetic inputs/responses. Each record
includes ID, location, generation method, invariants, purpose, author/license,
evidence, raw byte size/SHA-256, units and coordinate convention. Source-backed
records hash the whole source file; update the inventory after editing a source
fixture. The inventory does not hash itself. These raw hashes are distinct from
the canonical JSON and sequence hashes embedded in NF-08 golden vectors.

`test_fixture_inventory.py` verifies bytes, bounded size, coverage of all files in
`backend/tests/fixtures/`, and NF-08 `ContentHash`/`Metadata` semantics. An embedded
descriptor in `contracts-v1.json` describes fictional diagnostic bytes; the file
is a compatibility example, not an artifact store or successful prediction.

For a new fixture:

1. Author a tiny deterministic synthetic example; record its construction and
   independent expected result before testing the implementation. No real
   sequences, downloaded structures, weights, model outputs or research data.
2. Keep standalone fixtures at most 64 KiB each. Larger needs require a documented
   policy change/review; the size test is a guardrail, not a scientific review.
3. Inventory the bytes and expected invariants with independent attribution and
   license review. Use `evidence: synthetic`; represent absent units/coordinates
   using NF-08 `not_applicable` and a reason, never an invented value.
4. Preserve broad scientific-data ignore rules. Future synthetic molecular files
   use only the existing `backend/tests/fixtures/` allowlist. Frontend fixtures
   currently use inline source responses. Future shared molecular fixtures must
   be explicitly read from that backend directory by a test and served through
   `route.fulfill`; do not expose arbitrary filesystem roots or add broad ignores.
5. Recompute raw file bytes/hash, inspect the diff, and run backend inventory and
   relevant behavior tests. Frozen versioned contract fixtures need deliberate
   compatibility review; do not rewrite expected outputs to conceal a failure.

All present fixtures are authored for NeuroFold under Apache-2.0. This does not
relicense future external source data. NF-02 provider-shaped examples are
authored synthetic records, not captured
responses. M3 adds an authored coordinate fixture and RCSB adapter behavior with
injected transports; comparison numerics and biological validation remain future
work. See [NF-02 M1 evidence](nf02-m1-evidence.md).

NF-02 M2 local results and remaining environment/integration gates are recorded
in [its acceptance evidence](nf02-m2-evidence.md).

M3 results are recorded in [its evidence](nf02-m3-evidence.md). The authored
`structure-synthetic-v1.cif` uses angstroms in original deposited Cartesian
coordinates; unlike prior metadata fixtures its inventory marks those values
present. `test_structures.py` mutates those tiny bytes and independently specifies
maps for tags, substitutions, fragments, internal gaps and repeated domains.
Gzip bombs, over-limit content and malformed events are generated in memory.
All tests remain under the existing socket/DNS guards; no live structures or
research data are fetched. Full Python 3.13 verification uses a separate
`UV_PROJECT_ENVIRONMENT` and `--python`, preserving the default 3.12 environment.


## NF-02 M4 integration coverage

[M4 evidence](nf02-m4-evidence.md) separates actual production ASGI integration,
cross-language response validation, mocked component/browser HTTP, and container
acceptance. `test_integration.py` exercises eight operational routes plus versioned
audit projections with injected providers, real Gemmi/Biopython adapters and
private temporary archives. It covers offline restart, partial providers,
conflicts, source revalidation, original plain/gzip bytes, typed errors,
corruption/publication failures and bounded worker/cancellation accounting.
`test_container_profile.py` tests the explicit offline smoke composition in
process; this is not evidence of Linux/container execution.

Vitest validates actual backend responses before exercising accessible
selection, pagination, pin/import, stale/aborted requests, recovery, ambiguity,
missing coordinates, retained IDs and download links. Playwright tests the built
workflow and exact original download in native Chromium and no-WebGL Chromium.
No molecular rendering or scientific accuracy is inferred. The explicit
`compose.offline.yaml` profile and `infra/testing/smoke.py` add biological/proxy
and persistent-volume recreation checks to container CI; run them locally only
when a daemon is available. Frozen molecular/provider/schema examples remain
unchanged. Inventory updates distinguish source-fixture edits from frozen bytes.


`npm run test:integration` is the separate **unmocked local HTTP** browser layer.
It launches an explicitly synthetic Uvicorn composition and the actual Vite
proxy, with a private temporary archive. Its browser guard permits only that
local app/HMR origin; the injected backend transport cannot access providers.
The test covers pin/import, retained reopening and exact original gzip delivery
through the proxy, including independent decoding/checksum checks. Required
ordinary ASGI/unit tests retain their unchanged socket/DNS guards. This narrow
local-server layer does not permit live-provider or external traffic and does
not itself establish Linux/container or scientific acceptance. The later
[operational evidence](nf02-operational-evidence.md) records its Linux ARM64 run
and separate container retention checks. [Operational commands](operational-checks.md)
also document the explicitly enabled public probe; ordinary tests stay offline.

The explicit local/container synthetic server also installs outbound-connection
and DNS guards (`infra/testing/offline_server.py`), while allowing its incoming
HTTP listener. A subprocess regression verifies TCP/UDP/DNS rejection. This does
not add a production test switch or relax ordinary pytest socket policy.


## NF-04 M1 contracts

[Executed evidence](nf04-m1-evidence.md) covers strict construction/codecs and
four additive exchange schemas, independently spelled spec identity/hash goldens,
NF-02/NF-03 linkage, defaults/parameters/limits, all lifecycle edges, leases/fences,
cancellation/terminal history, samples/ranks/maps/confidence, synthetic/real
conditional provenance, captured remote-policy input identities and corrupt/missing
artifact bytes. Helpers provide authored in-memory records, not fake execution.
All socket/DNS guards remain intact. Existing startup/health, skeleton rejection
and all-core `-I -S` isolation tests remain required. Source-backed fixture bytes
and the standalone compatibility example are inventoried in fixtures.json.

Schemas can be regenerated from backend with
`uv run --locked python scripts/prediction_schema.py`; a reproducibility test
checks their checked-in bytes. The generator defines exchange shapes; core owns
cross-record/conditional invariants documented in the prediction guide. Every new
module/test/script participates in the existing strict CI checks. Run the full
checkpoint under both Python 3.12 and a separate 3.13 environment, setting
`UV_PROJECT_ENVIRONMENT=/tmp/neurofold-nf04-py313` and `--python 3.13` for every
alternate sync/run. Scientific review and the historical stopped-daemon
container-execution gap remain separate open gates.

## NF-04 M2 local orchestration

[Executed M2 evidence](nf04-m2-evidence.md) records locked Python 3.12/3.13,
Node 24 and actual Linux/container checkpoints. Tests use real temporary SQLite
connections, barrier-synchronized submissions/claims/cancellation/success, fsynced
archives, abrupt process exits and harmless FIFO-controlled children. Children
copy authored M1 output bundles, deny sockets/DNS and are never production
adapters. Existing M1 validators cover scientific/provenance/byte negative paths;
M2 tests exercise their storage and process integration. Every source-backed
fixture is inventoried. Software tests do not satisfy scientific review gates.

Use an isolated Compose project for controlled-child acceptance:

```sh
docker compose -p neurofold-nf04-m2 -f compose.yaml -f compose.prediction-test.yaml up --build --detach --wait backend frontend controlled-worker
python3 infra/testing/prediction_smoke.py
docker compose -p neurofold-nf04-m2 -f compose.yaml -f compose.prediction-test.yaml down --remove-orphans
```

The smoke driver uses loopback ports 8000/5173, recreates only its own services,
and retains its named volume. Set NF04_COMPOSE_PROJECT/NF04_API_URL/
NF04_FRONTEND_URL plus Compose port variables when using other ports. Do not run
this composition against a production archive. It checks non-root writes,
retained jobs/idempotency, separate workers, cancellation/timeout/shutdown/loss,
and Linux race/crash tests. M3 fake execution/UI and real runtime gates stay open.

The current authoritative check list is [AGENTS.md](../../AGENTS.md#required-checks).
NF-04 M2 review hardening is recorded separately in
[the checkpoint](nf04-m2-hardening-evidence.md), including guard sensitivity and
newly executed platform checks. Historical milestone evidence is not current approval.

NF-04 M2 [second-review hardening evidence](nf04-m2-hardening-pass2-evidence.md)
supersedes first-pass completeness claims; independent acceptance and remote CI
remain separate gates.

The current NF-04 M2 [focused cleanup closure](nf04-m2-cleanup-closure-evidence.md)
implements the five conditions for the authorized hardening commit. Verification
is targeted by user instruction. The first recorded hosted CI checkpoint for
fd2c8d5 is green (below); it does not cover this uncommitted follow-up. H1 and
scientific acceptance remain separate.


Dated state note (2026-11-12): local main and origin/main are fd2c8d5, and the
origin reflog records the 07:40:56 +0100 push. Earlier no-push statements are
historical. The **first recorded hosted CI checkpoint** is
[CI 43169838959](https://github.com/grusic91/neurofold/actions/runs/43169838959),
**success** for fd2c8d5 (2026-11-12). The user attributes the push to “Me”.
This uncommitted follow-up is not covered by that hosted result.
Current follow-up: [post-closure evidence](nf04-m2-post-closure-evidence.md). H1 is unresolved; M3 has not started.
