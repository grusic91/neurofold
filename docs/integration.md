# NF-02 M4 integration decisions

Decision record, 2026-11-10, before route/UI implementation. The frozen
biological/research v1 DTOs, schema files and compatibility examples stay intact.

The application factory accepts explicit settings and an injectable service
factory. Production lazily composes HTTPX, UniProt/RCSB catalogs, the immutable
filesystem archive, reference/structure services, Gemmi parser and polymer mapper
on a blocking worker. A stateless biological application service owns lookup,
reference-bound discovery and verified artifact reads. All services use the same
archive/dependency graph.
Startup and health perform no provider requests or scientific parsing. Scientific
imports remain lazy. Invalid settings fail configuration explicitly; unavailable
archive IO produces a sanitized service error. Default archive: `data/archive`
relative to the backend working directory; `NEUROFOLD_ARCHIVE_ROOT` selects an
durable private ignored directory (absolute recommended). This directory is retained storage,
never a metadata cache. No automatic cleanup. One trusted operator and one API
process are supported. Provider gates/cursors/caches are process-local; multiple
Uvicorn workers are unsupported.

Four blocking workers, zero waiting admissions, immediate 429/Retry-After: 1
when full. These are separate from each provider's two-slot concurrency and
15-second network-operation budgets. An admitted HTTP operation waits at most
90 seconds, including provider calls, parsing, alignment, archive verification
and response serialization. This is an await budget, not a preemptive parser
limit. The worker slot remains held until its concurrent future really finishes,
even after timeout, task cancellation or client disconnect. Shutdown closes
admission and drains accepted work. A timed-out/disconnected mutation may still
publish; there is no rollback or guaranteed thread cancellation. Clients must
not automatically retry mutations. Completion logs correlate request ID with
the published Location even after the client stops waiting; the operator can
recover that retained ID from Uvicorn logs. Only IDs/status are logged, not
sequences, provider headers, paths or exception text. Read retries and explicit reinspection are
safe; a repeated pin/import creates another immutable record. Work-count and
byte bounds from M2/M3 continue to apply.

The v1 StructureRequest deliberately omits author chain. An application service
entry point resolves it from a fresh authoritative inspection, compares expected
revision/entity/label chain, then invokes the unchanged strict M3 import path.
That path freshly inspects again and checks the complete selection against the
source, downloaded CIF and final revision. No model/assembly/operator is inferred.
Users explicitly supply these identifiers; unsupported choices fail. Separate
`/v1/structures/{id}/audit` and `/v1/references/{id}/audit` endpoints expose
versioned HTTP audit projections without adding fields to frozen v1 responses. Structure
audit exposes parsing inventory, scheme-author/PDB and atom-site numbering,
models, unapplied assemblies/operators, modifications, alternate locations,
scoring/ties, all coverage denominators and original 200 versus later 304 events.
HTTP audit versions are `neurofold-reference-audit-http/1` and
`neurofold-structure-audit-http/1`; their [additive schema](schemas/neurofold-biological-integration-1.schema.json)
is separate from frozen v1. `retained_hash` identifies the complete original
canonical pin/import audit. Only content-type/encoding/length, ETag,
Last-Modified, Date, UniProt release/date and Retry-After headers are exposed.
Unreviewed headers (including Set-Cookie) stay out of the HTTP audit projection;
the immutable original remains in the private archive.

HTTP errors use the epic envelope and a server-generated request ID (also a
response header); client request IDs are not echoed. 400 invalid/duplicate query
or cursor, 404 unknown record/artifact, 409 source change or immutable write
conflict, 413 local size/work profile, 422 unsupported selection/unknown revision,
429 admission, 502 invalid upstream content, 503 unavailable upstream/archive,
504 upstream deadline or operation await timeout. Retained dependency corruption
or loss is 500 ARCHIVE_INTEGRITY, never ordinary 404; unknown/unexpected errors
are 500 INTERNAL_ERROR. Invalid settings prevent serving; late archive-path configuration rejection is
503 CONFIGURATION_ERROR. Framework
validation on v1 uses the envelope (query 400, body/path 422); health keeps its
established behavior. Errors contain allowlisted guidance, not exception strings,
paths, credentials or tracebacks. Discovery still returns 200 with explicit
complete/partial/unavailable pages and candidate-specific safe warnings.

