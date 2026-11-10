import { useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import * as api from './api'

function useOperation<T>() {
  const [value, setValue] = useState<T>()
  const [error, setError] = useState<Error>()
  const [busy, setBusy] = useState(false)
  const current = useRef<AbortController | null>(null)
  useEffect(() => () => current.current?.abort(), [])
  function cancel() { current.current?.abort(); setBusy(false); setError(undefined) }
  async function run(work: (signal: AbortSignal) => Promise<T>): Promise<T | undefined> {
    current.current?.abort()
    const controller = new AbortController()
    current.current = controller
    setBusy(true); setError(undefined)
    try {
      const result = await work(controller.signal)
      if (!controller.signal.aborted) { setValue(result); return result }
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause : new Error('Request failed.'))
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }
  return { value, error, busy, run, cancel }
}
function Failure({ error }: { error?: Error }) {
  if (!error) return null
  let recovery = 'Check the service and retry the requested operation explicitly.'
  if (error instanceof api.MutationOutcomeError) recovery = 'Publication outcome is unknown. Preserve your retained results and consult the local operator before repeating the mutation.'
  if (error instanceof api.ApiError) {
    if (error.status === 409) recovery = 'The source changed. Inspect the accession or restart discovery, then select again.'
    if (error.status === 400) recovery = 'Check the query. For cursor errors, restart from the first page.'
    if (error.status === 429) recovery = 'Local capacity is full. Wait and retry explicitly.'
    if (error.status === 422) recovery = 'Check canonical accession, organism, model, assembly and operator. Unknown revisions cannot be imported.'
    if (error.error.details.publication_may_complete === true) recovery = 'Publication may still complete. Do not automatically repeat this mutation; consult the local operator with this request ID.'
  }
  return <div role="alert"><p>{error.message}</p><p>{recovery}</p>{error instanceof api.ApiError && <p>Code: {error.error.code}; request: {error.error.request_id}; retryable: {String(error.error.retryable)}.</p>}</div>
}
const metaText = (value: api.Metadata): string => value.state === 'present' ? typeof value.value === 'object' ? JSON.stringify(value.value) : String(value.value) : `${value.state}: ${value.reason}`
function Metadata({ label, value }: { label: string; value: api.Metadata }) { return <p><strong>{label}:</strong> {metaText(value)}</p> }
function OriginalDownload({ descriptor, children }: { descriptor: api.Artifact; children: ReactNode }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error>()
  const active = useRef<AbortController | null>(null)
  const local = useRef<string | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => () => {
    active.current?.abort()
    if (timer.current) clearTimeout(timer.current)
    if (local.current) URL.revokeObjectURL(local.current)
  }, [])
  async function download() {
    active.current?.abort()
    const controller = new AbortController(); active.current = controller
    setBusy(true); setError(undefined)
    try {
      const blob = await api.downloadArtifact(descriptor, controller.signal)
      if (controller.signal.aborted) return
      if (timer.current) clearTimeout(timer.current)
      if (local.current) URL.revokeObjectURL(local.current)
      const url = URL.createObjectURL(blob); local.current = url
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = descriptor.artifact_id + (descriptor.media_type === 'application/gzip' ? '.gz' : descriptor.media_type === 'chemical/x-mmcif' ? '.cif' : '.json')
      document.body.append(anchor); anchor.click(); anchor.remove()
      timer.current = setTimeout(() => { URL.revokeObjectURL(url); if (local.current === url) local.current = null }, 1000)
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause : new Error('Download failed.'))
    } finally { if (!controller.signal.aborted) setBusy(false) }
  }
  return <div><a href={api.apiUrl(`/v1/artifacts/${descriptor.artifact_id}`)} aria-disabled={busy} onClick={event => { event.preventDefault(); if (!busy) void download() }}>{children}</a>{busy && <p role="status">Verifying original artifact download…</p>}<Failure error={error} /></div>
}

