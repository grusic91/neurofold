# Architecture: NF-01, NF-08 M1, NF-09 M1 and NF-02 M1–M3

## Current implementation

The backend is a Python 3.12+ package with a `src` layout and a FastAPI application
factory. `GET /health` returns HTTP 200 with `{"status":"ok"}`. It has no network,
filesystem, database, GPU, or model dependency. HTTP response validation stays in
`api/`; core types use only the Python standard library.

The frontend is React/TypeScript with Vite, strict TypeScript checking, and ESLint.
It requests `/api/health`, validates the response, and shows checking, online, or
unavailable status. Requests are aborted on unmount and time out after five seconds.
Vite proxies `/api/*` to the API during development; production routing is deferred.
Mol* is an intended visualization integration, with no dependency or viewer yet.

## Prediction boundary

`core/prediction.py` defines immutable request/result dataclasses and a structural
`PredictionAdapter` protocol. The initial request carries a single protein
sequence and explicit seed. The result identifies a structure artifact and its
provenance manifest. This is an initial Python interface, not a prediction API,
validated input schema, or implemented inference service. Complexes, ligands,
model-specific parameters, and execution-specific manifest schemas require later
design. NF-08 M1 supplies shared provenance contracts without changing this seam.

Future orchestration will accept an adapter implementing this protocol. A Boltz-2
adapter will translate domain inputs to model inputs, execute in an appropriate
runtime, and translate outputs back into artifact references. Core must never
import concrete adapters. Adapters must not use FastAPI request/response types.
Optional runtime imports must occur only when explicitly selecting an adapter.
The API must remain startable without scientific packages or weights installed.

No model adapter, adapter registry, job scheduler, persistence layer, authentication,
or inference endpoint is introduced in NF-01. Long-running GPU inference should
eventually execute outside HTTP request handling; the execution mechanism remains
an explicit future decision rather than an implicit API dependency.

## Environments and reproducibility

Local development targets macOS Apple Silicon using ordinary CPU-only Python and
Node environments. Docker development uses Linux images compatible with host
architecture. Future NVIDIA CUDA inference needs a separate Linux image,
dependency set, and hardware validation; it must not inflate the API base image.

Both ecosystems commit dependency lockfiles. CI uses locked installs; GitHub
Actions are pinned to commits and uv is version-pinned. The Python build backend
is constrained separately in `pyproject.toml`; its isolated build dependencies are
not part of the runtime lock. Base image tags track updates and are not immutable
digests. This foundation does not yet provide a fully immutable scientific runtime.

Before producing scientific results, extend the shared provenance foundation to record
input hashes/sources, preprocessing, model/adapter versions, weight checksums,
parameters, seeds, code revision, dependency locks, runtime/container identity,
hardware, and CUDA versions. Preserve raw outputs and document nondeterminism.
Define confidence metrics and validation criteria before making biological claims.
The current adapter interface names a provenance artifact; no writer exists yet.

## Shared provenance foundation (NF-08 M1)

`core/canonical.py` defines canonical JSON v1, immutable structured input snapshots,
canonical decimal validation and exact-byte/sequence SHA-256 functions.
`core/provenance.py` defines frozen versioned inputs, source receipts, artifact
descriptors, evidence/absence labels, a provenance skeleton and storage protocols.
`core/_contracts.py` provides strict standard-library serialization. Core imports
remain usable with site-packages disabled.

The [contract guide](provenance-contracts.md) records M1 decisions, identity rules,
compatibility policy and ownership by NF-02 through NF-08. A checked-in JSON Schema
and synthetic compatibility/golden fixtures are tested with a development-only
validator. Capture, persistence, complete successful prediction manifests, runtime
inspection and exports remain future milestones; M1 adds no routes or startup work.

## Validation boundaries

Backend tests exercise HTTP behavior and verify that core imports with
site-packages disabled. They require no GPU, weights, external services, or data.
NF-09 M1 adds fixture inventory/integrity checks, backend socket/DNS guards and
Vitest/React Testing Library status behavior tests with explicit transport fakes.
Playwright tests the built status page in Chromium, including a WebGL-disabled
project, with mocked health responses and failing unmatched request guards.
Frontend lint, strict test/application type checking and production build remain
required alongside behavior tests. No API/worker/biological workflow is added.
Container CI checks both services and Vite proxy connectivity on Linux. Neither
health checks nor these foundation checks establish prediction accuracy or
scientific validity.