Registered artifact delivery buffers verified bounded bytes before response
commit. Exact raw entity bytes, descriptor media type, Content-Length, raw
X-Checksum-SHA256 and quoted SHA-256 ETag are returned. A gzip entity remains a
compressed downloadable artifact; `X-Artifact-Encoding: gzip` describes it,
**no Content-Encoding** is set. Download filename ends in `.gz` and Cache-Control
is `private, no-transform`. Proxy/middleware must neither decode nor recompress
it. No decoded HTTP representation is supplied. The browser fetches bounded raw
bytes, validates headers, byte size and raw SHA-256 with Web Crypto, then creates
a temporary local Blob download. A failure remains in the workflow with retained
results visible; it does not navigate to an error document. Blob URLs/timers and
fetches are released on completion/unmount. Future decoded artifacts need
separate derived identity and lineage. Deposited coordinates stay Cartesian
angstroms; assembly matrices are retained and unapplied, even when selected.

The frontend uses centralized `/api` routing (optional public VITE_API_BASE),
strict runtime validators, registered relative link checks, explicit inspected
hash/revision, independent recoverable operations and stale-request cancellation.
Failures retain completed snapshots/imports. Cursor failure restarts without a
cursor; conflicts require reinspection; admission/provider failures allow explicit
retry. Mutations never retry automatically. Retained ID reads never refresh
providers. Source evidence, rights, citations, missing metadata, uncertainty and
coordinate limitations are textual. No viewer or numerical comparison is added.

Container archive is a named volume mounted at `/app/data/archive`, with a
precreated private non-root-owned mountpoint. Operators retain/back up that volume;
`down --volumes` deliberately deletes it. No ephemeral default container archive.


## Running and recovery

From `backend/`, use `uv sync --locked`, then
`uv run --locked uvicorn neurofold.api.main:app --host 127.0.0.1 --port 8000`.
Optional local environment: copy `backend/.env.example` to `backend/.env` and
use `uv run --locked --env-file .env uvicorn neurofold.api.main:app`. The app does
not implicitly read dotenv files. Keep the archive outside source control and
review ownership, free space, backups and retention as the local operator.
The process lazily creates the private directory on first biological operation.
An existing root should be accessible only to the trusted operator. Symlink roots
and parent traversal are rejected. Hard-link and fsync support are required.
Never run cleanup/eviction tools over the archive. There is no retention UI,
authentication or distributed coordination. NF-04 M2 uses local SQLite job
metadata and a separately launched supervisor.

From `frontend/`, run `npm ci` and `npm run dev`. Browser API requests default to
`/api/health` and `/api/v1/...`; Vite strips `/api` and forwards to
`API_PROXY_TARGET`. `VITE_API_BASE` optionally changes the public browser origin
and prefix (no credentials/query/fragment); backend Location and registered
artifact paths are resolved through this base. No response-supplied absolute
URLs are followed. Health reports liveness, not provider or archive readiness.

The UI first inspects a canonical accession or explicitly selected gene/taxon
candidate. Pinning sends the inspected sequence hash. Discovery is against the
retained reference and does not consult UniProt. Select a candidate, then enter
an explicit model and asymmetric-unit or assembly/operator choice. There is no
first-model/copy default. Import freshly resolves the omitted author chain;
unsupported model/copy choices fail without convenient substitution. Imported
metadata includes the actual selection and revision. Reopening by ID performs
only archive integrity checks. IDs can be copied from the visible headings.

A complete empty page means no matching candidates on that query/page. Partial
results retain usable candidates plus per-candidate warnings. Unavailable means
the source could not establish a result; it must not be interpreted as absence.
Failures keep completed retained references/structures visible. Discovery pages
are bound to their reference so an old page cannot be imported against a new
reference. Aborted/stale requests cannot replace newer selections. No mutation
is retried automatically. Network or invalid-response failures during mutation
have an explicitly unknown outcome; archive IO/internal failures can also occur
after publication, so their mutation errors disclose that possibility. A failed audit/download does not replace its structure.

Cursor errors require restart from the first page, preserving the gene/taxon and
page size; process restarts/eviction lose cursors. On 409, inspect/select again
and explicitly submit the new hash/revision. Reinspection can use M2/M3 metadata
TTLs, while pin/import always requires fresh authoritative checks. No stale
metadata fallback is added. On 429, wait then retry explicitly. On provider
failure, retained reads remain available. On an await timeout/disconnect during a
mutation, publication may still finish; consult request-ID completion logs before
repeating. A second successful request creates a second immutable record. Orphan
dependencies after a failed publication are retained, never silently cleaned up.

Reference response-artifact evidence describes a provider response, not proof
that the sequence/annotation was experimentally measured. Reviewed status is
separate. Experimental structure origin is independently validated; construct
mismatches, tags/fragments and all five mapping states remain visible. Coverage
is labeled by its numerator/denominator. Missing metadata has its actual absence
reason. UniProt and RCSB receipts retain their source versions, original retrieval
and rights/citations; synthetic compositions explicitly identify NeuroFold
contributors and Apache-2.0. See the [source inventory](source-licensing.md).
No biological accuracy, clinical meaning, variant effect or causality is claimed.

