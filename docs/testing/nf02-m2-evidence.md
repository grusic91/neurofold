# NF-02 M2 acceptance evidence

Date: 2026-11-10. Scope: opt-in UniProt lookup and immutable reference pinning,
reviewed by the implementing agent from source, documentation and local command
results. No independent scientific/domain approval or live-provider compatibility
is claimed. [Behavior/configuration/limits](../uniprot-lookup.md) are authoritative
for this milestone. M3 structures and M4 route/frontend integration remain open.

## Baseline and identities

The working tree was clean at the requested baseline
`e97de6fec7c8327621aebdfba58cb2e5afb65874`
(`Complete NF-02 M1 biological data contracts`). NF-01, NF-08 M1, NF-09 M1 and
NF-02 M1 were verified through history, source, fixtures and the requested docs.
There was no subsequent uncommitted work to preserve. No commit, push,
publication, deployment or PR was performed.

Package/application version remains 0.1.0. Existing biological/research/canonical
versions, frozen fixtures and HTTP JSON Schema are unchanged. M2 adds separately
versioned `neurofold-reference-pin/1` for authoritative 200/304 check events;
`uniprot-rest/2` identifies the adapter and cache/cursor implementation. This
additive audit preserves original v1 receipt identities, especially on 304.
HTTPX 0.28.1 is now an explicit locked production dependency, alongside locked
httpcore 1.0.9 and certifi 2026.10.23. Existing package resolutions are retained;
httpx2 remains test-only. LICENSE and attribution are preserved.

| Exact file identity | Raw SHA-256 |
| --- | --- |
| `backend/uv.lock` | `e0b82a9959530ef6ad63f9711ba7674655da3efd82ef377db4a9340a5ab45976` |
| `frontend/package-lock.json` | `895d5c748dd378082bbf7860dc545fe14b734cf7d248e17081315b07cfc585de` |
| `docs/testing/fixtures.json` | `b80298f0268ac9a0a6c80604d2de353af50435afc9477acdc5ed31b1bdef2655` |
| `docs/schemas/neurofold-biological-http-1.schema.json` | `acde8893ea3997650d7dffeb198596b177442f81db53b29ac94677ba0f9bd71c` |

Working-tree change identity (22 changed/new files, excluding this record):
`1ad3266400decbef7d6e62dcf6fbeee557dc289f1a29a76d4351fdb590f9e9ef`.
New inline fixture source is 32,576 bytes.

Working-tree change identity excludes this evidence file to avoid circularity.
It is SHA-256 of compact sorted-key UTF-8 JSON containing the path-sorted array
of `{"path": relative_path, "sha256": raw_file_sha256}` for modified and untracked
nonignored files relative to the baseline. This is local evidence, not a commit,
release, CI run or independent attestation; recompute after any further edits.

## Acceptance

| M2 requirement | Evidence / result |
| --- | --- |
| Lookup/search | Canonical accession lookup; exact escaped/encoded gene plus optional positive taxon; multi-hit disambiguation, empty-complete search, isoform IDs preserved in summaries; invalid/obsolete/redirected/substituted identifiers rejected without replacement requests |
| Validated responses | Independent sequence/length/hash, primary identity, gene/taxon/order/page checks; missing metadata explicit; malformed/duplicate-key/truncated/type-inconsistent payloads fail; unknown source annotations retained in raw bytes |
| Pagination | Opaque provider/query/taxon/limit/order-bound capabilities, one-hour anchored expiry, bounded index and 20-page sessions; mismatch/unknown/expiry/eviction restart guidance; next links reconstructed only after exact host/path/query checks; nonprogress/duplicates rejected |
| Transport | Injected transport/monotonic+UTC clock/retry jitter/sleep/IDs; production HTTPX async deadline behind sync seam; connect ≤3s and upstream call budget ≤15s; at most two retries for the specified failures; capped Retry-After; provider-wide process concurrency two; streamed size/header/decompression bounds |
| Cache | Bounded LRU; search 1h/accession 24h/404 5m; conditional ETag/Last-Modified validation; transient failures are errors rather than negatives/empty pages; no stale fallback |
| Fresh pinning | Positive and negative caches cannot satisfy a fresh pin; authoritative 200/304 required; typed SourceChanged exposes expected/actual hashes; same sequence/new source versions pins the actual new receipt; known canonical identity/taxon required |
| 304 provenance | Exact original bytes/200 receipt/retrieval metadata remain unchanged; separate pin audit records authoritative check time, 304 status, actual headers and adapter version; no invented body or new full-response receipt |
| Immutable persistence | Configured ignored private root, ID-hashed paths, bounded complete bundles, checksum/size verification, fsync + atomic no-clobber links, idempotent identical concurrent writes and conflicting-write rejection; interrupted staging leaves no visible partial record |
| Retention/offline | Snapshot dependencies published before reference; a reopened filesystem store reads original references, receipts and raw bytes after cache eviction or provider change/outage; missing/corrupted dependencies fail explicitly |
| Architecture/scope | Core standard-library imports pass on 3.12 and 3.13; application services import core, provider parsing lives in adapters; startup and production OpenAPI remain health-only; no RCSB/structures/alignment/model/inference/database/auth/jobs/frontend lookup |
| Fixtures/docs | One new inventoried inline synthetic source fixture; existing frozen bytes unchanged; limits/rationale, source terms, protocols, roadmap/status, test guide/matrix and this evidence updated |

