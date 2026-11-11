# NF-09 — Testing, Documentation, and Release

Status: M1 test foundation implemented; M2–M5 remain proposed. Testing begins
with each feature, not after integration. See the [test guide](../testing/README.md),
[matrix](../testing/test-matrix.md), [fixture inventory](../testing/fixtures.json),
[review protocol](../testing/scientific-review.md) and
[evidence template](../testing/evidence-template.md).
[M1 acceptance evidence](../testing/nf09-m1-evidence.md) records local checks and
remaining gaps. Parent:
[NF-EPIC-001](../EPIC.md).

## 1. Objective and scientific motivation

Release a maintainable Protein Variant Explorer whose behavior, data contracts
and scientific limits have evidence behind them. Demonstrate that source
integration, variant construction, execution, comparison and export preserve the
same research record. Software correctness and scientific validity are separate
release requirements.

## 2. Scope and non-goals

Include unit/integration/contract tests, fake adapters, tiny synthetic scientific
fixtures, frontend interaction/browser tests, CI, container checks, contributor
and user documentation, optional live/GPU validation and a reviewable release
checklist. Plan release evidence and fixture provenance at M1.

Exclude clinical validation, a claim of general prediction accuracy, mandatory
GPU execution on every PR, real research datasets in Git, publishing/deployment,
automatic package/image release and organoid functionality. Preparing a release
does not authorize pushing, publishing, tagging remotely or opening a PR.

## 3. Dependencies

- M1 relies only on NF-01 tooling/CI and NF-08 M1 contracts.
- Tests/documentation accompany NF-02–08 milestones; final MVP acceptance depends
  on their completed contracts and integrated flow.
- A real scientific release requires NF-04's separately reviewed Linux/NVIDIA
  runtime and public target panel; a synthetic preview is a separate labeled gate.

## 4. Proposed architecture and interfaces

Preserve existing architecture tests and extend them to new core modules and
application imports. Inject fake catalogs, repositories, clocks, dispatchers,
prediction adapters and comparison fixtures through application composition.
No monkeypatch that silently lets a fake count as successful real inference.

Use temporary SQLite/filesystem stores for persistence/restart integration tests;
run a separately launched fake worker for the vertical slice. Stub HTTP at
transport boundaries for provider contracts. Disable external network access for
ordinary tests, including accidental Mol*/MSA downloads.

M1 uses Vitest, React Testing Library and Playwright after compatibility review,
pinned through npm and its lockfile. Current tests cover the status page; later
milestones add feature tests. Use a fake viewer controller for most UI tests
and a small separate actual-Mol* WebGL suite. Document test commands when created;
M1 commands are recorded below and in the test guide.

Keep CPU locked-install CI mandatory. Add a separately triggered, reviewed GPU
validation path only when hardware and model licensing are available; do not
install CUDA packages into existing API/container jobs. Live upstream probes are
diagnostic and separately classified from offline required contract tests.

## 5. Data models and API contracts

The M1 fixture inventory records fixture ID, synthetic-generation method,
expected invariants, license/author, byte size/hash, units/coordinate convention
and purpose. Synthetic mmCIF can live only in the existing narrow backend fixture
allowlist. For frontend tests, reuse those files via a documented fixture-serving
mechanism or use source string fixtures; do not weaken broad scientific-data ignore
rules. No real sequences, model outputs, weights or research datasets in fixtures.

Future release evidence records code revision, API/frontend/manifest versions,
lockfile hashes, CI run IDs/results, test environment, runtime image/weight
identities, manual review notes, supported target/profile/browser limits, known
limitations and gate outcomes. It contains references/checksums for real validation
artifacts kept outside source control, not the artifacts themselves.

Contract tests must assert implemented `/v1` OpenAPI schemas, statuses, stable
errors, idempotency/cancellation semantics, artifact bytes/headers and response
validation. Maintain NF-01 `GET /health` behavior. Test Python/JSON/frontend
agreement for manifest and DTO schema versions; distinguish safe additive changes
from breaking changes that require versioning.

## 6. Implementation milestones

1. **M1 — Test foundation:** choose/lock frontend tools, fixture inventory and
   offline transport guards; define test matrix, scientific review protocol and
   evidence template with NF-08 contracts.
2. **M2 — Feature coverage:** each NF-02–08 milestone adds unit/API/interaction
   and failure tests before acceptance; enforce architecture and schema contracts.
3. **M3 — Integrated preview:** API plus fake worker plus browser completes the
   workflow and verifies export offline. Exercise restart, partial failure and
   data-integrity recovery; label all outputs synthetic.
4. **M4 — Scientific/operational validation:** review target panel and real
   Boltz-2 runs, define numerical tolerances and performance bounds, validate
   supported environments, container behavior and privacy/license inventory.
5. **M5 — Release review:** finish contributor/user/scientific docs, record every
   release gate and remaining limitation. Obtain separate authorization for any
   future push/publication/PR; this roadmap authorizes none.

## 7. Acceptance criteria and MVP release gates