## Container acceptance profile

Normal `docker compose up --build --wait` uses HTTPX/live providers on demand.
The `biological-archive` volume is private and persists across container recreation;
`docker compose down` retains it. **`down --volumes` deletes it** and should only
be used when deliberately discarding that archive. Existing volume ownership
must match the image's neurofold user; do not bypass permission failures with an
ephemeral path. Do not share it across multiple API processes.

`compose.offline.yaml` is an explicit test-only override mounting authored
fixtures and `infra/testing/offline_app.py`. It injects a transport with no
network implementation; it is not a production environment switch. CI first
checks normal service/proxy health, then runs:

```sh
docker compose -f compose.yaml -f compose.offline.yaml up --detach --wait
python3 infra/testing/smoke.py create /tmp/neurofold-smoke-records.json
docker compose -f compose.yaml -f compose.offline.yaml up --detach --force-recreate --no-deps --wait backend
python3 infra/testing/smoke.py read /tmp/neurofold-smoke-records.json
```

This exercises representative biological routes, selections, exact original
bytes, the browser proxy and retained volume after container recreation. Local in-process
tests also exercise that composition but do not establish Linux/container
execution. [M4 evidence](testing/nf02-m4-evidence.md) records historical local
results; [operational evidence](testing/nf02-operational-evidence.md) records later
Linux ARM64 execution, both service builds and verified named-volume retention.


## Actual local browser integration

`npm run test:integration` from `frontend/` starts an explicitly synthetic API on
loopback 8001 (`offline_server:compressed_app`) and the real Vite proxy on loopback
4174. It uses a fresh private temporary archive and a transport without network
IO. Browser HTTP is **unmocked** in this suite: native Chromium performs
inspection/pinning/discovery/import/audit/reopening, downloads original gzip
bytes, verifies SHA-256/length/type/absence of Content-Encoding and independently
decodes them to the unchanged authored CIF. Only the exact local application
HTTP/HMR origin is allowed; unmatched external traffic fails. This complements
the socket-guarded ASGI exchange and mocked UI suites. It demonstrates local
proxy/application integration. It has passed on macOS and Linux ARM64, as recorded
in the operational evidence; the separate container smoke verifies volume
retention. It does not establish provider compatibility or scientific validity.
CI runs it with the locked environments.


Configuration bounds: `NEUROFOLD_WORKERS` defaults to 4 (1–8 supported),
`NEUROFOLD_OPERATION_SECONDS` defaults to 90 (positive, at most 120), and the
archive root defaults to `data/archive`. Waiting admissions are fixed at zero;
request bodies are capped at 16 KiB before JSON parsing/copying. Browser
biological requests have a 95-second deadline; when the server budget is raised
above the default the browser can stop waiting first. This does not cancel the
worker or guarantee rollback. `/v1` unknown paths use 404 NOT_FOUND; unsupported
methods use 405 HTTP_ERROR with Allow. Malformed/duplicate/control-character
queries use 400 INVALID_QUERY; invalid, duplicate-key or excessively nested JSON and body/path
validation use 422 INVALID_INPUT. The health contract retains its established
framework errors. Response redirects are rejected by the browser API client.


The test-only `infra/testing/offline_server.py` entry point permits listening and
accepted local HTTP sockets, while denying outbound connect/connect_ex/sendto
and DNS resolution. The container override uses its plain app; the local browser
suite uses its compressed app. Ordinary pytest socket/DNS guards remain unchanged.
This server guard prevents an accidental transport regression from contacting
live providers during real local HTTP acceptance.


Authoritative provider 404s retain a typed absence cause (including fresh RCSB
entry/instance requests); they are distinct from missing required fields in a
malformed 200 body, which remain 502. Candidate-specific 404/failures produce a
partial discovery page preserving usable candidates, rather than invalidating
the page or pretending it is complete empty.


## NF-03 M3 offline variant HTTP

`POST /v1/variants` accepts exactly `{reference_id, expected_reference_sha256,
notation}` with strict strings and no normalization. It returns the complete
`neurofold-variant/1` definition: pinned metadata/hashes, structured/versioned
substitution, canonical notation, exact sequence/hash/length, ordered 1-based
differences and hypothesis interpretation. The HTTP projection has no wrapper
or additional version. First publication returns 201; a verified identical
repeat returns 200. Both include the same `Location: /v1/variants/{variant_id}`.
GET of that resource verifies the entire retained graph every time, entirely
offline. HTTP schema errors precede unchanged service/domain validation.

