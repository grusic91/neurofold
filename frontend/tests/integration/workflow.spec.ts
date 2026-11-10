import { test as base, expect } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { gunzipSync } from 'node:zlib'

const test = base.extend<{ external: string[] }>({
  external: [async ({ context }, use) => {
    const blocked: string[] = []
    await context.route('**/*', async route => {
      const url = new URL(route.request().url())
      if (url.origin === 'http://127.0.0.1:4174') return route.continue()
      blocked.push(url.href); await route.abort('blockedbyclient')
    })
    await context.routeWebSocket('**/*', socket => {
      if (new URL(socket.url()).origin === 'ws://127.0.0.1:4174') { socket.connectToServer(); return }
      blocked.push(socket.url()); socket.close()
    })
    await use(blocked)
    expect(blocked).toEqual([])
  }, { auto: true }],
})

test('real browser -> Vite proxy -> production routes -> synthetic services -> durable archive', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('status')).toHaveText('Service is online.')
  await page.getByLabel('Canonical accession', { exact: true }).fill('P00001')
  await page.getByRole('button', { name: 'Inspect accession' }).click()
  await page.getByRole('button', { name: 'Pin inspected reference' }).click()
  const heading = page.getByRole('heading', { name: /^Pinned reference / })
  await expect(heading).toBeVisible()
  const referenceId = (await heading.textContent())!.replace('Pinned reference ', '')
  await page.getByRole('button', { name: 'Discover experimental structures / restart' }).click()
  await page.getByRole('button', { name: 'Select 1SYN chain A' }).click()
  await page.getByLabel('Model ID', { exact: true }).fill('2')
  await page.getByLabel('Coordinate selection').selectOption('assembly')
  await page.getByLabel('Assembly ID', { exact: true }).fill('1')
  await page.getByLabel('Operator ID / product').fill('2')
  await page.getByRole('button', { name: 'Import inspected structure' }).click()
  const result = page.getByRole('article', { name: 'Retained structure' })
  await expect(result).toBeVisible()
  const structureId = (await result.getByRole('heading').textContent())!.replace('Retained structure ', '')
  await expect(result.getByText(/original deposited Cartesian frame/)).toBeVisible()
  await expect(result.getByText('unobserved', { exact: true })).toHaveCount(2)
  const link = result.getByRole('link', { name: 'Download registered original structure (.gz)' })
  const artifactPath = await link.getAttribute('href')
  const responseReady = page.waitForResponse(response => new URL(response.url()).pathname === artifactPath)
  const downloadReady = page.waitForEvent('download')
  await link.click()
  const response = await responseReady
  const download = await downloadReady
  const bytes = await readFile((await download.path())!)
  const headers = response.headers()
  expect(headers['content-type']).toBe('application/gzip')
  expect(headers['content-encoding']).toBeUndefined()
  expect(headers['content-length']).toBe(String(bytes.length))
  expect(headers['x-checksum-sha256']).toBe(createHash('sha256').update(bytes).digest('hex'))
  expect(gunzipSync(bytes)).toEqual(await readFile('../backend/tests/fixtures/structure-synthetic-v1.cif'))
  await page.reload()
  await page.getByLabel('Reference ID', { exact: true }).fill(referenceId)
  await page.getByRole('button', { name: 'Open reference ID' }).click()
  await expect(page.getByRole('heading', { name: `Pinned reference ${referenceId}` })).toBeVisible()
  await page.getByLabel('Structure ID', { exact: true }).fill(structureId)
  await page.getByRole('button', { name: 'Open structure ID' }).click()
  await expect(page.getByRole('article', { name: 'Retained structure' })).toBeVisible()
  await expect(page.getByText('Retained numbering, assemblies, coverage and validation audit', { exact: true })).toBeVisible()
})
