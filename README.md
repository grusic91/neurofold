# NeuroFold

An open-source computational biology platform for protein structure prediction
and neurodegenerative disease research. Licensed under [Apache 2.0](LICENSE).

NeuroFold aims to make prediction workflows modular, inspectable, and scientifically
reproducible, and to support molecular exploration with Mol*.

**Implemented: NF-01, NF-08 M1 provenance contracts, NF-09 M1 test foundation,
NF-02 M1–M4 biological data integration, and NF-03 M1–M3 substitutions,
immutable variant storage and HTTP integration, plus NF-04 M1 contracts and M2 durable orchestration.**
The API serves canonical protein
lookup, immutable reference pinning, experimental structure discovery/import,
retained residue maps/audits and registered original artifacts. The frontend
provides explicit protein/organism/model/assembly selection, provenance,
numbering/uncertainty tables and reopening retained IDs. `/health` remains a
liveness endpoint with no provider, archive or scientific readiness probe.
See [integration/configuration decisions](docs/integration.md),
[biological contracts](docs/biological-contracts.md),
[UniProt lookup](docs/uniprot-lookup.md),
[structure import](docs/structure-import.md) and
[source licensing](docs/source-licensing.md).
The [substitution domain](docs/variants.md) parses and validates one substitution
against the complete pinned reference, constructs the exact sequence/hash and
reports immutable differences. NF-03 M2 adds reference-aware content IDs, an
injected offline variant service and atomic immutable archives with load-time
derivation checks. M3 exposes strict `POST /v1/variants` (201 winner / 200
verified duplicate, both with Location) and `GET /v1/variants/{variant_id}`.
Results are sequence hypotheses; frontend variant interaction remains NF-07 work.
See [HTTP contracts and recovery](docs/variants.md#m3-http-contract) and
[executed M3 evidence](docs/testing/nf03-m3-evidence.md).
[NF-04 M1](docs/prediction-contracts.md) adds strict capabilities, resolved exact
inputs, lifecycle/attempt proposals, sample/confidence/mapping records and complete
successful-provenance/publication validators. M2 adds SQLite jobs/idempotency, separately launched process supervision,
transactional fenced publication, verified retained reads and prediction HTTP
routes. All shipped profiles remain contract-only/unavailable: no executable fake
adapter, frontend polling or real runtime is installed. See
[orchestration and recovery](docs/prediction-orchestration.md) and
[M2 evidence](docs/testing/nf04-m2-evidence.md). M3 fake execution/frontend polling,
M4/M5 reviewed Boltz-2, viewing, comparisons, exports and independent scientific
acceptance remain open.

## Objectives

- Provide a consistent interface to protein structure prediction models.
- Support structure exploration and research on neurodegenerative disease.
- Track inputs, model versions, parameters, and execution environments so future
  scientific results can be audited and reproduced.
- Keep ordinary development usable on macOS Apple Silicon without GPU packages;
  run future inference separately on Linux with NVIDIA CUDA hardware.

## Repository and architecture

```text
backend/
  src/neurofold/
    api/            FastAPI application, routes, and HTTP schemas
    core/           Standard-library-only contracts and pure substitution logic
    adapters/       UniProt/RCSB, CIF/alignment and immutable storage adapters
    application/    Reference, structure, variant and prediction orchestration
  tests/            Offline HTTP, core, fixture and architectural boundary tests
  pyproject.toml    Dependencies, lint, formatting, types, and test settings
  uv.lock           Locked Python dependencies
frontend/           React, TypeScript, Vite; future Mol* integration
docs/               Architecture and scientific development notes
infra/docker/       Local development Dockerfiles
.github/workflows/  Backend, frontend, and container CI
compose.yaml        Local development services
```

Dependency direction is **API → core ← adapters**. Core does not import FastAPI
or model libraries. Future orchestration will inject model adapters instead of
putting inference inside HTTP handlers. See [architecture details](docs/architecture.md)
and [contributor conventions](AGENTS.md).

## Local development

Prerequisites: Git, [uv](https://docs.astral.sh/uv/getting-started/installation/)
0.13.7, Python 3.12+ (uv can download 3.12), and Node.js 24 with npm.
`backend/.python-version` selects Python 3.12; `frontend/.nvmrc` selects Node 24.
Docker with Compose is an alternative to installing the application toolchains.
No CUDA, external database, authentication service, weights or research data is required.
M2 uses Python’s standard-library SQLite only when prediction storage is accessed.

```sh
git clone https://github.com/grusic91/neurofold.git
cd neurofold
```

Start the backend in one terminal:

```sh
cd backend
uv sync --locked
uv run --locked uvicorn neurofold.api.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal, from the repository root:

```sh
cd frontend
# If you use nvm: nvm install && nvm use
npm ci
npm run dev
```

Open <http://localhost:5173>. API documentation is at
<http://127.0.0.1:8000/docs>, and
`curl http://127.0.0.1:8000/health` returns `{"status":"ok"}`.
This endpoint reports API liveness; it makes no model or GPU readiness claim.
Biological operations lazily create `backend/data/archive` when run from
`backend/`. Keep this private durable archive: caches are replaceable; retained
records are not. Copy `backend/.env.example` to `backend/.env` and explicitly
load it with `uv run --locked --env-file .env uvicorn neurofold.api.main:app`
for custom settings. One operator and one API process are supported.
[Configuration, resource limits, recovery and HTTP errors](docs/integration.md)
include timed-out mutation/publication behavior.

The Vite development server proxies `/api/*` to the backend, stripping `/api`.
The browser uses `/api/health`; FastAPI serves `/health`. This keeps development
requests on the same origin without adding permissive CORS middleware.
To change the backend target, copy `frontend/.env.example` to `frontend/.env`,
set `API_PROXY_TARGET`, and restart Vite. No environment file is required for defaults.
Variables prefixed `VITE_` are public browser configuration and must never contain
secrets. Vite's production preview serves static assets only; a deployment reverse
proxy for `/api` will be needed for a production build.

## Docker development

Start Docker Desktop or another Docker daemon, then run from the repository root:

```sh
docker compose config --quiet
docker compose up --build --wait
```

Use the same URLs as above. Both services run as non-root users, use native
container dependencies, and mount application source read-only for live reload.
The private `biological-archive` named volume preserves retained records across
container recreation. `docker compose down` retains it; `down --volumes` deletes
it deliberately. Host ports bind to loopback. The frontend container talks to `http://backend:8000`
over the Compose network. On Apple Silicon, no forced x86 emulation is configured.

Copy `.env.example` to `.env` to override `BACKEND_PORT` or `FRONTEND_PORT` for
Compose. These variables affect host ports only; the container proxy is unchanged.
Rebuild after dependency/configuration changes. View logs or stop services with:

```sh
docker compose logs --follow
docker compose down
```

These are development images using a Vite server and API reload. Production
serving and a separate CUDA inference image are deferred; see [infra notes](infra/README.md).

## Separate prediction worker

From `backend/`, run `uv run --locked python -m neurofold.worker` independently
of Uvicorn, using the same `NEUROFOLD_ARCHIVE_ROOT`. In Compose use
`docker compose --profile worker up --build --detach worker`.
The worker polls durable jobs; M2 deliberately has no executable profile and
production submission reports unavailable. Health/capabilities remain usable.
See the orchestration guide for strict submission schemas, code-identity
configuration, leases, cancellation, restart and integrity recovery. The explicit
`compose.prediction-test.yaml` runs controlled authored-output children only.

## Checks

From `backend/`, after `uv sync --locked`:

```sh
uv run --locked ruff check . ../infra/testing
uv run --locked ruff format --check . ../infra/testing
uv run --locked mypy src tests scripts ../infra/testing
uv run --locked pytest
```

Pytest checks liveness/OpenAPI, core contracts/canonical hashes, biological/HTTP
schemas, experimental-only discovery/import and residue maps, fixture integrity,
offline guards and core importability without third-party packages. Internet
sockets and DNS are blocked by default. Coverage must be at least 90%.
To apply Python formatting, run `uv run --locked ruff format .`.

From `frontend/`, after `npm ci`:

```sh
npm run lint
npm run typecheck
npm run build
npm run test
npm run test:browser:install
npm run test:browser
npm run test:integration
```

Browser installation downloads pinned Chromium once; Linux CI additionally uses
`npm run test:browser:install -- --with-deps`. Component and static-browser behavior tests
use synthetic responses and require no listening backend or external service.
Run `uv sync --locked` in `backend/` first: frontend contract/component/browser
tests invoke a socket/DNS-guarded Python child to produce actual application
responses. This establishes offline contract exchange; static-browser HTTP is mocked.
`test:integration` additionally starts a local synthetic API and Vite proxy,
then exercises real browser HTTP, pin/import, retained records and original gzip
downloads. Unmatched external browser traffic fails in both layers.
See the [test foundation guide](docs/testing/README.md),
[test matrix](docs/testing/test-matrix.md),
[scientific review protocol](docs/testing/scientific-review.md) and
[evidence template](docs/testing/evidence-template.md).

GitHub Actions runs these checks on pushes and pull requests, with Python 3.12
and 3.13 and Node 24. A separate job builds and smoke-tests the development
containers and proxy on Linux. It does not publish images or deploy anything.
See [operational checks](docs/testing/operational-checks.md) for a disposable Linux
runner, container retention checks and the separate explicitly enabled public
provider probe. [Executed evidence](docs/testing/nf02-operational-evidence.md)
records the bounded compatibility scope; independent scientific review remains open.

For dependency changes, edit the Python manifest and run `uv lock` / `uv sync`,
or use `npm install <package>` in `frontend/`. Review and commit the corresponding
lockfile. Normal installs and CI use `--locked` / `npm ci` to prevent silent updates.

## Scientific data and licensing

Keep secrets in ignored local environment files and use synthetic fixtures for
tests. Never commit model weights, research datasets, patient information, or
generated prediction artifacts. Local `data/`, `datasets/`, `models/`, `weights/`,
and `outputs/` directories and common scientific artifact extensions are ignored
and excluded from Docker build contexts. Ignore rules are a guardrail; review
every change before committing. Scientific provenance requirements are documented
in [AGENTS.md](AGENTS.md#scientific-reproducibility).

The original [Apache 2.0 license](LICENSE) is preserved. Future model weights,
datasets, and third-party components require separate license review.
