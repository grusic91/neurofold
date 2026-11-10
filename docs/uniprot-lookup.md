# UniProt lookup and immutable pinning — NF-02 M2

M2 implements Python catalog/application/storage behavior. Production still exposes
only `/health`; operational routes, HTTP error translation and frontend lookup
belong to M4. RCSB, structures, coordinates, parsing and alignment belong to M3.
There are no startup network requests or automatic provider probes.

## Selection and use

The opt-in composition is explicit; run synchronous calls outside an asyncio event
loop (a future synchronous FastAPI handler/thread pool is suitable):

```python
from pathlib import Path
from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.adapters.biological.transport import HttpxTransport
from neurofold.adapters.biological.uniprot import UniProtCatalog
from neurofold.application.references import ReferenceService

archive = FilesystemStore(Path("data/uniprot"))
catalog = UniProtCatalog(HttpxTransport(), archive.artifact_store, archive)
references = ReferenceService(catalog, archive, archive)
page = catalog.search(gene="SYNTH", taxon_id=1, limit=20)  # illustrative only
# Inspect/select an accession and its sequence hash before references.pin(...).
```

This snippet performs IO only when called, and its fictional gene/taxon is not a
scientific example. No API startup wiring is added. Storage roots are configured
by application composition, never client requests; use a private ignored
`data/uniprot` directory. `outputs/` and `.cache/` roots are also accepted, but
never apply cache cleanup to the archive. Symlink roots and parent traversal are
rejected. Directory permissions are private on creation; operate under one trusted
local OS account. This is not multi-user storage or a hostile-filesystem sandbox.

`get(accession)` validates canonical syntax and provider primary identity.
Isoforms are rejected explicitly, preserving their suffix in the request/error;
obsolete entries, redirects and secondary-to-primary substitutions require a new
explicit selection. No replacement request is followed. Search returns every
validated hit on the requested page, including isoform IDs if supplied; it never
chooses the first hit. Unknown taxon/reviewed/version/citation metadata has explicit
NF-08 absence states. Unknown annotation fields remain in the raw artifact.
Sequences must already be uppercase supported amino-acid text with the reported
length; no silent case/residue/whitespace normalization occurs.

Search uses `gene_exact:"escaped-token"`, optionally `AND organism_id:taxon`,
and `sort=accession asc`. Quotes/backslashes are escaped inside the query literal;
all parameters are separately URL-encoded. Gene matching is case insensitive,
exact across provider gene names/synonyms/locus/ORF names. The adapter independently
checks returned gene/taxon identities, page size and strictly increasing unique
accessions. An inconsistent response fails instead of quietly dropping hits.

## Bounds and resilience

| Resource | Limit and reason |
| --- | --- |
| Connect timeout | At most 3 seconds, capped by remaining call budget |
| Whole upstream call | 15 seconds including catalog/gate waiting, all attempts, body streaming and retry sleeps; HTTPX inactivity timeouts alone do not enforce this, so each attempt also has an asyncio deadline |
| Retries | At most two after the first attempt, for transport failures, 429 and 502/503/504 only; never validation errors, redirects or 404 |
| Backoff | 0.25 × 2^attempt seconds plus jitter 0–0.25 seconds, bounded at 2 seconds; Retry-After seconds or HTTP-date honored up to 5 seconds; no sleep/attempt beyond remaining budget |
| Concurrency | Two active calls per provider per process, shared across catalog instances; one mutable catalog operation at a time; future multi-process deployment must preserve the provider-wide limit |
| Download | 2 MiB of original HTTP entity bytes; 16 KiB of decoded header names/values; streamed enforcement before accumulation |
| Expansion | 8 MiB decoded JSON; gzip only, one complete member, no trailing members/bytes; reject corruption/truncation and unsupported encodings |
| Sequence | 100,000 residues per entry; sufficient for ordinary single-protein metadata while bounding sequence validation work; an explicit limit error never extracts a fragment |
| Provider collections/text | At most 1,000 elements per parsed collection and 4,096 characters per metadata string; entire unknown annotation content remains bounded by the JSON byte limit |
| Search page/session | Default 20, maximum 100 hits/page; 20 pages (at most 2,000 hits) per session; final truncated page is `partial` with narrowing/restart guidance |
| Cursor index | 128 opaque random 192-bit capabilities, bounded by the cache byte budget; one-hour session expiry, preserved across subsequent pages, anchored to a monotonic clock |
| Metadata cache | 128 entries and 32 MiB accounted retained payload (raw bytes, serialized receipts and headers, plus per-entry allowance); LRU eviction; this is a payload budget, not exact interpreter heap accounting |
| Cache TTL | Search 1 hour; accession 24 hours; negative 404 5 minutes; expired validators may be used for conditional requests |
| Archive | 8 MiB per raw artifact; 16 MiB per serialized bundle/record; small JSON bundles use base64 to atomically bind exact bytes and descriptors |

These are conservative application limits, not UniProt guarantees. There is no
stale fallback, streaming database download or unbounded pagination/mirroring.
Transient failures remain `ProviderError`, never negative/empty results. Only
actual 404s receive negative caching. Parser/coordinate/assembly limits are M3.
Local parsing/serialization/fsync are bounded by sizes but are not interruptible
network operations and are outside the upstream wall-clock deadline.

Cursors are server-side capabilities tied to provider/adapter version, exact
normalized query, taxon, page size, ordering, previous accession and expiry. They
expose neither a trusted client URL nor the provider cursor. Unknown, evicted,
expired and mismatched cursors raise `CursorError` with `restart_hint` and an
instruction to restart without a cursor. Restarting a process loses cursors and
metadata caches, deliberately. Next-page Links must retain HTTPS, the exact
UniProt host/path and query/format/size/order; the URL is rebuilt from validated
parameters. Cross-host/userinfo/fragment/changed-query Links fail. Provider
ordering/release drift cannot establish a transactionally frozen whole search;
inspect the selected accession and revalidate before pinning.