The [testing guide](testing/README.md) records tooling compatibility, fixture and
offline policy. Its matrix, scientific review protocol and evidence template
distinguish current foundation acceptance from future synthetic integration and
real scientific release gates. Actual Mol* rendering/fallback and GPU validation
remain future work with their respective features.

## Frontend tooling compatibility

TypeScript is held on 6.0 while `typescript-eslint` supports versions below 6.1;
the current Vite scaffold's TypeScript 7 is outside that supported range.
An npm override selects `minimatch` 11.0.1+ for the lint toolchain to address
[GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249).
This crosses the upstream tools' minimatch 10 range, so validate lint configuration
after updates and remove the override when the tools adopt the patched major.
Node 24 meets the patched package's runtime requirement. No application runtime
dependency relies on this override.

## Biological contract foundation (NF-02 M1)

`core/biological.py` owns frozen reference/structure records, residue identity and
five mapping states, bounded page records and catalog/repository protocols. It
reuses NF-08 receipts, rights, hashes and explicit Metadata absence; core remains
standard-library-only. `api/biological.py` owns Pydantic request/response DTOs and
conversion/response integrity checks. A frozen HTTP JSON Schema documents the
exchange shape without changing the NF-08 schema. M1 itself added no dependencies.

The [biological guide](biological-contracts.md) specifies numbering, identity,
coverage, absence, protocol/error semantics and the contract-only scope. The
[source licensing inventory](source-licensing.md) records independently reviewed
UniProt/RCSB terms and attribution. All fixtures are authored synthetic records.
Tests use a separate ASGI contract harness for planned `/v1` operations; the
production application remains health-only. M2 now adds opt-in lookup, cache and
filesystem references and M3 adds structures as described below. Operational
routes remain NF-02 M4; scientific runtimes remain out of scope.

## UniProt lookup and reference pinning (NF-02 M2)

Opt-in `adapters/biological/` implements UniProt transport/parsing, bounded cache
and cursor policy, and immutable filesystem storage. `application/references.py`
composes the core fresh-catalog/repository/archive protocols to revalidate, compare
sequence identity and pin references. `core/lookup.py` adds standard-library
errors/protocols and a separate versioned pin audit; frozen M1 records/schema stay
unchanged. No adapter is constructed by API startup or health checks. HTTPX 0.28.1
is now explicitly locked in production dependencies; the earlier test-only
httpx2 client is not used by this adapter.

The [M2 guide](uniprot-lookup.md) documents limits, time/concurrency semantics,
cache TTLs, 200/304 provenance, typed conflicts, storage composition and offline
tests. The raw source archive is independent of LRU metadata caches. Application
services import core only; the dependency direction remains API → core ← adapters.
M3 now adds RCSB and molecular structures/mapping. Operational `/v1` routes remain M4.

## Experimental structure imports (NF-02 M3)

[The M3 decision/behavior guide](structure-import.md) pins libraries, numbering,
scoring, chemistry, alternate-location, assembly and resource policies.
`adapters/biological/rcsb.py` implements the existing experimental catalog and
additive source acquisition protocol. It uses Search/Data APIs, independently
validates experimental origin, and retains raw metadata and selected mmCIF.
`mmcif.py` reads Gemmi CIF tables; `alignment.py` uses Biopython optimal-path
consensus. These CPU dependencies are lazy adapter imports; core and API startup
remain independent of them. HTTPX remains the explicit production transport.

`application/structures.py` loads the actual pinned reference, validates explicit
selection/revision, delegates parsing/mapping and revalidates the entry immediately
before publication. Unknown revisions fail closed; changed revisions have a typed
conflict. `core/structures.py` adds standard-library seams and a separately
versioned `neurofold-structure-import/1` bundle/audit, preserving all frozen v1
records and schemas. No inference, API routes or frontend features are added.

`FilesystemStructures` composes the M2 store to publish descriptor/map/audit as
one checksummed atomic bundle after artifacts/receipts/reference dependencies.
Both map and descriptor lookup resolve the same bundle; map IDs are the opaque
structure ID plus `:map`. Original deposited Cartesian coordinates remain intact;
assembly/operator matrices are recorded without applying them. Retained references,
raw bytes, receipts and maps remain readable offline after restart and cache loss.
This is trusted local filesystem storage, not a database or multi-user service.
