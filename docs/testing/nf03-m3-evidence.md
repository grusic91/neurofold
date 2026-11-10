# NF-03 M3 — HTTP integration acceptance evidence

Date: 2026-11-10. Implementing-agent software validation against initially clean
`be1486d786dc9ce93e9bc4b89928b275f6b14124`. Existing M1/M2 implementation was
inspected and preserved. **M3 complete for offline HTTP integration.** All changes
remain uncommitted. No push, publication, PR, model runtime or dependency change.
This is software acceptance, not independent scientific approval.

## Interfaces and compatibility

[The contract guide](../variants.md#m3-http-contract) specifies schemas, exact
synthetic request/full response bodies, validation precedence and complete
status/error mapping. `api/variants.py` adds strict required DTO projections;
`routes.py` adds production POST `/v1/variants` and GET
`/v1/variants/{variant_id}`. POST uses exactly the three required strings
`reference_id`, `expected_reference_sha256`, `notation`. HTTP representation
validation precedes the unchanged service's deterministic domain validation.
No normalization, algorithm/hashing duplication or unchecked success dictionary.

POST returns 201 only for `created=True`, otherwise 200 after duplicate
verification. Both return the same usable GET Location and complete versioned
`VariantDefinition`, including metadata/hash linkage, structured substitution
and notation version, canonical notation, exact mutated sequence/hash/length,
1-based differences and `hypothesis`. GET verifies the full actual retained graph
on every call. Identical synthetic MACAG/A4V requests return MACVG with ID
`variant-4f0a7366f1a3a152596ba4337b0f2050b7b06e70640cc77ef54aafa84143f165`.
OpenAPI documents strict schemas, both statuses/Location, GET, error envelopes,
request IDs, representative errors and exact authored examples. A small OpenAPI
postprocessing step preserves required explicit nulls that FastAPI otherwise
removes from example dictionaries; examples are validated against schemas/codecs.

The persisted `neurofold-variant/1` four-field identity, archive envelopes and
M1/M2 behavior remain unchanged. No core/adapters, frozen NF-02/NF-08 schema or
standalone fixture bytes, dependency manifests/locks, LICENSE or attribution were
modified. Existing production-route path-count assertions changed from 11 to 13;
the eight-path frozen contract harness/schema stayed unchanged. Fixture inventory
hashes were refreshed for edited source fixtures and added for the new HTTP tests
and authored OpenAPI examples.

## Errors, uncertainty and execution

Errors preserve the existing envelope and matching X-Request-ID. Reached typed
VariantError codes/details map to 422, except missing creation reference (404
REFERENCE_NOT_FOUND) and expected/actual hash mismatch (409
REFERENCE_HASH_MISMATCH). Unknown variants are 404 NOT_FOUND; damaged retained
records/dependencies are 500 ARCHIVE_INTEGRITY. Valid immutable conflicts return
409 ARCHIVE_CONFLICT. Unsupported methods retain 405 HTTP_ERROR/Allow. Existing
non-variant error behavior is preserved.

Publication I/O is 503 ARCHIVE_PUBLICATION_FAILED, nonretryable, with
`publication_may_complete=true`, `automatic_retry=false` and deliberate recovery
instructions. `VariantPublicationFailure`, an ArchivePublicationError subclass,
adds only an already derived variant ID as transient application context. Its
response recovery URL does not certify existence or verification. Before-link
failures leave no final variant in tests; after-link failure can leave a complete
record verified by GET and then a duplicate 200 POST. No overwrite, repair,
rollback or guaranteed absence is claimed.

Mutating timeouts return 504 OPERATION_TIMEOUT, nonretryable and uncertain, with
no invented recovery ID/URL. Cancelled callers may receive no response. A caller
can verify a known ID or deliberately repeat the identical request under the
content-addressed idempotency contract; automatic retries are discouraged.
Raw exception text, paths and sequences are absent from error responses/logs.

Composition is lazy and shares the configured archive/reference repository.
Variants never call providers, including with unrelated catalogs configured.
The same zero-queue BlockingExecutor admits repository I/O, verification, DTO
conversion and serialization. Health stays responsive; admission returns 429
with Retry-After. Timeout/cancellation keeps capacity until actual completion;
late success/failure is observed/logged with request correlation, capacity
recovers and shutdown drains actual workers. No second pool or queue was added.

## Executed behavioral evidence

`tests/test_variant_api.py` adds **117 tests**, under unchanged socket/DNS guards:

- Real temporary filesystem archive creation, exact 201 response/Location,
  sequential 200 duplicate, GET by ID/following Location, fresh production
  composition reopening with provider transport forbidden, unchanged original
  references/receipts/provenance/artifacts, structured differences/hypothesis.
- Missing/extra fields, bool/number/string/container coercions, invalid IDs/hashes,
  malformed/duplicate-key/non-UTF-8/deep JSON, size/query/path boundaries, lazy
  health and unsupported methods; all required response fields, outgoing strict
  types/versions/invariants and invalid outgoing production DTO handling.
- Reached notation and biological failures with exact structured details and
  syntax/alphabet/bounds/mismatch/no-op precedence; absent reference, expected
  hash mismatch and unknown variant without publication.
- Unknown versus corrupt variants; missing/corrupt reference, pin audit, source
  receipt and artifact dependencies; corrupt duplicates stay damaged; valid
  simulated identity collision returns immutable conflict without overwriting.
- Injected stage/link/file-fsync/directory-fsync failures and post-link verified
  recovery. Safe envelope fields and matching request-ID headers.
- Four genuinely concurrent HTTP contenders synchronized at the atomic link:
  exactly one 201 and three 200 responses, identical complete definition/Location,
  one retained bundle. This is separate from admission rejection tests.
- Event-controlled blocking publication, responsive health, 429 admission,
  timeout/cancellation without early capacity release, eventual verified GET and
  duplicate POST, safe completion logging; blocked GET serialization within an
  admitted worker; late failures observed/logged and shutdown draining.
- Generated OpenAPI success/error schemas, both POST statuses, headers, strict
  required schemas, complete examples including explicit nulls, and codec/schema
  validation of exact synthetic examples.

Existing M1/M2 domain/storage/process-race/interruption/core-import-isolation,
biological/API/archive, fixture inventory and offline container-profile tests all
pass in both full checkpoints below. No live upstream, research dataset, weights,
GPU, socket/DNS opt-out or new testing dependency was used.

## Executed checkpoints

macOS Apple Silicon CPU-only; uv **0.13.7**, default CPython **3.12.16**, separate
Homebrew CPython **3.13.2**, Node **v24.5.0**, npm **11.5.1**. CI already enforces
locked installs and the same backend checks on 3.12/3.13; this evidence records
actual local execution, not inferred CI coverage.

From `backend/`, `UV_CACHE_DIR=/tmp/neurofold-uv-cache` was set for every uv
command because the default user cache is outside the workspace write sandbox:

```sh
uv sync --locked
uv run --locked python --version
uv run --locked ruff check . ../infra/testing
uv run --locked ruff format --check . ../infra/testing
uv run --locked mypy src tests scripts ../infra/testing
uv run --locked pytest
```

Python **3.12.16**: locked sync, lint, format and strict mypy **passed** (60 checked
source files). Full pytest **1,341 passed, 0 failed**, **97.10%** combined
statement/branch coverage, 38.40 seconds; 90% gate passed. Variant domain, variant
adapter, variant service, variant DTOs and routes each report **100%** coverage.

For **every** alternate command, both
`UV_PROJECT_ENVIRONMENT=/tmp/neurofold-nf03-py313` and the same UV_CACHE_DIR were
set, and `--python 3.13` was supplied consistently:

```sh
uv sync --locked --python 3.13
uv run --locked --python 3.13 python --version
uv run --locked --python 3.13 ruff check . ../infra/testing
uv run --locked --python 3.13 ruff format --check . ../infra/testing
uv run --locked --python 3.13 mypy src tests scripts ../infra/testing
uv run --locked --python 3.13 pytest
```

Python **3.13.2**: locked sync, lint, format and strict mypy **passed** (60 files).
Full pytest **1,341 passed, 0 failed**, **97.10%** coverage, 35.43 seconds. The
3.13 pytest used `COVERAGE_FILE=/tmp/neurofold-nf03-coverage313` to avoid sharing
coverage output with 3.12. The default `.venv` remains Python 3.12.16; no lock
changes or replacement of that environment occurred.

Additional offline check from `backend/`:
`uv run --locked python tests/contract_exchange.py` **passed**, producing nine
actual biological route/service/parser/archive response groups with original-byte
payload. This also ran through the frontend behavior suite's guarded child.

From `frontend/`, under Node v24.5.0:

```sh
npm ci --cache /tmp/neurofold-npm-cache --offline
npm run lint
npm run typecheck
npm run build
npm run test
```

All **passed**, locked npm install audited 269 packages; **4 test files / 36 tests
passed**, 0 failures. No frontend source/lock changes.

`docker compose config --quiet` **passed**. Docker daemon/build/smoke checks are
**unavailable**: `docker info --format '{{.ServerVersion}}'` could not connect to
`~/.colima/default/docker.sock` (socket absent). No daemon was started or existing
stack altered. Updated injected offline composition is tested in-process by the
full backend suite. Native browser, local proxy, live-provider and container
investigations were not repeated for these offline HTTP routes. The existing
frontend contract-exchange/component checks passed; no new browser interaction
was implemented or claimed. `git diff --check` passed.

## Remaining gates

NF-07 mutation entry/inspection/confirmation/highlighting, prediction/runtime,
viewer, comparison, complete scientific provenance/export and independent
scientific acceptance remain open. Full pinned sequence numbering includes the
initial methionine and does not identify an atom or author residue number. These
software tests validate a sequence hypothesis and archive/transport behavior;
they establish no disease effect, model accuracy, clinical utility or broader
provider/platform compatibility. Container execution remains unavailable in this
checkpoint; previous operational evidence is not relabeled as a new run.