| Gate | Evidence required |
| --- | --- |
| Foundation | Existing liveness/API/core boundaries remain intact; all locked checks pass |
| Biological integration | Accession/gene/taxon selection, immutable versions, experimental-only discovery, mappings and upstream error contracts covered offline |
| Variants | Strict syntax, range/reference validation, one-change construction, immutability and hashes tested |
| Jobs | Separate worker, durable states, idempotency, cancellation/races, timeout/restart/fencing and integrity failures covered |
| Visualization/workflow | Accessible end-to-end interaction, sample/chain selection, mutation mapping, synthetic badges, missing-data/WebGL and recovery paths |
| Comparison | Analytic rigid/deformed/mirrored fixtures, explicit mapping/selection, RMSD/coverage and uncertainty review |
| Reproducibility | Offline verified export, all required metadata, license/omission inventory and fake replay |
| Real scientific runtime | Exact model/weights/licenses, locked Linux/CUDA environment, measured resource bounds, public reference/variant smoke runs, full provenance and scientific limitations |
| Documentation | Current architecture, setup, fake and real execution, API, export verification, methods, unsupported cases and troubleshooting |
| Operational scope | Declared trusted single-operator topology, retention/recovery, production API routing if deployed, no unsupported remote/multi-user claim |

A fake-only preview may pass the software slice but must not be named the real
scientific MVP. Any unavailable required real-runtime/scientific gate is explicitly
recorded as incomplete; no fabricated success or inference-accuracy claim.

## 8. Automated testing requirements and required commands

| Layer | Representative checks | Environment |
| --- | --- | --- |
| Pure domain | canonicalization, substitution invariants, state/selection validation | Offline CPU; no site-packages for core importability |
| Adapter/unit contracts | malformed/rate-limited upstream fixtures, caching, YAML translation, license/manifest validation | Injected transports and temporary files |
| Service/API integration | routes/errors, SQLite transitions/restarts, worker child lifecycle, artifacts/export | CPU with fake inference, no external services |
| Scientific numerics | known transforms/deformations, ambiguity/gaps, metric denominators/units/tolerances | Tiny synthetic fixtures and optional numerical adapter |
| Frontend interactions | all workflow states, accessibility, request races, polling/cancellation/resume | Component tests with HTTP/controller fakes |
| Browser vertical slice | full flow, actual Mol* subset, offline export verification, error/retry | API + separate fake worker + controlled WebGL/fallback |
| Containers | locked builds, liveness and frontend proxy, non-root CPU services | Docker/Linux CI |
| Optional upstream/GPU | live schema probes and pinned real-runtime scientific smoke protocol | Explicit opt-in; classified separately |

Retain the required commands, executed from `backend/` after `uv sync --locked`:

```sh
uv run --locked ruff check . ../infra/testing
uv run --locked ruff format --check . ../infra/testing
uv run --locked mypy src tests scripts ../infra/testing
uv run --locked pytest
```

From `frontend/` after `npm ci`:

```sh
npm run lint
npm run typecheck
npm run build
npm run test
npm run test:browser:install
npm run test:browser
npm run test:integration
```

M1 adds component/browser scripts and CI steps alongside these checks. Browser
installation needs network access once; Linux CI passes `-- --with-deps`.
Required behavior suites then run with guarded synthetic transports. Keep Python
3.12/3.13 coverage in current CI and Node 24. Keep the backend's existing 90% coverage gate,
but require meaningful negative-path/contract tests rather than chasing coverage
with mirrored implementation assertions.

For infrastructure changes, run `docker compose config --quiet`; when a daemon
is available, build/smoke-test both services and proxy as documented in the
[infra guide](../../infra/README.md). Keep real GPU validation in a separate image
and CI path. Report unavailable checks explicitly.

## 9. Scientific validity and reproducibility

Analytic fixtures establish that implementation computes its declared metric;
they do not establish biological validity. Real smoke runs establish pipeline
execution/provenance on named inputs, not accuracy across disease proteins.
Select a public validation panel with reference/variant pair, structural context,
applicability limits and a disordered or poorly covered case; choose exact targets
with scientific review before M4. Do not cherry-pick only visually favorable cases.

Predeclare comparison settings, sample selection, seed/sampling protocol,
hardware/runtime and justified tolerances. Record observed nondeterminism and
within-protocol sample variation. If a prediction fails or confidence is absent,
preserve the failure/absence rather than replacing it with plausible output.

Contributor docs must explain framework boundaries, optional dependencies, locked
installs, adding adapters/fakes, fixture licensing and artifact ignore rules. User
methods docs must define notation/indexing, source/version selection, experimental
versus predicted evidence, confidence, mapping, RMSD limitations, outbound MSA
disclosure, export verification and why structure differences do not prove causality.

## 10. Risks and unresolved decisions

- **Test compatibility:** M1 pins frontend versions and runs Chromium with and
  without WebGL. Actual Mol* rendering/software WebGL and viewer fallback remain
  NF-05 work; a reliable no-WebGL path is not a reason to skip viewer tests.
- **Real hardware availability:** name an operator/environment before M4; absent
  evidence blocks real MVP release but does not block the synthetic preview.
- **Scientific review:** target panel, protocol/tolerances and interpretation need
  a recorded domain review before M5; passing code checks alone is insufficient.
- **Docs ownership:** update README/current architecture and add feature/method
  guides during implementation, so the proposed roadmap is never misrepresented
  as already shipped behavior. M1 updates the foundation docs only.
- **Deployment:** public exposure, remote scheduling or multiple users require a
  new task and security/operations design; they are outside these release gates.
