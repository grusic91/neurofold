# NeuroFold

An open-source computational biology platform for protein structure prediction
and neurodegenerative disease research. Licensed under [Apache 2.0](LICENSE).

NeuroFold aims to make prediction workflows modular, inspectable, and scientifically
reproducible, and to support molecular exploration with Mol*.

**Implemented: NF-01, NF-08 M1 shared provenance contracts, NF-09 M1 test
foundation, and NF-02 M1 biological data contracts.** The API exposes a tested
health endpoint and the frontend displays service status. Shared immutable provenance contracts and offline backend,
component and browser tests are present. [Biological contracts](docs/biological-contracts.md)
and [source licensing inventory](docs/source-licensing.md) are implemented;
lookup, pinning and structure imports await NF-02 M2–M4. Prediction,
molecular visualization, complete manifests and exports remain future work.
Boltz-2 is planned; it is not installed or executed.

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
    core/           Standard-library-only prediction, provenance and biological contracts
    adapters/       Future model adapter implementations
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
No CUDA, database, authentication service, weights, or research data is required.

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
Host ports bind to loopback. The frontend container talks to `http://backend:8000`
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

## Checks

From `backend/`, after `uv sync --locked`:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests
uv run --locked pytest
```

Pytest checks liveness/OpenAPI, core contracts/canonical hashes, biological/HTTP
schemas, fixture integrity,
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
```

Browser installation downloads pinned Chromium once; Linux CI additionally uses
`npm run test:browser:install -- --with-deps`. Component/browser behavior tests
use synthetic health responses and require no backend or external service.
See the [test foundation guide](docs/testing/README.md),
[test matrix](docs/testing/test-matrix.md),
[scientific review protocol](docs/testing/scientific-review.md) and
[evidence template](docs/testing/evidence-template.md).

GitHub Actions runs these checks on pushes and pull requests, with Python 3.12
and 3.13 and Node 24. A separate job builds and smoke-tests the development
containers and proxy on Linux. It does not publish images or deploy anything.

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
