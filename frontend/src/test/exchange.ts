// Actual production ASGI routes -> application -> real parser/mapper/archive ->
// JSON -> these frontend readers. The Python child enables socket/DNS guards.
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import * as api from '../api'

export function backendExchange() {
  const directory = resolve(process.cwd(), '../backend')
  const output = execFileSync('uv', ['run', '--locked', 'python', 'tests/contract_exchange.py'], { cwd: directory, encoding: 'utf8', env: { ...process.env, UV_CACHE_DIR: process.env.UV_CACHE_DIR || '/tmp/neurofold-uv-cache' }, timeout: 30000 })
  const raw: unknown = JSON.parse(output)
  if (!raw || typeof raw !== 'object') throw new Error('Missing backend exchange')
  const record = raw as Record<string, unknown>
  return { proteinPage: api.proteinPage(record.proteinPage), protein: api.protein(record.protein), reference: api.reference(record.reference), pinAudit: api.pinAudit(record.pinAudit), structurePage: api.structurePage(record.structurePage), structure: api.structure(record.structure), structureAudit: api.structureAudit(record.structureAudit), original: String(record.original), headers: record.headers as Record<string, string> }
}
