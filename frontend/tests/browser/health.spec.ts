import { test, expect } from './offline'

test('renders checking then online with a synthetic health response', async ({ page }) => {
  let release!: () => void
  const responseReady = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/api/health', async (route) => {
    await responseReady
    await route.fulfill({ json: { status: 'ok' } })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'NeuroFold', exact: true })).toBeVisible()
  await expect(page.getByRole('status')).toHaveText('Checking service status…')
  release()
  await expect(page.getByRole('status')).toHaveText('Service is online.')
})

test('shows unavailable on HTTP failure', async ({ page }) => {
  await page.route('**/api/health', (route) => route.fulfill({ status: 503, body: '' }))
  await page.goto('/')
  await expect(page.getByRole('status')).toContainText('Service is unavailable.')
})

test('rejects an incompatible health response', async ({ page }) => {
  await page.route('**/api/health', (route) => route.fulfill({ json: { status: 'ready' } }))
  await page.goto('/')
  await expect(page.getByRole('status')).toContainText('Service is unavailable.')
})

test('blocks accidental external HTTP and WebSocket traffic', async ({ page, blockedRequests }) => {
  await page.route('**/api/health', (route) => route.fulfill({ json: { status: 'ok' } }))
  await page.goto('/')
  await expect(page.getByRole('status')).toHaveText('Service is online.')
  const failed = await page.evaluate(async () => {
    try {
      await fetch('https://example.invalid/guard-probe')
      return false
    } catch { return true }
  })
  expect(failed).toBe(true)
  await page.evaluate(() => new Promise<void>((resolve) => {
    const socket = new WebSocket('wss://example.invalid/guard-probe')
    socket.onclose = () => resolve()
  }))
  expect(blockedRequests.splice(0).sort()).toEqual([
    'https://example.invalid/guard-probe',
    'wss://example.invalid/guard-probe',
  ])
})
