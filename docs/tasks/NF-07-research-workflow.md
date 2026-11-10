# NF-07 — Research Workflow UI

Status: proposed. Parent: [NF-EPIC-001](../EPIC.md).

## 1. Objective and scientific motivation

Connect protein selection, sequence inspection, substitution definition,
prediction, visualization, comparison and export into one inspectable research
workflow. Researchers should always know which reference, variant and evidence
they are viewing and be able to recover from incomplete or failed steps.

## 2. Scope and non-goals

Include accession/gene search, organism disambiguation, reference confirmation,
sequence/difference view, variant validation, explicit prediction settings,
reference/variant jobs, progress, Mol* results, comparison reports, provenance and
export. Include loading/empty/partial/error states and keyboard-accessible controls.

Exclude authentication, research-team collaboration, clinical recommendations,
private sequence uploads, dashboards unrelated to this workflow, automatic
prediction upon search, and organoid features. No model or database logic belongs
in React. A CPU fake mode is a clearly labeled development/release-preview mode,
not an automatic substitute when real inference is unavailable.

## 3. Dependencies

- NF-02 lookup, pinned references and structure import/read routes.
- NF-03 immutable variant creation and structured difference.
- NF-04 capabilities, jobs, cancellation and results.
- NF-05 encapsulated viewer and residue selection events.
- NF-06 comparison creation/result contracts.
- NF-08 manifests/export routes; NF-09 frontend test tooling and CI.

Develop screens against reviewed mock contracts while prerequisites mature;
integrated acceptance requires their real HTTP implementations. NF-07 does not
block backend scientific contracts.

## 4. Proposed architecture and interfaces

Use React function components and strict TypeScript, preserving the existing
HTTP boundary. Introduce a typed `frontend/src/api/` layer with runtime response
validation and centralized error-envelope handling. Choose validation/testing
dependencies only when needed and update npm manifest/lockfile together.

Proposed components: `ProteinSearch`, `ProteinCandidateList`, `ReferenceSummary`,
`SequenceView`, `VariantEditor`, `PredictionSetup`, `PredictionJobPanel`,
`StructureWorkspace`, `ComparisonReport`, `ProvenancePanel` and `ExportPanel`.
`StructureWorkspace` delegates Mol* details to NF-05. A reducer/state machine
coordinates immutable IDs and async operations; component-local state handles
temporary text/selection. Start without a global state library unless measured
complexity justifies one.

Use relative `/api/v1` requests under current development routing; production
routing is an explicit NF-09 release requirement for deployed use. Abort obsolete
fetches and ignore late responses by operation/reference ID. Switching reference
invalidates dependent selections but never deletes immutable backend records or
silently cancels running jobs.

## 5. Data models and API contracts

Frontend DTOs mirror API contracts, not Python internals. Store reference/variant/
job/structure/comparison/export IDs plus selected sample/chain/model/operator and
display preferences. Persist only public opaque IDs and harmless UI preferences
in a versioned local resume record; do not persist raw sequences, signed links,
credentials or research artifacts in browser storage. On reload re-fetch records,
check schema/availability, and explain expired/missing data. Do not pretend a local
resume record is a provenance manifest or a shared research account.

| Step | Actions and HTTP contracts | Required states |
| --- | --- | --- |
| Select protein | NF-02 search or accession lookup; select organism/entry | idle, loading, multiple matches, empty, stale/partial, upstream error |
| Pin reference | inspect sequence/source/version, then `POST /v1/references` with inspected hash | ready, pinning, source changed/conflict, unsupported reference |
| Define variant | enter notation, preview residue/window, `POST /v1/variants` | draft, locally invalid, server validating, validated, mismatch/error |
| Configure predictions | load capabilities; select profile, seed and parameters; disclose any MSA transfer | available, synthetic mode, real worker unavailable, unsupported settings |
| Submit/monitor | submit distinct reference and variant jobs with idempotency keys; poll job routes | submitting, queued, running, cancelling, failed, cancelled, succeeded |
| Inspect structures | import experimental selection or open job sample in NF-05 | loading, ready, no experimental structure, missing mapping, no confidence, viewer failure |
| Compare | choose compatible samples/chains and method; `POST /v1/comparisons` | incomplete selection, computing, incompatible/ambiguous, report, failed |
| Export | inspect NF-08 inventory and create/download export | preparing, ready, partial/permission omission, failed verification, expired |

Client variant syntax checks improve feedback; the backend remains authoritative
for sequence validation and identity. Show 1-based positions, numbering convention,
nearby reference sequence and the precise substitution before prediction.