## Receipts, pinning and compatibility

`ReferenceService.pin(accession, expected_sequence_sha256)` always calls
`get_fresh`, bypassing positive and negative TTLs. It requires authoritative 200
or conditional 304 validation and compares the inspected hash. `SourceChanged`
retains expected/actual hashes for later HTTP 409 translation and inspection/retry
guidance. Changed entry/sequence versions with identical sequence bytes are
allowed: the snapshot contains metadata from the newly retrieved receipt.
Unknown taxon prevents pinning. Every successful pin creates a new opaque ID.

A 200 receipt retains exact original entity bytes (compressed if supplied), raw
SHA-256/size, query, UTC retrieval time, original response validators/release,
entry/sequence versions, accession/taxon, sequence identity, source rights and
attribution. The sequence is separately hashed in `sequence-ascii/1`. Transfer
framing/TLS packets are not artifacts. The artifact descriptor's `experimental`
evidence label denotes the observed provider-response artifact; it makes **no
claim that a UniProt sequence or annotation was experimentally measured**.
Reviewed status is separately reported, never equated with experimental or
clinical validity. Synthetic transports explicitly select `synthetic` evidence.
Source annotations and any source-supplied copyright/citation references remain
in raw bytes; extracted notices/citation cross-references are retained too.

A 304 has no new full entity. The original 200 bytes, receipt ID, retrieval time,
versions and validators stay unchanged. Replaceable cache validation time and
validators may advance. An additive `neurofold-reference-pin/1` `PinReceipt`
records the pin ID, original receipt ID, authoritative check time, HTTP 200/304,
actual check-response headers and adapter version. A snapshot's capture time is
the authoritative check time, distinct from the original 200 retrieval time.
The archive publishes this audit before the snapshot. Cache reads do not create
retrieval receipts. Unsolicited/body-bearing 304s fail. Revalidation never invents
bytes or replaces original 200 metadata with purported new full-response data.

Existing `neurofold-biological/1`, `neurofold-research/1`, frozen JSON fixtures and
HTTP schema are unchanged. New core seams live in `core/lookup.py`; the pin audit
is a separately versioned additive record, avoiding a silent v1 wire change.
Core stays standard-library-only. Protocol reuse: catalog implements
`ProteinCatalog` plus `FreshProteinCatalog`; storage implements
`ReferenceRepository`/`SourceArchive`, with `.artifact_store` implementing NF-08
`ArtifactStore` (the two existing protocols both use `publish` for distinct types).

## Persistence and failure semantics

The archive hashes opaque IDs into filenames, validates bytes/sizes/hashes on
reads, and rejects conflicting immutable writes. Each complete bundle is staged,
file-fsynced and atomically hard-linked without replacement; directory fsync
follows publication. Concurrent identical writes are idempotent. Dependencies
(artifact, source receipt, pin audit) are durable before a reference becomes
visible. Interrupted publication can leave an unreferenced dependency, never a
partially visible reference; automatic archive garbage collection is not added.
All staging occurs on the destination filesystem. A filesystem supporting atomic
hard links and fsync is required. Provider outages/changes, process restarts and
cache eviction cannot remove retained references or their source artifacts.
Archive capacity/retention is managed explicitly by the local operator, not LRU.

`KeyError` means missing accession/reference/artifact. Invalid client selections
raise `ValueError`/`UnsupportedIdentifier`; cursor and source-change conflicts
have distinct typed errors. Malformed/oversized provider data raises
`ProviderValidationError`; exhausted retry/status/budget errors raise
`ProviderError`. Storage conflicts/integrity failures raise `ValueError`;
filesystem failures remain IO errors. M4 owns their HTTP envelope/status mapping.

## Documentation review and tests

Official sources reviewed 2026-11-10: [UniProt REST API paper](https://academic.oup.com/nar/advance-article-pdf/doi/10.1093/nar/gkaf394/63079860/gkaf394.pdf)
(entry/search pagination, sorting and release headers),
[API support documentation](https://www.uniprot.org/api-documentation/support-data)
(database CC BY 4.0 statement),
[search field configuration](https://rest.uniprot.org/configure/uniprotkb/search-fields),
[HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/),
[streaming/redirect behavior](https://www.python-httpx.org/compatibility/) and
[HTTPX 0.28.1 license](https://github.com/encode/httpx/blob/0.28.1/LICENSE.md).
HTTPX 0.28.1 (BSD-3-Clause) is an explicit locked production dependency; existing
`httpx2` stays development-only for the prior ASGI harness. Some UniProt help
pages returned a JavaScript fallback and the attempted `/uniprotkb/openapi`
endpoint returned 400; no compatibility claim is inferred from those failures.

Documentation/configuration retrieval is separate from the mandatory offline
suite. No live protein records, sequences or research data were retrieved.
`tests/test_uniprot.py` uses tiny authored entries derived from the unchanged
six-residue synthetic fixture, fake clocks/transports, HTTPX MockTransport and
temporary ignored archives. It covers success/multiple hits/escaping/taxon,
selection failures, cursor/session/URL bounds, TTL/304/pinning/source changes,
negative versus transient errors, retries/deadlines/streaming limits/concurrency,
immutable writes/interruption/corruption and restart/offline archive reads.
See [M2 evidence](testing/nf02-m2-evidence.md) for results and remaining gates.