Fixture inventory has twelve entries. New inline fixture source is under 64 KiB;
provider events derive from the unchanged authored six-residue UniProt example.
No live protein records, sequences, structures, datasets or weights were fetched.
Gzip/size adversarial data is generated in tests rather than committed. Every
backend test runs under the existing socket/DNS guards; HTTPX uses MockTransport.
The adapter's raw-response evidence label does not establish experimental support
for any underlying sequence or annotation; see the guide's explicit distinction.

## Environment and checks

macOS 27.0.1 (26A434), Darwin arm64 CPU-only; Python 3.12.16 default project
environment and Python 3.13.2 in `/private/tmp/neurofold-m2-py313`; uv 0.13.7,
Node 24.5.0, npm 11.5.1; existing pinned Playwright 1.65.0/Chromium. Commands
used `UV_CACHE_DIR=/private/tmp/neurofold-uv-cache` to avoid the unwritable default
cache. The 3.13 environment used `UV_PROJECT_ENVIRONMENT` and `--python` overrides;
the project's `.python-version` and default 3.12 environment were preserved.

| Command / environment | Result |
| --- | --- |
| `uv sync --locked` (backend, 3.12) | pass, 42 locked packages resolved / 40 installed checked |
| `uv run --locked ruff check .` | pass |
| `uv run --locked ruff format --check .` | pass, 30 files |
| `uv run --locked mypy src tests` | pass, 30 files |
| `uv run --locked pytest` (3.12.16) | 351 passed; 73 new M2 cases; 96.96% combined statement/branch coverage, existing ≥90% gate retained |
| Locked sync + Ruff/format/mypy/full pytest (3.13.2) | pass; all 351 tests, 96.96% combined coverage; includes standard-library core import test |
| `npm ci` | pass; package-lock unchanged |
| `npm run lint` / `npm run typecheck` / `npm run build` | pass |
| `npm run test` | 12 passed |
| `npm run test:browser` | 8 passed, Chromium and WebGL-disabled Chromium |
| `docker compose config --quiet` | pass |
| Docker current `colima` endpoint | unavailable; `/Users/gasperus/.colima/default/docker.sock` missing |
| Docker `colima-arm64` endpoint | unavailable; `/Users/gasperus/.colima/arm64/docker.sock` missing |
| Docker `default` endpoint | unavailable; `/var/run/docker.sock` missing |
| Container builds/services/proxy smoke and Linux execution | not run; no available daemon across all configured contexts |
| Full diff, `git diff --check`, local documentation links and frozen fixture identities | reviewed/pass |

Initial dependency/3.13 downloads failed under restricted DNS and succeeded with
network permission using the same locked dependency selection. The first browser
run could not bind loopback (EPERM); the existing offline tests passed with
permission to run the local preview. Several early tool commands were issued
from repository root instead of backend and could not find the check tools; all
required checks above were subsequently run from their prescribed directories.
Final review moved nonprogressing search validation ahead of cache publication
and explicitly included biological/research schema identities in cache/cursor
bindings. The final suites above include those changes.
An early new test had a mistyped expected sequence digest and another omitted the
second authoritative provider event; tests caught both and were corrected against
the unchanged synthetic fixture. No frozen expectation was rewritten.

Official UniProt/API/license documentation and HTTP dependency licenses were
reviewed separately from behavior tests; see the [source inventory](../source-licensing.md)
and [documentation review notes](../uniprot-lookup.md#documentation-review-and-tests).
The UniProt field-configuration document was inspected without retrieving protein
data. Several help pages were JavaScript fallbacks; PMC returned a browser check,
the attempted OpenAPI endpoint returned 400, and the full paper PDF fetch failed.
Indexed official paper excerpts and the accessible dataset/license declarations
were used within those limitations. These are not live compatibility probes.

## Review and remaining gates

Reviewed the full tracked diff and all new application/core/adapter/test files,
receipt/sequence/raw identities, licensing notices, resource limits, cancellation,
source-change and 304 semantics, offline persistence, atomic publication, cache
independence and scope boundaries. Existing CI already enforces the same locked
backend/frontend checks, coverage, Python 3.12/3.13 and Linux container smoke;
no workflow change or weakening was needed. No CI run ID exists without a push.

M2 acceptance: **pass for the documented Python/offline scope**. The previous
full-3.13 gap is now closed locally on macOS; Linux/container execution is still
unverified. Optional live-provider schema/behavior probes remain unrun. M3 still
owns RCSB experimental discovery, structure downloads, mmCIF/parser/alignment
license review, coordinate/assembly limits and residue maps; M4 owns real routes,
HTTP error/status translation and frontend integration. Full scientific manifests,
exports, retention/backup administration, multi-process provider rate coordination,
independent domain review and scientific release approval remain future work.
Local storage requires atomic hard links/fsync; this is not a database or a
multi-user service. No biological accuracy, causality or clinical claim is made.
