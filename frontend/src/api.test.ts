import { expect, it, vi } from 'vitest'
import * as api from './api'
import { backendExchange } from './test/exchange'

const data = backendExchange()
it('validates actual backend route/service/archive responses and original bytes', () => {
  expect(data.protein.summary.accession).toBe('P00001')
  expect(data.reference.protein.sequence_hash).toEqual(data.protein.sequence_hash)
  expect(data.pinAudit.response_status).toBe(304)
  expect(data.structure.descriptor.evidence).toBe('synthetic')
  expect(data.structureAudit.parsing.transform_applied).toBe(false)
  expect(Buffer.from(data.original, 'base64').length).toBe(Number(data.headers['content-length']))
  expect(data.headers['x-checksum-sha256']).toBe(data.structure.descriptor.raw_artifact.content_hash.sha256)
})
it.each([
  () => api.reference({ ...data.reference, extra: true }),
  () => api.protein({ ...data.protein, schema_version: 'unknown' }),
  () => api.structure({ ...data.structure, artifact_url: 'https://untrusted.invalid/structure' }),
  () => api.metadata({ state: 'unavailable', value: 0, reason: 'Missing' }),
  () => api.metadata({ state: 'present', value: null, reason: null }),
  () => api.structureAudit({ ...data.structureAudit, parsing: { ...data.structureAudit.parsing, transform_applied: true } }),
  () => api.proteinPage({ ...data.proteinPage, items: Array(101).fill(data.protein.summary) }),
])('rejects incompatible runtime responses', read => expect(read).toThrow())
it('resolves only registered links against an explicit browser API base', () => {
  expect(api.apiUrl('/v1/artifacts/opaque', 'https://api.example.invalid/api')).toBe('https://api.example.invalid/api/v1/artifacts/opaque')
  for (const path of ['//evil.invalid/file', 'https://evil.invalid/file', '/v1/artifacts/../private', '/v1/artifacts/name#fragment', '/v1/artifacts/name%2Fpath']) expect(() => api.apiUrl(path)).toThrow()
  for (const base of ['//evil.invalid', 'https://user:pass@example.invalid', '/api?token=secret', 'javascript:evil']) expect(() => api.apiUrl('/v1/artifacts/opaque', base)).toThrow()
})
it('rejects unusable mutation locations without following them', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => Response.json(data.reference, { status: 201, headers: { Location: 'https://untrusted.invalid/ref' } })))
  await expect(api.request('/v1/references', api.reference, new AbortController().signal, {})).rejects.toThrow()
})

it('verifies original download bytes without decoding or changing checksum semantics', async () => {
  const { webcrypto } = await import('node:crypto')
  vi.stubGlobal('crypto', webcrypto)
  const descriptor = data.structure.descriptor.raw_artifact
  vi.stubGlobal('fetch', vi.fn(async () => new Response(Buffer.from(data.original, 'base64'), { headers: data.headers })))
  const blob = await api.downloadArtifact(descriptor, new AbortController().signal)
  expect(blob.size).toBe(descriptor.byte_size)
  expect(blob.type).toBe(descriptor.media_type)
})
it.each(['checksum', 'size', 'encoding'])('rejects %s download inconsistency', async kind => {
  const { webcrypto } = await import('node:crypto')
  vi.stubGlobal('crypto', webcrypto)
  const bytes = Buffer.from(data.original, 'base64')
  if (kind === 'checksum') bytes[0] ^= 1
  const headers = { ...data.headers, ...(kind === 'encoding' ? { 'content-encoding': 'gzip' } : {}) }
  vi.stubGlobal('fetch', vi.fn(async () => new Response(kind === 'size' ? bytes.subarray(1) : bytes, { headers })))
  await expect(api.downloadArtifact(data.structure.descriptor.raw_artifact, new AbortController().signal)).rejects.toThrow()
})
