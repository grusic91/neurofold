# NeuroFold contributor and agent conventions

NeuroFold is a public Apache-2.0 project for protein structure prediction and
neurodegenerative disease research. Preserve the existing LICENSE and attribution.

## Context Isolation

- Treat NeuroFold as an independent project.
- Do not assume architecture, requirements, or implementation decisions from other
  projects.
- Base decisions only on this repository, its documentation, and the current task.
- Do not access or modify sibling project directories.
- Do not import code, configuration, or dependencies from unrelated repositories.
- Ask for clarification when required information is missing.

## Layout and architectural boundaries

- `backend/src/neurofold/api/`: FastAPI routes, HTTP schemas, and transport concerns.
- `backend/src/neurofold/core/`: framework-independent prediction contracts and
  scientific domain logic. Use Python standard-library types here; never import
  FastAPI, HTTP schemas, or concrete model packages from core.
- `backend/src/neurofold/adapters/`: future implementations of core protocols.
  Load optional model dependencies only when explicitly selected. Keep model
  initialization and inference out of API startup and health checks.
- `frontend/`: React/TypeScript UI. Future Mol* visualization belongs here, behind
  components; communicate with the backend through HTTP, never Python internals.
- `docs/`: architecture, scientific methods, and contributor documentation.
- `infra/`: Docker and future deployment configuration.

Keep dependency direction API -> core <- adapters. A future application service
will select/inject adapters; HTTP handlers must not embed inference algorithms.
Do not introduce a database, authentication, job queue, or model runtime until a
task requires it. NF-01 must not install or execute Boltz-2.

## Development conventions

- Support Python 3.12+; the default development runtime is 3.12. Use a `src`
  layout, type annotations, Ruff formatting/linting, and mypy strict checking.
- Use `uv` and commit `backend/uv.lock`. Use npm and commit
  `frontend/package-lock.json`. Install with `uv sync --locked` and `npm ci`.
  Update manifests and lockfiles together when changing dependencies.
- Use Node.js 24, React function components, strict TypeScript, and ESLint.
- Keep macOS Apple Silicon development CPU-only. Future Linux/NVIDIA CUDA
  dependencies and container images must be separate from the base API runtime.
- Keep changes focused and document new commands and architecture decisions.
- Do not push, publish, or open a pull request without the user's authorization.

## Required checks

The authoritative current checklist is this section; README, task guidance and CI
must match it. Install with `uv sync --locked` and `npm ci` first. CI runs the
backend checks on Python 3.12 and 3.13.

Run from `backend/`:

```sh
uv run --locked ruff check . ../infra/testing
uv run --locked ruff format --check . ../infra/testing
uv run --locked mypy src tests scripts ../infra/testing
uv run --locked pytest
```

Run from `frontend/`:

```sh
npm run lint
npm run typecheck
npm run build
npm run test
npm run test:browser:install
npm run test:browser
npm run test:integration
```

Validate infrastructure changes with `docker compose config --quiet`. When a
Docker daemon is available, build and smoke-test both services. Report unavailable
checks explicitly. CI must enforce the same code checks using locked installs.

Add automated tests for new backend behavior, including errors and public API
contracts. Unit tests must run without networks, GPUs, weights, or research data.
Use small synthetic fixtures and fake adapters for scientific orchestration.
Add frontend behavior tests as interactive features grow. Do not treat lint or
type checking as a substitute for behavior tests.

## Scientific reproducibility

- Every future prediction must carry provenance: input hash and source, model and
  adapter versions, weight checksum/license, parameters, seed, dependency lockfile
  identity, code revision, hardware, OS, and relevant CUDA/library versions.
- Preserve raw outputs and record preprocessing, units, coordinate conventions,
  confidence metric definitions, and transformations. Never silently overwrite
  source data or substitute missing results with plausible predictions.
- Distinguish predictions, measured observations, and hypotheses. Document
  uncertainty and validation limits; avoid unsupported biological claims.
- A fixed seed alone does not guarantee identical GPU results. Record known
  nondeterminism and use justified numerical tolerances in scientific tests.
- Never commit secrets, private sequences, patient information, model weights,
  generated structures, or research datasets. Keep local artifacts in ignored
  `data/`, `datasets/`, `models/`, `weights/`, or `outputs/` directories. Only tiny,
  synthetic, license-compatible fixtures belong in source control.
- Check each future model, weight, and dataset license independently; the
  repository's Apache-2.0 license does not relicense third-party artifacts.