The [variant HTTP contract](variants.md#m3-http-contract) specifies complete
schemas, exact synthetic examples and error/status mappings. Unknown variants
return 404 NOT_FOUND; known variants with damaged/missing dependencies return
500 ARCHIVE_INTEGRITY. Creation distinguishes absent references (404), expected
hash mismatch (409), domain validation (422), immutable conflict (409) and
publication I/O uncertainty (503 ARCHIVE_PUBLICATION_FAILED). No update endpoint
exists; unsupported methods use 405 HTTP_ERROR with Allow.

Variant operations reuse lazy services, the shared archive and the same bounded
executor as biological routes. Reference reads/verification and substantial
DTO conversion/serialization run in admitted workers. No provider calls are made,
even with unrelated catalogs configured. Health remains responsive while work
blocks. Timeout/cancellation never frees capacity before actual completion;
shutdown drains workers and completion/failure logging retains request correlation.

Publication failures can happen after the atomic link; response timeout or caller
cancellation can leave publication running. Mutation errors do not authorize
automatic retries or assert rollback/absence. Publication I/O responses include
an already derived recovery ID/URL as transient application metadata; timeout
responses invent none. Verify a known ID or deliberately repeat the identical
request. Unlike reference/import re-submission above, identical variant
re-submission converges on the same immutable content identity. Never delete,
overwrite or repair retained content to retry.

Frontend variant interaction is not implemented. Structured fields support later
NF-07 interaction without parsing notation in the browser. Existing biological
contracts, source provenance, frozen schemas/fixtures and archive bytes remain
unchanged. Prediction, comparison, export and independent scientific acceptance
remain separate gates; a sequence hypothesis is no disease-effect claim.
See [executed M3 evidence](testing/nf03-m3-evidence.md).


## Historical NF-04 M1 contract boundary

[Prediction contracts](prediction-contracts.md) are pure core records and injected
validators. The synchronous worker seam now accepts an authoritative resolved
`PredictionSpec` and returns registered sample/artifact/manifest identities.
No prediction endpoint, submission service, job repository implementation,
background execution or frontend interaction is composed. Startup, health,
existing API paths and the immutable biological/variant archive remain unchanged.
Future M2 must perform final expected-version/state/lease/fence checks atomically
with successful publication. M1 byte validation cannot supply that transaction
or verify actual model execution. NF-03 M3's stopped-daemon build/smoke gap remains
open until the next execution-infrastructure checkpoint.

## NF-04 M2 prediction integration

The [orchestration guide](prediction-orchestration.md) supersedes the historical
M1-only boundary above. Eight prediction resource paths now expose static
capabilities, idempotent submit/get/cancel, result/manifest and graph-bound raw
artifacts and a checksummed operational failure extension. Job HTTP bodies use the explicit versioned status envelope around the
unchanged M1 job. Required nulls and Idempotency-Key, status/error precedence,
Location/Retry-After and uncertain mutation outcomes are specified there.

Prediction composition is independently lazy: a damaged prediction database does
not block biological reads, startup, health or static capabilities. SQLite and
archive verification/serialization use the existing admitted blocking workers.
No provider calls occur on prediction polls or retained reads. Production
`NEUROFOLD_CODE_IDENTITY` is strict M1 CodeIdentity JSON; absent identity blocks
submission rather than inventing a clean revision. Dirty code requires a retained
raw patch reference. No shipped profile is executable in M2, even with identity
configured. The test-only composition is mounted explicitly and cannot be enabled
through production request parameters.

Storage is under `<archive>/predictions/{jobs.sqlite3,registered/,staging/}`.
The DB’s durable identity marker detects a missing retained database instead of
silently creating new empty history. Retain DB/WAL, identity marker and archive
together. A successful job verifies its complete retained graph on every read,
including duplicate submissions. Missing/corrupt required dependencies are 500
integrity failures. Recovery never overwrites retained data or reruns inference.

See the [second-pass checkpoint](testing/nf04-m2-hardening-pass2-evidence.md) and
[historical first pass](testing/nf04-m2-hardening-evidence.md) for the
historical review disposition, failure extension compatibility, configuration/
contention errors, variant container acceptance and remaining deployment gates.
The broad first-pass configuration claim is limited: symlinked prediction
sub-folders are not consistently translated to 503 CONFIGURATION_ERROR. This
remains a tracked configuration/error-translation gap; no uniform response is
promised for that topology. Current cleanup evidence is in the
[focused cleanup closure](testing/nf04-m2-cleanup-closure-evidence.md).
The historical NF-03/M1 stopped-daemon gap is tracked there, not silently waived.
