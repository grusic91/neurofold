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
```

`npm run preview` previews static build output; it does not provide the development
API proxy. Production deployment needs separate routing for `/api`.

The current page reports service status. Mol* visualization and prediction
workflows are planned for later milestones. See [architecture](../docs/architecture.md).
