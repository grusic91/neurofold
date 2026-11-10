# NF-02 M1 acceptance evidence

Date: 2026-11-10. Scope: biological data **contracts only**, reviewed by the
implementing agent from local code, fixtures and command results. No independent
domain reviewer, biological validation or scientific approval is claimed.

## Baseline and change identity

Initial working tree was clean at
`ca01300b4e6bf33abfbdd072aa1a20921e339681` (completed NF-09 M1). Inspection of
Git history, application/core/tests, requested specifications and fixture inventory
confirmed NF-01, NF-08 M1 and NF-09 M1. There was no uncommitted work to preserve.
No commit, push, publication, deployment or PR was performed.

Package/application versions remain 0.1.0. NF-02 introduces
`neurofold-biological/1` and HTTP schema `urn:neurofold:biological-http:1`.
NF-08 `neurofold-research/1`, `neurofold-json/1`, `raw-bytes/1` and
`sequence-ascii/1`, their original fixtures/schema, dependency manifests/locks,
CI and LICENSE remain unchanged. Production OpenAPI still lists `/health` only.

| Exact file identity | Raw SHA-256 |
| --- | --- |
| `backend/uv.lock` | `f873e9dc63115642982bb18397444b1a60d75b41c556161acf71cb428251d9fd` |
| `frontend/package-lock.json` | `895d5c748dd378082bbf7860dc545fe14b734cf7d248e17081315b07cfc585de` |
| `docs/testing/fixtures.json` | `bda2f549ce4629778a22073fdf72399ff10907a066a65aad7cb3b8557a97a706` |
| `docs/schemas/neurofold-biological-http-1.schema.json` | `acde8893ea3997650d7dffeb198596b177442f81db53b29ac94677ba0f9bd71c` |

Working-tree change identity, excluding this record:
`2ca8ac683ee2f30b7973424df111be96c6c3a896ab956cf166c6eec48abca2fb`.
Computed as SHA-256 of compact sorted-key UTF-8 JSON containing the path-sorted
array of `{"path": relative_path, "sha256": raw_file_sha256}` for modified and
untracked nonignored files relative to the baseline. Exclude this evidence file
to avoid circular identity; recompute after any further edits. This is local
working-tree evidence, not a release revision or CI attestation.

Environment: macOS 27.0.1 (26A434), arm64 CPU-only; Python 3.12.16,
uv 0.13.7, Node 24.5.0, npm 11.5.1; pinned Playwright 1.65.0 with the existing
Chromium installation. No live biological endpoints, GPUs, weights, downloaded
structures, research data or scientific runtime were used. Primary-source policy
web pages were consulted only for the [licensing inventory](../source-licensing.md),
separately from offline tests.

## Contract acceptance

| M1 deliverable | Evidence | Outcome |
| --- | --- | --- |
| Immutable reference/structure records | Frozen stdlib dataclasses, tuple collections, exact sequence/raw/canonical hash domains, source versions/receipts, UTC capture, strict wire round trips and mutation rejection | pass |
| Residue identities/states | Reference ID/sequence hash, structure ID/raw hash, entity/label/auth chain, model/assembly/operator, insertion code, string author numbering; exact/mismatch/unobserved/unmapped/ambiguous and non-exact reasons | pass |
| Missing information | NF-08 Metadata/ReferenceCollections, absent source metadata/resolution/coverage/mappings, synthetic evidence and independent ArtifactRights; no zero/null substitution | pass within record validation scope |
| Core protocols | ProteinCatalog, ExperimentalStructureCatalog, ReferenceRepository, StructureRepository; reused NF-08 ArtifactStore; no implementations or new third-party core imports | pass |
| HTTP contracts | Explicit request/response DTOs, frozen schema, request bounds/strict body types, core conversion and descriptor/map cross-integrity checks | pass |
| API contracts | Separate in-process fixed-response harness for all eight proposed operations, request/response validation, OpenAPI shape, 201/Location, raw placeholder bytes/media type/length/checksum/ETag; stable error envelope/status shapes | pass as contracts; operational routes/translation unimplemented |
| Source licensing/attribution | Reviewed primary UniProt/RCSB policy scope, attribution/changes, separate fixture license, missing-rights and recheck policy in inventory | pass as inventory; per-source retrieved artifact/export review deferred |
| Tiny provider fixtures | Authored synthetic UniProt-shaped JSON (6-letter sequence), RCSB entry/entity/instance JSON, frozen biological records with six manually specified mapping rows; raw hashes/sizes and provenance in inventory | pass; not live compatibility or structural import evidence |
| Documentation | Root README, architecture, epic, NF-02 status, provenance ownership, testing guide/matrix, contract decisions and evidence | pass |
| Architectural/scope preservation | API → core ← adapters; core imports without site-packages; startup/health unchanged; no clients, cache, lookup/import, inference, jobs, database, auth or new dependencies | pass |

