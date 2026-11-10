import { defineConfig, devices } from '@playwright/test'
import { mkdtempSync, realpathSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// One private ignored archive per invocation. Both servers are local; backend
// composition selects an explicit synthetic transport with no network IO.
const archive = join(realpathSync(mkdtempSync(join(tmpdir(), 'neurofold-m4-browser-'))), 'data/archive')
export default defineConfig({
  testDir: './tests/integration',
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:4174', serviceWorkers: 'block', trace: 'retain-on-failure' },
  webServer: [
    { command: 'uv run --locked uvicorn offline_server:compressed_app --app-dir ../infra/testing --host 127.0.0.1 --port 8001', cwd: '../backend', url: 'http://127.0.0.1:8001/health', reuseExistingServer: false, env: { NEUROFOLD_ARCHIVE_ROOT: archive, UV_CACHE_DIR: process.env.UV_CACHE_DIR || '/tmp/neurofold-uv-cache' } },
    { command: 'npm run dev -- --host 127.0.0.1 --port 4174 --strictPort', url: 'http://127.0.0.1:4174', reuseExistingServer: false, env: { API_PROXY_TARGET: 'http://127.0.0.1:8001' } },
  ],
})
