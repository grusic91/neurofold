import { readFile } from 'node:fs/promises'
import { backendExchange } from '../../src/test/exchange'
import { test, expect } from './offline'

// These are actual production-ASGI/service/parser/archive responses, produced
// under Python socket/DNS guards. Browser requests are still route mocks.
const data = backendExchange()
const refPath = `/api/v1/references/${data.reference.reference_id}`
const structPath = `/api/v1/structures/${data.structure.descriptor.structure_id}`

test('selects a protein, pins, imports an explicit assembly copy and downloads exact original bytes', async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({ json: { status: 'ok' } }))
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (path === '/api/v1/proteins') return route.fulfill({ json: data.proteinPage })
    if (path === '/api/v1/proteins/P00001') return route.fulfill({ json: data.protein })
    if (path === '/api/v1/references' && request.method() === 'POST') {
      expect(request.postDataJSON()).toEqual({ accession: 'P00001', expected_sequence_sha256: data.protein.sequence_hash.sha256 })
      return route.fulfill({ status: 201, json: data.reference, headers: { Location: refPath.slice(4) } })
    }
    if (path === refPath + '/audit') return route.fulfill({ json: data.pinAudit })
    if (path === refPath + '/structures') return route.fulfill({ json: data.structurePage })
    if (path === '/api/v1/structures' && request.method() === 'POST') {
      expect(request.postDataJSON().model_id).toBe('2')
      expect(request.postDataJSON().operator_id.value).toBe('2')
      return route.fulfill({ status: 201, json: data.structure, headers: { Location: structPath.slice(4) } })
    }
    if (path === structPath + '/audit') return route.fulfill({ json: data.structureAudit })
    if (path === '/api' + data.structure.artifact_url) return route.fulfill({ body: Buffer.from(data.original, 'base64'), headers: data.headers })
    await route.fallback()
  })
  await page.goto('/')
  await page.getByLabel('Exact gene', { exact: true }).fill('SYNTH')
  await page.getByLabel('Taxon ID (optional)').fill('1')
  await page.getByRole('button', { name: 'Search gene' }).click()
  await expect(page.getByRole('button', { name: 'Inspect P00002' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Inspected P00001' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Inspect P00001' }).click()
  await page.getByRole('button', { name: 'Pin inspected reference' }).click()
  await page.getByRole('button', { name: 'Discover experimental structures / restart' }).click()
  await page.getByRole('button', { name: 'Select 1SYN chain A' }).click()
  await expect(page.getByRole('button', { name: 'Import inspected structure' })).toBeDisabled()
  await page.getByLabel('Model ID', { exact: true }).fill('2')
  await page.getByLabel('Coordinate selection').selectOption('assembly')
  await page.getByLabel('Assembly ID', { exact: true }).fill('1')
  await page.getByLabel('Operator ID / product').fill('2')
  await page.getByRole('button', { name: 'Import inspected structure' }).click()
  const article = page.getByRole('article', { name: 'Retained structure' })
  await expect(article.getByText(/original deposited Cartesian frame/)).toBeVisible()
  await expect(article.getByText('unobserved', { exact: true })).toHaveCount(2)
  await expect(article.getByText(/authored synthetic example/, { exact: false }).first()).toBeVisible()
  await article.getByText('Retained numbering, assemblies, coverage and validation audit', { exact: true }).click()
  await expect(article.getByText(/Scheme author numbers and scheme PDB numbers/)).toBeVisible()
  const downloadReady = page.waitForEvent('download')
  await article.getByRole('link', { name: 'Download registered original structure' }).click()
  const download = await downloadReady
  const saved = await download.path()
  expect(saved).not.toBeNull()
  expect(await readFile(saved!)).toEqual(Buffer.from(data.original, 'base64'))
})

test('reopens offline records and preserves them when a provider operation fails', async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({ json: { status: 'ok' } }))
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === refPath) return route.fulfill({ json: data.reference })
    if (path === refPath + '/audit') return route.fulfill({ json: data.pinAudit })
    if (path === refPath + '/structures') return route.fulfill({ json: { ...data.structurePage, availability: 'unavailable', items: [], warnings: ['RCSB discovery unavailable; retry explicitly.'] } })
    if (path === structPath) return route.fulfill({ json: data.structure })
    if (path === structPath + '/audit') return route.fulfill({ json: data.structureAudit })
    await route.fallback()
  })
  await page.goto('/')
  await page.getByLabel('Reference ID', { exact: true }).fill(data.reference.reference_id)
  await page.getByRole('button', { name: 'Open reference ID' }).click()
  await page.getByLabel('Structure ID', { exact: true }).fill(data.structure.descriptor.structure_id)
  await page.getByRole('button', { name: 'Open structure ID' }).click()
  await expect(page.getByRole('article', { name: 'Retained structure' })).toBeVisible()
  await page.getByRole('button', { name: 'Discover experimental structures / restart' }).click()
  await expect(page.getByText(/Discovery could not establish an empty result/)).toBeVisible()
  await expect(page.getByRole('heading', { name: `Pinned reference ${data.reference.reference_id}` })).toBeVisible()
  await expect(page.getByRole('article', { name: 'Retained structure' })).toBeVisible()
})