Fixture inventory now has eleven entries. Standalone NF-02 biological JSON is
under 40 KiB; each provider example is under 1 KiB. No molecular coordinates are
committed. The synthetic mmCIF descriptor refers to a **44-byte diagnostic
placeholder**, whose exact bytes are served only by the test harness; it is not
a molecular file or imported structure. The map is hand-authored, not inferred
from that placeholder. Fixture tests independently check actual provider JSON
raw sizes/hashes and the six-letter sequence hash. Original NF-08 frozen fixtures
are preserved. All backend behavior tests use default socket/DNS guards.

## Checks

| Command / environment | Local result |
| --- | --- |
| `uv sync --locked` | pass; no dependency changes |
| `uv run --locked ruff check .` | pass |
| `uv run --locked ruff format --check .` | pass, 21 files |
| `uv run --locked mypy src tests` | pass, 21 source files |
| `uv run --locked pytest` | 278 passed (129 new NF-02 tests); 100% statements, 99.70% combined statement/branch coverage; 90% minimum retained |
| Python 3.13.2 `-I -S` stdlib smoke | pass: import every core module; deserialize/serialize five biological root records against frozen fixtures; no third-party packages |
| Full Python 3.13 Ruff/mypy/pytest environment | not run; the stdlib smoke is not full 3.13 acceptance |
| `npm ci` | pass; lock unchanged |
| `npm run lint` | pass |
| `npm run typecheck` | pass |
| `npm run build` | pass |
| `npm run test` | 12 passed |
| `npm run test:browser` | 8 passed across Chromium and WebGL-disabled Chromium |
| `docker compose config --quiet` | pass |
| `docker info --format '{{.ServerVersion}}'` / configured context `colima` | unavailable: `/Users/gasperus/.colima/default/docker.sock` does not exist |
| `docker --context colima-arm64 info --format '{{.ServerVersion}}'` | unavailable: `/Users/gasperus/.colima/arm64/docker.sock` does not exist |
| `docker --context default info --format '{{.ServerVersion}}'` | unavailable: `/var/run/docker.sock` does not exist |
| Container builds/services/proxy smoke | not run; no daemon available through any configured context; Docker CLI 29.5.2 is installed |
| `git diff --check` and local documentation link checks | pass |

uv initially could not create a lock in the default user cache; commands used
`UV_CACHE_DIR=/private/tmp/neurofold-uv-cache`, preserving `--locked` and the
project environment. An early check ran outside `backend/` and failed to find
the tools; the required checks above were rerun from `backend/`. The first
browser run could not bind `127.0.0.1:4173` under the sandbox (EPERM). It passed
when rerun with permission for loopback preview/browser execution. No browser
redownload or daemon provisioning was needed. These sandbox restrictions are
distinct from the missing Docker sockets.

During development, new tests caught an incorrect placeholder byte size
(43 versus actual 44), an incorrect route-count assertion and a Pydantic query
annotation order that emitted nonstandard `ge`/`le` schema keywords. These were
corrected before freezing/reviewing the contract; the final schema uses standard
`minimum`/`maximum`, and final fixture receipt hashes/sizes match actual bytes.

## Review, gaps and gate decision

Reviewed new source files, test harness/fixtures, frozen schema, documentation and
full tracked diff; verified no changes to runtime manifests/locks, NF-08 contracts,
LICENSE, frontend source, adapters, CI or application route registration. Checked
synthetic labels, per-artifact rights, canonical/raw/sequence identity separation,
missing mappings, numbering/gaps/tags, bounded HTTP fields and all fixture sizes.
Current CI commands already cover new tests via backend pytest and import checks;
no CI workflow changes are needed. CI IDs/results are unavailable because no push
was authorized. Linux execution and full Python 3.13 suite remain unverified.
Configured local Docker endpoints were rechecked rather than inheriting NF-09's
availability result. Container/Linux/full-3.13 gaps do not block M1 contract design.

M1 contract acceptance: **pass within the documented scope**. Biological
integration and all NF-02 M2–M4 behavior remain **incomplete**: live provider
compatibility, encoded queries, cursor binding/expiry, cache/revalidation,
source-change detection, transport error/status translation, resource/retry
limits, source-origin verification, atomic immutable storage, downloads,
mmCIF parsing, reference-to-polymer alignment, actual reference/residue/length
consistency, full mapping/coverage production and operational routes.
Core validates declared identities/states; it cannot establish their truth from
raw bytes without those producers. Harness error responses do not prove real
404/409/retry/partial-failure orchestration. Parser/alignment license review,
current source-notice capture, model/data licenses, exports, independent domain
review and real scientific release gates remain future work. No accuracy,
biological causality, clinical validity or real scientific MVP is claimed.