function Source({ receipt }: { receipt: api.Protein['source_receipt'] }) {
  return <details><summary>Source, evidence and rights — {receipt.provider}</summary>
    <p>Evidence: {receipt.raw_artifact.evidence}{receipt.raw_artifact.evidence === 'synthetic' ? ' — authored synthetic example; no biological validation.' : ' — provider-response evidence does not establish sequence or annotation validity.'}</p>
    <p>Source: {receipt.query}</p><p>Retrieved: {receipt.retrieved_at}; receipt: {receipt.receipt_id}</p>
    <Metadata label="Entry version" value={receipt.entry_version} /><Metadata label="Sequence version" value={receipt.sequence_version} />
    <Metadata label="Release" value={receipt.release} /><Metadata label="License" value={receipt.raw_artifact.rights.license} />
    <Metadata label="Attribution" value={receipt.raw_artifact.rights.attribution} />
    <p>Citations: {receipt.citation_references.values.join(', ') || receipt.citation_references.reason}</p>
    <p>License references: {receipt.license_references.values.join(', ') || receipt.license_references.reason}</p>
    <p>Redistribution: {receipt.raw_artifact.rights.redistribution}. {receipt.raw_artifact.rights.basis}</p>
    <p>Original raw SHA-256: <code>{receipt.raw_artifact.content_hash.sha256}</code> ({receipt.raw_artifact.byte_size} bytes).</p>
    <OriginalDownload key={receipt.raw_artifact.artifact_id} descriptor={receipt.raw_artifact}>Download original {receipt.provider} metadata</OriginalDownload>
  </details>
}
function PageState({ page, children }: { page: api.ProteinPage | api.StructurePage; children: ReactNode }) {
  return <><p>Availability: <strong>{page.availability}</strong>.</p>{page.warnings.length > 0 && <ul>{page.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}
    {page.items.length === 0 && <p>{page.availability === 'complete' ? 'No matching candidates.' : 'Discovery could not establish an empty result. Retry explicitly.'}</p>}{children}</>
}
function StructureDetails({ record, audit }: { record: api.Structure; audit?: api.StructureAudit }) {
  const d = record.descriptor
  const rows = 'rows' in record.mapping ? record.mapping.rows : []
  const coverage = d.source.mapped_coverage
  return <article aria-label="Retained structure">
    <h3>Retained structure {d.structure_id}</h3><p>Evidence: <strong>{d.evidence}</strong>{d.evidence === 'synthetic' && ' — authored synthetic example'}</p>
    <p>{d.source.entry_id}; entity {d.selection.entity_id}; label chain {d.selection.label_asym_id}; author chain {metaText(d.selection.auth_asym_id)}; model {d.selection.model_id}.</p>
    <Metadata label="Assembly" value={d.selection.assembly_id} /><Metadata label="Operator" value={d.selection.operator_id} /><Metadata label="Source revision" value={d.source.source_revision} />
    <p>Coordinates remain in the original deposited Cartesian frame, in angstroms. Assembly matrices/operators are retained and unapplied. Selecting an assembly does not generate transformed coordinates.</p>
    <p>Missing coordinates do not mean a polymer residue is absent. Ambiguous candidate positions are possibilities, not unique assignments. Construct mismatches, fragments and tags remain explicit.</p>
    {'mapped_positions' in coverage ? <p>Mapped reference coverage: {coverage.mapped_positions} / {coverage.reference_length} full reference positions.</p> : <Metadata label="Mapped reference coverage" value={coverage} />}
    <p>Mapping coverage: unique exact, mismatch and unobserved reference positions / full reference length; excludes ambiguous candidates. Coordinate coverage and aligned-pair identity have separate denominators below.</p>
    <p>Original artifact: {d.raw_artifact.media_type}; {d.raw_artifact.byte_size} bytes; raw SHA-256 <code>{d.raw_artifact.content_hash.sha256}</code>.</p>
    <OriginalDownload key={d.raw_artifact.artifact_id} descriptor={d.raw_artifact}>Download registered original structure{d.raw_artifact.media_type === 'application/gzip' ? ' (.gz)' : ''}</OriginalDownload>
    <p>Gzip downloads retain compressed entity bytes. Decode locally as a separate representation; the displayed checksum and size describe the original download.</p>
    <Source receipt={d.source.source_receipt} />
    {'rows' in record.mapping ? <>
      <p>Reference ID: {record.mapping.identity.reference.record_id}. Mapping: {record.mapping.mapping_id}; {record.mapping.method} ({record.mapping.method_version}).</p>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Residue mapping table"><table><caption>Reference, polymer and coordinate numbering — all five mapping states remain distinct</caption><thead><tr>{['Reference position / residue', 'Polymer label / residue', 'Coordinate author / insertion', 'Coordinates present', 'Status', 'Candidate reference positions', 'Reason'].map(text => <th key={text} scope="col">{text}</th>)}</tr></thead><tbody>{rows.map((r, i) => <tr key={i}><td>{metaText(r.reference_position)} / {metaText(r.reference_residue)}</td><td>{metaText(r.label_seq_id)} / {metaText(r.observed_residue)}</td><td>{metaText(r.auth_seq_id)} / {metaText(r.insertion_code)}</td><td>{r.coordinate_present ? 'Yes' : 'No'}</td><td>{r.status}</td><td>{r.candidate_reference_positions.join(', ') || 'None asserted'}</td><td>{r.reason ?? 'Unique matching residue with coordinates'}</td></tr>)}</tbody></table></div>
    </> : <Metadata label="Mapping" value={record.mapping} />}
    {audit && audit.descriptor.structure_id === d.structure_id && <details><summary>Retained numbering, assemblies, coverage and validation audit</summary>
      <p>Scheme author numbers and scheme PDB numbers are separate from atom-site author numbers. Selected residue inventory retains missing identifiers, alternate atoms and occupancy. Assembly matrices below are not applied.</p>
      <h4>Coverage counts and alignment uncertainty</h4><pre>{JSON.stringify(audit.alignment, null, 2)}</pre>
      <h4>Scheme author/PDB and coordinate inventory</h4><pre>{JSON.stringify(audit.parsing, null, 2)}</pre>
      <h4>Authoritative source checks</h4><p>200 retains original bytes and retrieval receipt. 304 checks validate that receipt without replacing it.</p><pre>{JSON.stringify(audit.checks, null, 2)}</pre>
    </details>}
  </article>
}

export default function Workflow() {
  const [accession, setAccession] = useState('')
  const [gene, setGene] = useState('')
  const [taxon, setTaxon] = useState('')
  const [query, setQuery] = useState('')
  const search = useOperation<api.ProteinPage>()
  const inspect = useOperation<api.Protein>()
  const pinned = useOperation<api.Reference>()
  const pinAudit = useOperation<api.PinAudit>()
  const discover = useOperation<{ referenceId: string; page: api.StructurePage }>()
  const imported = useOperation<api.Structure>()
  const audit = useOperation<api.StructureAudit>()
  const [selected, setSelected] = useState<api.StructureSummary>()
  const [model, setModel] = useState('')
  const [assemblyMode, setAssemblyMode] = useState('')
  const [assembly, setAssembly] = useState('')
  const [operator, setOperator] = useState('')
  const [referenceId, setReferenceId] = useState('')
  const [structureId, setStructureId] = useState('')
  const [validation, setValidation] = useState('')
  const validId = (value: string) => { try { api.id(value); setValidation(''); return true } catch { setValidation('Enter a valid retained ID.'); return false } }
  const inspected = inspect.value
  const reference = pinned.value
  function inspectAccession(value: string) {
    if (!/^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?:-[1-9][0-9]*)?$/.test(value)) { setValidation('Enter a valid UniProt accession with its exact case and isoform suffix.'); return }
    setValidation(''); pinned.cancel()
    void inspect.run(signal => api.request(`/v1/proteins/${value}`, api.protein, signal))
  }
  function searchGene(event: FormEvent) {
    event.preventDefault()
    if (!/^\S{1,128}$/.test(gene) || taxon !== '' && (!/^[1-9][0-9]*$/.test(taxon) || !Number.isSafeInteger(Number(taxon)))) { setValidation('Enter one exact gene token and an optional positive taxon ID.'); return }
    setValidation('')
    const params = new URLSearchParams({ gene, limit: '20', ...(taxon ? { taxon_id: taxon } : {}) })
    const path = `/v1/proteins?${params}`
    void search.run(signal => api.request(path, api.proteinPage, signal)).then(result => { if (result) setQuery(path) })
  }
  function loadDiscovery(cursor?: string) {
    if (!reference) return
    const path = `/v1/references/${reference.reference_id}/structures?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`
    void discover.run(async signal => ({ referenceId: reference.reference_id, page: await api.request(path, api.structurePage, signal) }))
  }
  function loadPinAudit(value: api.Reference) { void pinAudit.run(signal => api.request(`/v1/references/${value.reference_id}/audit`, api.pinAudit, signal)) }
  function loadAudit(value: api.Structure) { void audit.run(signal => api.request(`/v1/structures/${value.descriptor.structure_id}/audit`, api.structureAudit, signal)) }
  function changeReference() { discover.cancel(); imported.cancel(); audit.cancel(); pinAudit.cancel() }
  async function pinReference() {
    if (!inspected) return
    changeReference()
    const result = await pinned.run(signal => api.request('/v1/references', api.reference, signal, { accession: inspected.summary.accession, expected_sequence_sha256: inspected.sequence_hash.sha256 }))
    if (result) { if (result.reference_id !== reference?.reference_id) setSelected(undefined); loadPinAudit(result) }
  }
  function selectStructure(value: api.StructureSummary) { imported.cancel(); setSelected(value); setModel(''); setAssemblyMode(''); setAssembly(''); setOperator('') }
  async function importStructure() {
    if (!reference || !selected) return
    const result = await imported.run(signal => api.request('/v1/structures', api.structure, signal, { reference_id: reference.reference_id, entry_id: selected.entry_id, entity_id: selected.entity_id, label_asym_id: selected.label_asym_id, model_id: model, assembly_id: assemblyMode === 'asymmetric' ? api.notApplicable('Explicit asymmetric unit') : api.present(assembly), operator_id: assemblyMode === 'asymmetric' ? api.notApplicable('No assembly operator selected') : api.present(operator), expected_source_revision: selected.source_revision }))
    if (result) loadAudit(result)
  }
  async function reopenReference(event: FormEvent) {
    event.preventDefault(); if (!validId(referenceId)) return
    changeReference()
    const result = await pinned.run(signal => api.request(`/v1/references/${referenceId}`, api.reference, signal))
    if (result) { if (result.reference_id !== reference?.reference_id) setSelected(undefined); loadPinAudit(result) }
  }
  async function reopenStructure(event: FormEvent) {
    event.preventDefault(); if (!validId(structureId)) return
    const result = await imported.run(signal => api.request(`/v1/structures/${structureId}`, api.structure, signal))
    if (result) loadAudit(result)
  }
  return <>
    <section aria-labelledby="lookup-heading"><h2 id="lookup-heading">Select a public protein</h2>
      <p>Inspect candidates and choose an organism explicitly. Only canonical accessions can be pinned. Provider annotations are not clinical conclusions.</p>
      <form onSubmit={event => { event.preventDefault(); inspectAccession(accession) }}><label>Canonical accession<input value={accession} onChange={e => setAccession(e.target.value)} required maxLength={32} placeholder="UniProt accession" /></label><button disabled={inspect.busy}>Inspect accession</button></form>
      <form onSubmit={searchGene}><label>Exact gene<input value={gene} onChange={e => setGene(e.target.value)} required maxLength={128} /></label><label>Taxon ID (optional)<input value={taxon} onChange={e => setTaxon(e.target.value)} inputMode="numeric" /></label><button disabled={search.busy}>Search gene</button></form>
      {validation && <p role="alert">{validation}</p>}
      {(search.busy || inspect.busy) && <p role="status">Loading protein candidates…</p>}<Failure error={search.error} /><Failure error={inspect.error} />
      {search.value && <div><p>Candidate page for gene {new URLSearchParams(query.split('?')[1]).get('gene')}; taxon {new URLSearchParams(query.split('?')[1]).get('taxon_id') || 'any'}.</p><PageState page={search.value}><ul>{search.value.items.map(item => <li key={item.accession}><strong>{item.accession}</strong>; organism {metaText(item.organism_name)}; taxon {metaText(item.taxon_id)}; reviewed {metaText(item.reviewed)}; {item.sequence_length} residues; {item.canonical ? 'canonical' : `isoform ${metaText(item.isoform)}`} <button disabled={inspect.busy} onClick={() => inspectAccession(item.accession)}>Inspect {item.accession}</button></li>)}</ul></PageState>
        <button disabled={search.busy || !query} onClick={() => void search.run(signal => api.request(query, api.proteinPage, signal))}>Restart protein search</button>
        {search.value.next_cursor.state === 'present' && <button disabled={search.busy} onClick={() => void search.run(signal => api.request(`${query}&cursor=${encodeURIComponent(String(search.value?.next_cursor.value))}`, api.proteinPage, signal))}>Next protein page</button>}
      </div>}
      {inspected && <article aria-label="Inspected protein"><h3>Inspected {inspected.summary.accession}</h3><Metadata label="Organism" value={inspected.summary.organism_name} /><Metadata label="Taxon" value={inspected.summary.taxon_id} /><Metadata label="Reviewed" value={inspected.summary.reviewed} />
        <p>{inspected.summary.sequence_length} residues; sequence SHA-256: <code>{inspected.sequence_hash.sha256}</code>.</p><details><summary>Inspected sequence and extraction</summary><pre>{inspected.sequence}</pre><p>{inspected.normalization}</p></details><Source receipt={inspected.source_receipt} />
        <button disabled={pinned.busy || inspect.busy || !inspected.summary.canonical || inspected.summary.taxon_id.state !== 'present'} onClick={() => void pinReference()}>Pin inspected reference</button>
      </article>}
      {pinned.busy && <p role="status">Loading or pinning reference…</p>}<Failure error={pinned.error} />
    </section>
    <section aria-labelledby="retained-heading"><h2 id="retained-heading">Reopen retained records</h2><p>Retained reference, structure, mapping and original-artifact reads work offline without provider refresh.</p>
      <form onSubmit={event => void reopenReference(event)}><label>Reference ID<input required value={referenceId} onChange={e => setReferenceId(e.target.value)} /></label><button disabled={pinned.busy}>Open reference ID</button></form>
      <form onSubmit={event => void reopenStructure(event)}><label>Structure ID<input required value={structureId} onChange={e => setStructureId(e.target.value)} /></label><button disabled={imported.busy}>Open structure ID</button></form>
    </section>
    {reference && <section aria-labelledby="reference-heading"><h2 id="reference-heading">Pinned reference {reference.reference_id}</h2>
      <p>{reference.protein.summary.accession}; captured {reference.captured_at}; {reference.protein.summary.sequence_length} residues.</p><Metadata label="Pinned organism" value={reference.protein.summary.organism_name} /><Metadata label="Pinned taxon" value={reference.protein.summary.taxon_id} /><p>Sequence SHA-256: <code>{reference.protein.sequence_hash.sha256}</code></p><details><summary>Pinned sequence and extraction</summary><pre>{reference.protein.sequence}</pre><p>{reference.protein.normalization}</p></details><Source receipt={reference.protein.source_receipt} />
      <p>Refresh means reinspection and a new explicit pin/import. Existing records are immutable and never replaced. A fixed identifier does not imply unchanged source content.</p>
      {pinAudit.value?.reference_id === reference.reference_id && <details><summary>Reference authoritative pin check</summary><p>Status {pinAudit.value.response_status}; checked {pinAudit.value.checked_at}; original receipt {pinAudit.value.source_receipt_id}. A later 304 does not replace original 200 metadata.</p></details>}<Failure error={pinAudit.error} />
      <button disabled={discover.busy} onClick={() => loadDiscovery()}>Discover experimental structures / restart</button>
      {discover.busy && <p role="status">Discovering experimental structures…</p>}<Failure error={discover.error} />
      {discover.value?.referenceId === reference.reference_id && <PageState page={discover.value.page}><ul>{discover.value.page.items.map((item, i) => <li key={`${item.entry_id}:${item.label_asym_id}:${i}`}><p>{item.entry_id}; entity {item.entity_id}; label chain {item.label_asym_id}; author chain {metaText(item.auth_asym_id)}; revision {metaText(item.source_revision)}.</p><p>Methods: {item.experimental_methods.join(', ')}. Resolution: {item.resolutions.map(r => `${r.method}: ${metaText(r.value)} ${r.unit}`).join('; ')}.</p><p>Assemblies: {item.assembly_ids.values.join(', ') || item.assembly_ids.reason}; evidence: {item.source_receipt.raw_artifact.evidence}. Discovery does not establish construct identity or coordinate coverage.</p><Source receipt={item.source_receipt} /><button onClick={() => selectStructure(item)}>Select {item.entry_id} chain {item.label_asym_id}</button></li>)}</ul>
        {discover.value.page.next_cursor.state === 'present' && <button disabled={discover.busy} onClick={() => loadDiscovery(String(discover.value?.page.next_cursor.value))}>Next structure page</button>}
      </PageState>}
      {selected && <form onSubmit={event => { event.preventDefault(); void importStructure() }}><h3>Import selected {selected.entry_id} chain {selected.label_asym_id}</h3><p>Revision: {metaText(selected.source_revision)}. Supply explicit deposited model and assembly/operator IDs; unsupported identifiers are rejected. No first model or operator is assumed.</p>
        <label>Model ID<input required value={model} onChange={e => setModel(e.target.value)} /></label>
        <label>Coordinate selection<select required value={assemblyMode} onChange={e => setAssemblyMode(e.target.value)}><option value="">Choose explicitly</option><option value="asymmetric">Deposited asymmetric unit</option><option value="assembly">Recorded assembly copy (operators unapplied)</option></select></label>
        {assemblyMode === 'assembly' && <><label>Assembly ID<input required value={assembly} onChange={e => setAssembly(e.target.value)} /></label><label>Operator ID / product<input required value={operator} onChange={e => setOperator(e.target.value)} /></label></>}
        <button disabled={imported.busy || !model.trim() || !assemblyMode || assemblyMode === 'assembly' && (!assembly.trim() || !operator.trim()) || selected.source_revision.state !== 'present'}>Import inspected structure</button>
      </form>}
    </section>}
    {(imported.busy || imported.error || imported.value) && <section aria-label="Structure results">{imported.busy && <p role="status">Loading or importing structure…</p>}<Failure error={imported.error} />{imported.value && <StructureDetails record={imported.value} audit={audit.value} />}<Failure error={audit.error} />{audit.busy && <p role="status">Loading retained audit…</p>}{imported.value && <button disabled={audit.busy} onClick={() => imported.value && loadAudit(imported.value)}>Reload retained audit</button>}</section>}
  </>
}
