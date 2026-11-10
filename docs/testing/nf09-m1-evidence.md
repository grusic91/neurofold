# NF-09 M1 acceptance evidence

Date: 2026-11-10. Scope: test foundation only. Prepared from local command
results and code/document review; no domain scientific approval is claimed.

## Baseline and identity

The initial working tree was clean at
`2b261f289925dfbbd9d748e3084dbdebcf403a50` (NF-08 M1). Inspection confirmed
NF-01 and NF-08 M1: health-only API, service-status UI, frozen standard-library
provenance contracts, schema and synthetic golden fixtures. No NF-02 client,
scientific runtime, storage, jobs or viewer was present.

This implementation is uncommitted. Package versions remain backend/frontend
0.1.0; the health API and `neurofold-research/1`, `neurofold-json/1`,
`raw-bytes/1` and `sequence-ascii/1` contracts are unchanged.

| Exact file identity | Raw SHA-256 |
| --- | --- |
| `backend/uv.lock` | `f873e9dc63115642982bb18397444b1a60d75b41c556161acf71cb428251d9fd` |
| `frontend/package-lock.json` | `895d5c748dd378082bbf7860dc545fe14b734cf7d248e17081315b07cfc585de` |
| `docs/testing/fixtures.json` | `09ab9b99fb96b92fe7e56934723502b0555515dd622498defc96f5d4c0e2e5f2` |

Working-tree change identity (excluding this record): `8d8df731ba052bbee87a75cd96ef577bedbef055892b806ff73cfc714050a186`.
This is SHA-256 of UTF-8 compact JSON with sorted keys, containing the sorted
array of `{"path": relative_path, "sha256": raw_file_sha256}` for all modified
and untracked, nonignored files relative to the baseline. This record is excluded
to avoid a circular identity. Recompute after subsequent edits; this is local
acceptance evidence, not a published release revision or CI attestation.

Environment: macOS 27.0.1 (26A434), arm64, CPU-only; Python 3.12.16,
uv 0.13.7, Node 24.5.0, npm 11.5.1. Playwright 1.65.0 installed Chromium
158.0.8127.18 (build 1254). No GPUs, weights, research data or live providers
were used in behavior tests. Dependency and browser installation needed network
access; test execution used the documented transport guards.

## Acceptance results

| M1 deliverable | Evidence | Outcome |
| --- | --- | --- |
| Choose/lock frontend tools | Exact direct npm test versions and compatibility rationale in the [guide](README.md); npm peer tree valid; existing package versions unchanged | pass |
| Component behavior tests | Checking/success, HTTP/network/JSON/schema errors, timeout, unmount abort; transport guards; 12 tests across 2 files | pass |
| Browser tooling/tests | Built status page with explicit health fakes; 8 tests across Chromium and WebGL-disabled Chromium; external HTTP/WebSocket probes blocked | pass |
| Fixture inventory | Six versioned raw-file records with author/license, generation, invariants, size/hash, evidence and explicit absence; byte/hash/size/coverage check in pytest | pass |
| Offline guards | Default backend INET socket/DNS denial, in-process health tests; frontend browser/Node transports denied; browser unmatched requests abort and fail teardown | pass within documented guard boundaries |
| Test matrix | [Implemented and planned coverage](test-matrix.md), owners, commands/environments, CPU/live/GPU separation | pass |
| Scientific review protocol | [Predeclared panel/method/tolerances, provenance, licensing, failures and domain review](scientific-review.md) | procedure defined; scientific execution/review incomplete |
| Evidence template | [Identity, environment, checks, artifact references, gate outcomes and reviewers](evidence-template.md) with NF-08 semantics | pass |
| Current documentation | Root/frontend README, architecture, epic and task status updated; local links checked | pass |
| Architectural/scope preservation | No changes in backend or frontend application source, core schemas, model packages or LICENSE; only test tooling/development dependencies and documentation | pass |

| Command | Local result |
| --- | --- |
| `uv sync --locked` | pass |
| `uv run --locked ruff check .` | pass |
| `uv run --locked ruff format --check .` | pass (17 files) |
| `uv run --locked mypy src tests` | pass (17 source files) |
| `uv run --locked pytest` | 149 passed, 100% statement/branch coverage; existing minimum remains 90% |
| `npm ci` | pass |
| `npm run lint` | pass |
| `npm run typecheck` | pass, including test/config sources |
| `npm run build` | pass |
| `npm run test` | 12 passed |
| `npm run test:browser:install` | pass after allowing browser-cache download |
| `npm run test:browser` | 8 passed after allowing local preview binding/browser launch |
| `docker compose config --quiet` | pass |
| `docker info --format '{{.ServerVersion}}'` | unavailable: configured Colima socket does not exist |
| Container builds and service/proxy smoke tests | not run: no available Docker daemon |
| `git diff --check` | pass |

Initial sandbox attempts could not write uv/browser caches or bind the preview
port; these checks were rerun successfully with the required execution
permissions. npm registry metadata needed network access. These restrictions are
distinct from the missing Docker daemon: Docker CLI 29.5.2 is installed, but
`unix:///Users/gasperus/.colima/default/docker.sock` is absent, so no server or
container image execution was verified. No daemon was provisioned or started.

## Review and remaining gaps

Reviewed the dependency/lock diff, default guard configuration and its regression
tests, fixture hashes/provenance, CI commands, document links and scope. Existing
runtime dependency versions and application behavior remain unchanged. The CI
workflow now requires both frontend behavior suites and browser installation,
retaining Python 3.12/3.13, Node 24, backend coverage and the container smoke job.
CI run IDs/results are unavailable because this uncommitted work was not pushed;
Python 3.13 and Linux browser/container execution were not run locally.

Foundation software checks pass locally; container execution remains unverified.
The transport guards are regression barriers, not OS-level isolation; native
libraries/child processes and alternate APIs require explicit isolation when
introduced. Current browser checks cover the status page, including no-WebGL
startup, not actual Mol* rendering or an integrated protein workflow.

NF-09 M2–M5 remain incomplete. Biological data, variants, workers, scientific
numerics, viewer interactions, full synthetic workflow and offline export
verification await NF-02–08 implementation. Real model/weights/licenses/MSA,
public panel, Linux/NVIDIA environment, measured limits, justified tolerances,
nondeterminism studies and named domain review remain incomplete. The M1
provenance skeleton cannot certify successful inference. No real scientific MVP,
prediction accuracy, biological causality or clinical validity is claimed.

No commit, push, publication, deployment or PR was performed.
