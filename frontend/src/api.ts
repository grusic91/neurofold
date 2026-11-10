// Strict wire readers for consumed NF-02 endpoints. Scientific identities come
// from the backend; this module never reserializes records to invent hashes.
type Reader<T> = (value: unknown) => T
export type Json = string | number | boolean | null | Json[] | { [key: string]: Json }
const fail = (): never => { throw new Error('Unexpected API response contract.') }
const string: Reader<string> = v => typeof v === 'string' && v.length > 0 ? v : fail()
const nullableString: Reader<string | null> = v => v === null ? null : string(v)
const boolean: Reader<boolean> = v => typeof v === 'boolean' ? v : fail()
const integer: Reader<number> = v => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 ? v : fail()
const positive: Reader<number> = v => integer(v) > 0 ? integer(v) : fail()
const literal = <const T extends string>(...values: T[]): Reader<T> => v => values.includes(v as T) ? v as T : fail()
const array = <T>(read: Reader<T>, max = 100000): Reader<T[]> => v => Array.isArray(v) && v.length <= max ? v.map(read) : fail()
const object = <T extends Record<string, Reader<unknown>>>(shape: T): Reader<{ [K in keyof T]: ReturnType<T[K]> }> => v => {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return fail()
  const record = v as Record<string, unknown>
  if (Object.keys(record).length !== Object.keys(shape).length || Object.keys(record).some(k => !(k in shape))) return fail()
  return Object.fromEntries(Object.entries(shape).map(([k, read]) => [k, read(record[k])])) as { [K in keyof T]: ReturnType<T[K]> }
}
const json: Reader<Json> = v => {
  if (v === null || typeof v === 'string' || typeof v === 'boolean') return v
  if (typeof v === 'number' && Number.isSafeInteger(v)) return v
  if (Array.isArray(v)) return v.map(json)
  if (typeof v === 'object' && v) return Object.fromEntries(Object.entries(v).map(([k, value]) => [k, json(value)]))
  return fail()
}
const jsonObject: Reader<Record<string, Json>> = v => v && typeof v === 'object' && !Array.isArray(v) ? json(v) as Record<string, Json> : fail()
const digest: Reader<string> = v => /^[a-f0-9]{64}$/.test(string(v)) ? string(v) : fail()
export const id: Reader<string> = v => /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(string(v)) ? string(v) : fail()
const metaShape = object({ state: literal('present', 'unavailable', 'not_applicable'), value: json, reason: nullableString })
export const metadata: Reader<ReturnType<typeof metaShape>> = v => {
  const result = metaShape(v)
  if (result.state === 'present' ? result.value === null || result.reason !== null : result.value !== null || result.reason === null) return fail()
  return result
}
export type Metadata = ReturnType<typeof metadata>
export const present = (value: string): Metadata => ({ state: 'present', value, reason: null })
export const notApplicable = (reason: string): Metadata => ({ state: 'not_applicable', value: null, reason })
const collectionShape = object({ state: literal('present', 'unavailable', 'not_applicable'), values: array(string), reason: nullableString })
const collection: Reader<ReturnType<typeof collectionShape>> = v => {
  const result = collectionShape(v)
  if (result.state === 'present' ? result.values.length === 0 || result.reason !== null : result.values.length !== 0 || result.reason === null) return fail()
  return result
}
const hash = object({ algorithm: literal('sha256'), encoding: literal('raw-bytes/1', 'sequence-ascii/1', 'neurofold-json/1'), sha256: digest })
const hashFor = (encoding: ReturnType<typeof hash>['encoding']): Reader<ReturnType<typeof hash>> => v => { const result = hash(v); return result.encoding === encoding ? result : fail() }
const contentReference = object({ record_id: id, content_hash: hash })
const rights = object({ license: metadata, attribution: metadata, redistribution: literal('allowed', 'prohibited', 'unknown'), basis: string })
const artifact = object({ schema_version: literal('neurofold-research/1'), record_kind: literal('artifact'), artifact_id: id, content_hash: hashFor('raw-bytes/1'), byte_size: integer, media_type: string, evidence: literal('experimental', 'predicted', 'synthetic'), rights, parents: array(hash), transformation: metadata })
const receipt = object({ schema_version: literal('neurofold-research/1'), record_kind: literal('source_receipt'), receipt_id: id, provider: string, query: string, retrieved_at: string, raw_artifact: artifact, accession: metadata, isoform: metadata, taxon_id: metadata, entry_version: metadata, sequence_version: metadata, release: metadata, release_date: metadata, etag: metadata, last_modified: metadata, license_references: collection, citation_references: collection })
const summary = object({ schema_version: literal('neurofold-biological/1'), accession: string, canonical: boolean, isoform: metadata, gene_names: collection, organism_name: metadata, taxon_id: metadata, reviewed: metadata, sequence_length: positive, source_receipt_id: id })
export const protein = object({ schema_version: literal('neurofold-biological/1'), summary, sequence: string, sequence_hash: hashFor('sequence-ascii/1'), source_receipt: receipt, normalization: string })
export const reference = object({ schema_version: literal('neurofold-biological/1'), reference_id: id, protein, captured_at: string })
const selection = object({ entity_id: string, label_asym_id: string, auth_asym_id: metadata, model_id: string, assembly_id: metadata, operator_id: metadata })
const coverage = object({ mapped_positions: integer, reference_length: positive, definition: literal('unique-reference-positions/1') })
const coverageOrMetadata: Reader<ReturnType<typeof coverage> | Metadata> = v => v && typeof v === 'object' && 'state' in v ? metadata(v) : coverage(v)
const structureSummary = object({ schema_version: literal('neurofold-biological/1'), entry_id: string, entity_id: string, label_asym_id: string, auth_asym_id: metadata, experimental_methods: array(string), resolutions: array(object({ value: metadata, method: string, unit: literal('angstrom') })), source_revision: metadata, revision_date: metadata, assembly_ids: collection, polymer_sequence: metadata, mapped_coverage: coverageOrMetadata, citations: collection, source_receipt: receipt, origin: literal('experimental') })
const pageShape = { schema_version: literal('neurofold-biological/1'), next_cursor: metadata, availability: literal('complete', 'partial', 'unavailable'), warnings: array(string), source_receipts: array(receipt) }
const page = <T>(item: Reader<T>) => {
  const read = object({ ...pageShape, items: array(item, 100) })
  return (v: unknown) => {
    const result = read(v)
    if (result.availability === 'unavailable' && result.items.length > 0 || result.availability !== 'complete' && result.warnings.length === 0 || result.next_cursor.state === 'present' && typeof result.next_cursor.value !== 'string') return fail()
    return result
  }
}
export const proteinPage = page(summary)
export const structurePage = page(structureSummary)
const identity = object({ reference: contentReference, structure: contentReference, selection })
const rowShape = object({ identity, reference_position: metadata, reference_residue: metadata, label_seq_id: metadata, auth_seq_id: metadata, insertion_code: metadata, observed_residue: metadata, coordinate_present: boolean, status: literal('exact', 'mismatch', 'unobserved', 'unmapped', 'ambiguous'), reason: nullableString, candidate_reference_positions: array(positive) })
const row: Reader<ReturnType<typeof rowShape>> = v => {
  const result = rowShape(v)
  if (result.status === 'ambiguous' && (result.reference_position.state === 'present' || result.reference_residue.state === 'present')) return fail()
  if (result.status === 'exact' ? !result.coordinate_present || result.reason !== null : result.reason === null) return fail()
  if (result.status === 'unobserved' && result.coordinate_present) return fail()
  if (result.status !== 'ambiguous' && result.candidate_reference_positions.length > 0) return fail()
  return result
}