For paired predictions, retain two explicit job IDs and display each status. If
one submission fails, preserve the accepted job and retry only the missing one.
Do not create a second job on double-click or uncertain network response: retain
the request's idempotency key until its outcome is known. A deliberate new run
uses a new key and records retry lineage when appropriate.

Proposed polling: start at two seconds, back off to ten seconds with jitter, stop
on terminal states/unmount, and pause or reduce activity in a hidden tab. A transport
failure means status is unknown, not that the scientific job failed. On recovery
query the same job. Running stages without numeric progress use an indeterminate
indicator; do not invent percentages or completion-time estimates.

Always expose a textual provenance summary: accession/taxon/reference version/hash,
variant, evidence origin, experimental method or model/profile, selected sample,
confidence definition, mapping coverage and manifest link. Place uncertainty and
comparison limitations beside results. Synthetic labeling remains visible through
every step and export.

## 6. Implementation milestones

1. **M1 — State/API layer:** finalize DTOs, reducer transitions, resume format,
   request cancellation, error translation and mocked interaction fixtures.
2. **M2 — Sequence slice:** search/disambiguation, reference pinning, readable
   sequence display and server-validated variant/difference preview.
3. **M3 — Prediction slice:** capabilities/settings disclosure, paired submission,
   idempotent recovery, polling/cancellation and NF-05 sample inspection.
4. **M4 — Comparison/export:** selected structures, report/overlay, confidence and
   provenance, NF-08 export inventory/download, keyboard and error recovery review.

## 7. Acceptance criteria

- A researcher completes the entire supported flow with public/synthetic data;
  selected reference and variant stay visible and consistent across steps.
- Search ambiguity, source changes, invalid substitutions and unsupported profiles
  prevent dependent submission with actionable errors.
- Double-clicks, reloads, late responses and partial paired submission do not
  silently duplicate jobs, mix references or discard accepted results.
- Network loss preserves a recoverable job ID and an unknown-status message;
  cancellation remains pending until the worker confirms it.
- No structures/confidence/mapped mutation coordinates is a supported state.
  The sequence, metadata and provenance remain readable without WebGL.
- Keyboard navigation, focus management, semantic labels, live status/error
  announcements and non-color alternatives cover all workflow controls.
- Export identifies exact selected samples/comparison and any omitted content;
  no view suggests that a structural difference establishes disease causality.

## 8. Automated testing requirements

Component/reducer tests use HTTP mocks for all required states: ambiguous search,
pin conflict, sequence mismatch, rapid reference switches, stale responses,
variant preview, capability failure, disclosure acknowledgement, paired submission
failure, duplicate clicks, timeout with unknown submission outcome, polling
recovery, cancellation, reload, missing confidence/mutation coordinates, comparison
errors and export omissions. Assert user-visible behavior and accessible roles.

An end-to-end browser test runs API plus a separate fake worker and synthetic
catalog: select → pin → variant → two predictions → view → compare → export.
Add failure/retry and no-WebGL paths. Disable external network access, use fixed
fixtures/clocks where relevant and verify synthetic labels. Separate actual Mol*
WebGL coverage from tests using its fake controller. Lint/typecheck/build remain
required but do not replace interaction tests.

## 9. Scientific validity and reproducibility

Show evidence and hypothesis separately: reference databases provide source
annotations, experimental structures have methods/constructs, predictions have
model confidence, and a proposed mutation is a research hypothesis. The UI must
not translate RMSD/confidence into a disease risk color or an unsupported verdict.

Submission uses immutable IDs and complete resolved settings. Expose protocol
differences between reference/variant runs before comparison, retain sample
selection and avoid hiding excluded residues or low-confidence regions. Sequence
disclosure for optional network MSA generation requires an explicit informed
choice; public-data MVP scope does not justify undisclosed outbound calls.

## 10. Risks and unresolved decisions

- **Navigation/resume:** default to one explorer flow and versioned public-ID
  resume state. A routing/state library requires a concrete need in M1, not an
  assumption of a larger application.
- **Long sequences/large structures:** choose readable pagination/virtualization
  and viewer limits from measurements; preserve correct 1-based selection.
- **Frontend tooling:** agree and lock component/browser test tools in NF-09 M1;
  test compatibility with the current React/TypeScript/Vite versions.
- **Deployment:** current Vite preview has no API proxy. A deployed release needs
  documented same-origin production routing before the workflow is advertised.
