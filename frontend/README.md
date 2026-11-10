# NeuroFold frontend

React and strict TypeScript with Vite. Requires Node.js 24; use `nvm install` and
`nvm use` here if nvm is installed.

```sh
npm ci
npm run dev
```

Open <http://localhost:5173>. The development server proxies `/api/*` to
`http://127.0.0.1:8000`, stripping `/api`. Start the backend using the
[root setup instructions](../README.md#local-development). Copy `.env.example` to
`.env` to change the server-only `API_PROXY_TARGET`, then restart Vite. No secrets
belong in `VITE_*` variables because those are included in public browser code.

```sh
npm run lint
npm run typecheck
npm run build
npm run test
npm run test:browser:install
npm run test:browser
```

`npm run preview` previews static build output; it does not provide the development
API proxy. Production deployment needs separate routing for `/api`.

Vitest/React Testing Library exercises status behavior and failure/timeout/abort
paths with explicit HTTP fakes. Playwright builds and serves the page on its own
port 4173 with synthetic health responses, in Chromium and Chromium without
WebGL. Unmatched HTTP/WebSocket requests fail browser tests. No backend, weights,
GPU or research data is needed. Install downloads Chromium once; Linux CI adds
`-- --with-deps`. See [testing policy and matrix](../docs/testing/README.md).

The current page reports service status. Mol* visualization and prediction
workflows are planned for later milestones. See [architecture](../docs/architecture.md).


NF-02 M4 adds the protein/reference/experimental-structure workflow over
`/api/v1`. Configure only the public API origin/prefix with `VITE_API_BASE`
(default `/api`); `API_PROXY_TARGET` remains Vite server configuration. Backend
links are checked registry paths and resolved through that base. There is no
viewer or comparison engine. See [integration decisions](../docs/integration.md).

Tests require the repository's backend locked environment (`cd backend && uv sync
--locked`) and uv. A socket/DNS-guarded Python child creates actual production
ASGI responses for TypeScript contract/component/browser tests. No API listener
or provider network is used. Playwright HTTP responses remain explicitly mocked;
only the local static preview is served. Run lint, typecheck, build, test and
`test:browser` as documented at repository root.


`npm run test:integration` separately launches a local synthetic API and the real
Vite proxy with unmocked browser HTTP. It tests retained pin/import and original
gzip downloads while rejecting external traffic. This is additional to the
static-built mocked browser suite; it requires local loopback listeners and
pinned Chromium, not live providers or Docker.