const mapping = object({ schema_version: literal('neurofold-biological/1'), mapping_id: id, identity, reference_length: positive, method: string, method_version: string, rows: array(row) })
const referenceOrMetadata: Reader<ReturnType<typeof contentReference> | Metadata> = v => v && typeof v === 'object' && 'state' in v ? metadata(v) : contentReference(v)
const descriptor = object({ schema_version: literal('neurofold-biological/1'), structure_id: id, raw_artifact: artifact, evidence: literal('experimental', 'synthetic'), selection, source: structureSummary, mapping: referenceOrMetadata, format: literal('mmcif') })
const mappingOrMetadata: Reader<ReturnType<typeof mapping> | Metadata> = v => v && typeof v === 'object' && 'state' in v ? metadata(v) : mapping(v)
const structureShape = object({ descriptor, mapping: mappingOrMetadata, artifact_url: string })
export const structure: Reader<ReturnType<typeof structureShape>> = v => {
  const result = structureShape(v)
  if (result.artifact_url !== `/v1/artifacts/${result.descriptor.raw_artifact.artifact_id}`) return fail()
  if ('mapping_id' in result.mapping && (result.mapping.identity.structure.record_id !== result.descriptor.structure_id || result.mapping.identity.structure.content_hash.sha256 !== result.descriptor.raw_artifact.content_hash.sha256)) return fail()
  return result
}
const check = object({ source_receipt_id: id, checked_at: string, response_status: (v: unknown): 200 | 304 => v === 200 || v === 304 ? v : fail(), response_headers: jsonObject, adapter_version: string })
export const pinAudit = object({ ...{schema_version: literal('neurofold-reference-audit-http/1'), retained_hash: hash, reference_id: id}, source_receipt_id: id, checked_at: string, response_status: (v: unknown): 200 | 304 => v === 200 || v === 304 ? v : fail(), response_headers: jsonObject, adapter_version: string })
const auditShape = object({ schema_version: literal('neurofold-structure-audit-http/1'), retained_hash: hash, descriptor, mapping, reference: contentReference, checks: array(check), parsing: jsonObject, alignment: jsonObject })
export const structureAudit: Reader<ReturnType<typeof auditShape>> = v => {
  const result = auditShape(v)
  if (result.parsing.coordinate_frame !== 'original-deposited-cartesian' || result.parsing.coordinate_unit !== 'angstrom' || result.parsing.transform_applied !== false) return fail()
  return result
}
export type Protein = ReturnType<typeof protein>
export type Reference = ReturnType<typeof reference>
export type Structure = ReturnType<typeof structure>
export type StructureSummary = ReturnType<typeof structureSummary>
export type StructureAudit = ReturnType<typeof structureAudit>
export type ProteinPage = ReturnType<typeof proteinPage>
export type StructurePage = ReturnType<typeof structurePage>
export type PinAudit = ReturnType<typeof pinAudit>
const errorEnvelope = object({ error: object({ code: string, message: string, retryable: boolean, details: jsonObject, request_id: id }) })
export class ApiError extends Error {
  readonly status: number
  readonly error: ReturnType<typeof errorEnvelope>['error']
  constructor(status: number, error: ReturnType<typeof errorEnvelope>['error']) { super(error.message); this.status = status; this.error = error }
}
// Relative /v1 registry routes only. Neither server links nor public config can
// supply credentials, query strings, fragments or an arbitrary artifact URL.
export function apiUrl(path: string, base = import.meta.env.VITE_API_BASE || '/api'): string {
  if (path !== '/health' && !/^\/v1\/(?:proteins|references|structures|artifacts)(?:\/[A-Za-z0-9][A-Za-z0-9._:-]{0,127})*(?:\?(?:gene|taxon_id|limit|cursor)=[^#]*)?$/.test(path)) throw new Error('Untrusted API link.')
  if (!(base.startsWith('/') && !base.startsWith('//') || /^https?:\/\//.test(base))) throw new Error('Invalid API base.')
  const parsed = new URL(base, 'http://local.invalid')
  if (parsed.username || parsed.password || parsed.search || parsed.hash) throw new Error('Invalid API base.')
  return base.replace(/\/$/, '') + path
}
export class MutationOutcomeError extends Error {}
export async function request<T>(path: string, read: Reader<T>, signal: AbortSignal, body?: unknown): Promise<T> {
  try {
    const response = await fetch(apiUrl(path), { redirect: 'error', method: body === undefined ? 'GET' : 'POST', signal: AbortSignal.any([signal, AbortSignal.timeout(95000)]), ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) })
    const payload: unknown = await response.json()
    if (!response.ok) throw new ApiError(response.status, errorEnvelope(payload).error)
    const result = read(payload)
    if (body !== undefined) {
      const location = response.headers.get('Location')
      if (response.status !== 201 || !location) return fail()
      const record = result as { reference_id?: string; descriptor?: { structure_id: string } }
      const expected = record.reference_id ? `/v1/references/${record.reference_id}` : `/v1/structures/${record.descriptor?.structure_id}`
      if (location !== expected) return fail()
      apiUrl(location)
    }
    return result
  } catch (error) {
    if (body !== undefined && !(error instanceof ApiError)) throw new MutationOutcomeError('The mutation response could not establish its publication outcome. No automatic retry was made.')
    throw error
  }
}

export type Artifact = ReturnType<typeof artifact>
export async function downloadArtifact(descriptor: Artifact, signal: AbortSignal): Promise<Blob> {
  if (descriptor.byte_size > 8 * 1024 * 1024) throw new Error('Artifact exceeds the supported download size.')
  const response = await fetch(apiUrl(`/v1/artifacts/${descriptor.artifact_id}`), { redirect: 'error', method: 'GET', signal: AbortSignal.any([signal, AbortSignal.timeout(95000)]) })
  if (!response.ok) throw new ApiError(response.status, errorEnvelope(await response.json()).error)
  if (response.headers.has('Content-Encoding') || response.headers.get('Content-Type') !== descriptor.media_type || response.headers.get('Content-Length') !== String(descriptor.byte_size) || response.headers.get('X-Checksum-SHA256') !== descriptor.content_hash.sha256 || response.headers.get('ETag') !== `"${descriptor.content_hash.sha256}"`) throw new Error('Original artifact headers do not match its retained identity.')
  const reader = response.body?.getReader()
  if (!reader) throw new Error('Original artifact body is missing.')
  const raw = new Uint8Array(new ArrayBuffer(descriptor.byte_size))
  let size = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (size + value.length > raw.length) throw new Error('Original artifact exceeds its registered size.')
      raw.set(value, size); size += value.length
    }
  } finally { await reader.cancel(); reader.releaseLock() }
  const sha256 = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', raw.buffer)), byte => byte.toString(16).padStart(2, '0')).join('')
  if (size !== raw.length || sha256 !== descriptor.content_hash.sha256) throw new Error('Original artifact failed size/checksum verification.')
  return new Blob([raw.buffer], { type: descriptor.media_type })
}
