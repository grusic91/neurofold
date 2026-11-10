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

## Commands and compatibility

From `backend/`, using Python 3.12 (CI also uses 3.13):

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests
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
```

Installation downloads dependencies/browser binaries and needs network access.
After installation, required behavior tests use no external services. On Linux,
install browser OS dependencies with
`npm run test:browser:install -- --with-deps` as CI does. Browser installation is
explicit; `test:browser` never downloads browsers. It builds current sources and
launches its own static Vite preview on `127.0.0.1:4173`, failing if occupied.
It does not launch or require an API or worker. Reports/traces stay ignored in
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
