import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import Workflow from './Workflow'
import { backendExchange } from './test/exchange'
import { present } from './api'

const data = backendExchange()
type Handler = (init: RequestInit) => Response | Promise<Response>
let unmatched: string[] = []
function mock(routes: Record<string, Handler>) {
  unmatched = []
  const fetch = vi.fn(async (input: string, init: RequestInit) => {
    const key = `${init.method} ${input}`
    if (!routes[key]) { unmatched.push(key); throw new Error('Unmatched offline request') }
    return routes[key](init)
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}
afterEach(() => expect(unmatched).toEqual([]))
const refPath = `/api/v1/references/${data.reference.reference_id}`
const structurePath = `/api/v1/structures/${data.structure.descriptor.structure_id}`
const refResponse = () => Response.json(data.reference, { status: 201, headers: { Location: refPath.slice(4) } })
const structureResponse = () => Response.json(data.structure, { status: 201, headers: { Location: structurePath.slice(4) } })
const error = (status: number, code: string, details = {}) => Response.json({ error: { code, message: 'Synthetic operation failure.', retryable: status === 429 || status === 503, details, request_id: 'synthetic-request' } }, { status })
function referenceRoutes(): Record<string, Handler> {
  return { [`GET ${refPath}`]: () => Response.json(data.reference), [`GET ${refPath}/audit`]: () => Response.json(data.pinAudit) }
}
async function openReference() {
  fireEvent.change(screen.getByLabelText('Reference ID'), { target: { value: data.reference.reference_id } })
  fireEvent.click(screen.getByRole('button', { name: 'Open reference ID' }))
  await screen.findByRole('heading', { name: `Pinned reference ${data.reference.reference_id}` })
}
async function inspectProtein() {
  fireEvent.change(screen.getByLabelText('Canonical accession'), { target: { value: 'P00001' } })
  fireEvent.click(screen.getByRole('button', { name: 'Inspect accession' }))
  await screen.findByRole('heading', { name: 'Inspected P00001' })
}

it('requires explicit gene candidate/organism selection, paginates and pins the inspected hash', async () => {
  const fetch = mock({
    'GET /api/v1/proteins?gene=SYNTH&limit=20&taxon_id=1': () => Response.json({ ...data.proteinPage, next_cursor: present('opaque') }),
    'GET /api/v1/proteins?gene=SYNTH&limit=20&taxon_id=1&cursor=opaque': () => Response.json(data.proteinPage),
    'GET /api/v1/proteins/P00001': () => Response.json(data.protein),
    'POST /api/v1/references': init => { expect(JSON.parse(String(init.body))).toEqual({ accession: 'P00001', expected_sequence_sha256: data.protein.sequence_hash.sha256 }); return refResponse() },
    ...referenceRoutes(),
  })
  render(<Workflow />)
  fireEvent.change(screen.getByLabelText('Exact gene'), { target: { value: 'SYNTH' } })
  fireEvent.change(screen.getByLabelText('Taxon ID (optional)'), { target: { value: '1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search gene' }))
  await screen.findByRole('button', { name: 'Inspect P00002' })
  expect(screen.queryByRole('heading', { name: 'Inspected P00001' })).not.toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', { name: 'Next protein page' }))
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Next protein page' })).not.toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: 'Inspect P00001' }))
  await screen.findByRole('heading', { name: 'Inspected P00001' })
  fireEvent.click(screen.getByRole('button', { name: 'Pin inspected reference' }))
  await screen.findByRole('heading', { name: `Pinned reference ${data.reference.reference_id}` })
  expect(screen.getAllByText(/synthetic example/).length).toBeGreaterThan(0)
})

it('opens retained IDs, preserves partial candidates, explicitly imports and exposes numbering/downloads', async () => {
  mock({ ...referenceRoutes(),
    [`GET ${refPath}/structures?limit=20`]: () => Response.json({ ...data.structurePage, availability: 'partial', warnings: ['1SYN.B: provider unavailable'] }),
    'POST /api/v1/structures': init => { const body = JSON.parse(String(init.body)); expect(body.model_id).toBe('2'); expect(body.expected_source_revision).toEqual(data.structurePage.items[0].source_revision); expect(body).not.toHaveProperty('auth_asym_id'); return structureResponse() },
    [`GET ${structurePath}/audit`]: () => Response.json(data.structureAudit),
  })
  render(<Workflow />); await openReference()
  fireEvent.click(screen.getByRole('button', { name: 'Discover experimental structures / restart' }))
  await screen.findByText('1SYN.B: provider unavailable')
  fireEvent.click(screen.getByRole('button', { name: 'Select 1SYN chain A' }))
  expect(screen.getByRole('button', { name: 'Import inspected structure' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Model ID'), { target: { value: '2' } })
  fireEvent.change(screen.getByLabelText('Coordinate selection'), { target: { value: 'assembly' } })
  fireEvent.change(screen.getByLabelText('Assembly ID'), { target: { value: '1' } })
  fireEvent.change(screen.getByLabelText('Operator ID / product'), { target: { value: '2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Import inspected structure' }))
  const result = await screen.findByRole('article', { name: 'Retained structure' })
  expect(within(result).getByText(/Cartesian frame, in angstroms/)).toBeInTheDocument()
  expect(within(result).getByText(/Missing coordinates do not mean/)).toBeInTheDocument()
  expect(within(result).getAllByText('unobserved').length).toBe(2)
  expect(within(result).getByRole('link', { name: 'Download registered original structure' })).toHaveAttribute('href', '/api' + data.structure.artifact_url)
  await screen.findByText('Retained numbering, assemblies, coverage and validation audit')
  expect(screen.getByText(/Scheme author numbers and scheme PDB numbers/)).toBeInTheDocument()
})

it.each([[409, 'SOURCE_CHANGED', /source changed/i], [429, 'ADMISSION_LIMIT', /capacity is full/i], [503, 'UPSTREAM_UNAVAILABLE', /retry the requested operation/i]])('preserves completed selections after %s and never retries mutations automatically', async (status, code, recovery) => {
  const fetch = mock({ ...referenceRoutes(), 'GET /api/v1/proteins/P00001': () => Response.json(data.protein), 'POST /api/v1/references': () => error(Number(status), String(code)) })
  render(<Workflow />); await openReference(); await inspectProtein()
  fireEvent.click(screen.getByRole('button', { name: 'Pin inspected reference' }))
  await screen.findByRole('alert')
  expect(screen.getByText(recovery)).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: `Pinned reference ${data.reference.reference_id}` })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Inspected P00001' })).toBeInTheDocument()
  expect(fetch.mock.calls.filter(([, init]) => init.method === 'POST')).toHaveLength(1)
})

it('rejects local invalid inputs and refuses unsupported isoform pinning', async () => {
  mock({ 'GET /api/v1/proteins/P00001': () => Response.json({ ...data.protein, summary: { ...data.protein.summary, canonical: false } }) })
  render(<Workflow />)
  fireEvent.change(screen.getByLabelText('Exact gene'), { target: { value: 'TWO TOKENS' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search gene' }))
  expect(screen.getByRole('alert')).toHaveTextContent('one exact gene token')
  await inspectProtein()
  expect(screen.getByRole('button', { name: 'Pin inspected reference' })).toBeDisabled()
})

it('discards stale inspections and aborts on unmount', async () => {
  let resolve!: (response: Response) => void
  let signal!: AbortSignal
  mock({ 'GET /api/v1/proteins/P00001': init => { signal = init.signal as AbortSignal; return new Promise<Response>(done => { resolve = done }) }, 'GET /api/v1/proteins/P00002': () => Response.json({ ...data.protein, summary: { ...data.protein.summary, accession: 'P00002' } }) })
  const { unmount } = render(<Workflow />)
  fireEvent.change(screen.getByLabelText('Canonical accession'), { target: { value: 'P00001' } })
  fireEvent.click(screen.getByRole('button', { name: 'Inspect accession' }))
  // Explicit candidate selection can supersede an in-flight direct lookup.
  // Trigger form submit directly to exercise a caller that replaces a request.
  fireEvent.change(screen.getByLabelText('Canonical accession'), { target: { value: 'P00002' } })
  fireEvent.submit(screen.getByLabelText('Canonical accession').closest('form')!)
  await screen.findByRole('heading', { name: 'Inspected P00002' })
  expect(signal.aborted).toBe(true)
  await act(async () => resolve(Response.json(data.protein)))
  expect(screen.queryByRole('heading', { name: 'Inspected P00001' })).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Canonical accession'), { target: { value: 'P00001' } })
  fireEvent.click(screen.getByRole('button', { name: 'Inspect accession' }))
  unmount(); expect(signal.aborted).toBe(true)
})

it('reopens a structure without discovery and preserves ambiguity and missing identifiers', async () => {
  const record = structuredClone(data.structure)
  if (!('rows' in record.mapping)) throw new Error('Expected synthetic map')
  record.mapping.rows[0] = { ...record.mapping.rows[0], status: 'ambiguous', reference_position: { state: 'unavailable', value: null, reason: 'Repeated domain' }, reference_residue: { state: 'unavailable', value: null, reason: 'Repeated domain' }, candidate_reference_positions: [1, 3], reason: 'Equally valid assignments' }
  record.mapping.rows[1] = { ...record.mapping.rows[1], status: 'mismatch', reason: 'Construct substitution' }
  record.mapping.rows[3] = { ...record.mapping.rows[3], status: 'unmapped', reference_position: { state: 'not_applicable', value: null, reason: 'Construct tag' }, reference_residue: { state: 'not_applicable', value: null, reason: 'Construct tag' }, reason: 'Polymer tag outside reference' }
  mock({ [`GET ${structurePath}`]: () => Response.json(record), [`GET ${structurePath}/audit`]: () => Response.json(data.structureAudit) })
  render(<Workflow />)
  fireEvent.change(screen.getByLabelText('Structure ID'), { target: { value: data.structure.descriptor.structure_id } })
  fireEvent.click(screen.getByRole('button', { name: 'Open structure ID' }))
  await screen.findByRole('article', { name: 'Retained structure' })
  for (const state of ['exact', 'mismatch', 'unobserved', 'unmapped', 'ambiguous']) expect(screen.getAllByText(state).length).toBeGreaterThan(0)
  expect(screen.getByText('1, 3')).toBeInTheDocument()
  expect(screen.getByText('Equally valid assignments')).toBeInTheDocument()
  expect(screen.getAllByText(/unavailable:/).length).toBeGreaterThan(0)
})

it('preserves retained structure and reports a failed original download without navigation', async () => {
  mock({ [`GET ${structurePath}`]: () => Response.json(data.structure), [`GET ${structurePath}/audit`]: () => Response.json(data.structureAudit), [`GET /api${data.structure.artifact_url}`]: () => error(500, 'ARCHIVE_INTEGRITY') })
  render(<Workflow />)
  fireEvent.change(screen.getByLabelText('Structure ID'), { target: { value: data.structure.descriptor.structure_id } })
  fireEvent.click(screen.getByRole('button', { name: 'Open structure ID' }))
  await screen.findByRole('article', { name: 'Retained structure' })
  fireEvent.click(screen.getByRole('link', { name: 'Download registered original structure' }))
  await screen.findByRole('alert')
  expect(screen.getByRole('article', { name: 'Retained structure' })).toBeInTheDocument()
  expect(screen.getByText(/ARCHIVE_INTEGRITY/)).toBeInTheDocument()
})

it('restarts an invalid cursor and distinguishes a complete empty search', async () => {
  let first = true
  mock({
    'GET /api/v1/proteins?gene=SYNTH&limit=20': () => { const response = first ? { ...data.proteinPage, next_cursor: present('expired') } : { ...data.proteinPage, items: [] }; first = false; return Response.json(response) },
    'GET /api/v1/proteins?gene=SYNTH&limit=20&cursor=expired': () => error(400, 'INVALID_CURSOR'),
  })
  render(<Workflow />)
  fireEvent.change(screen.getByLabelText('Exact gene'), { target: { value: 'SYNTH' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search gene' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Next protein page' }))
  await screen.findByRole('alert')
  expect(screen.getByText(/restart from the first page/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Restart protein search' }))
  await screen.findByText('No matching candidates.')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
