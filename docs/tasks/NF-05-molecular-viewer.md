# NF-05 — Molecular Visualization

Status: proposed. Parent: [NF-EPIC-001](../EPIC.md).

## 1. Objective and scientific motivation

Let researchers inspect experimental and computational structures with an
interactive Mol* viewer, locate mapped substitution sites, and understand what
is observed, predicted, missing or uncertain. A compelling rendering must not
conceal the provenance or limitations of the coordinates.

## 2. Scope and non-goals

Load registered mmCIF artifacts; rotate/zoom/reset; choose a recorded model/chain;
select residues; highlight the substitution; display structure metadata and
supported confidence; and accept NF-06 alignment transforms for overlays.
Experimental browsing is useful before inference is available.

Exclude inference or scientific alignment in the browser, arbitrary remote file
URLs, clinical annotations, trajectory simulation, editing coordinates, electron
density/map validation and an independent Mol* server. Loading a structure must
not silently request third-party data or expose sequences to external services.

## 3. Dependencies

- [NF-02](NF-02-biological-data.md) descriptors, mmCIF artifacts and residue maps.
- NF-03 structured substitution/reference positions.
- [NF-08 M1](NF-08-reproducibility.md) artifact, evidence and metric descriptors.
- NF-04 adds predicted samples; use synthetic fixtures for initial development.
- NF-06 later supplies scientific transforms/selection mappings. Its backend
  numerical work does not depend on the initial viewer implementation.

## 4. Proposed architecture and interfaces

Add Mol* as a frontend dependency with independent license/notice review and a
matching `package-lock.json` update during implementation. Check the selected
release against the repository's React, strict TypeScript, Vite and Node 24 stack.
Keep the integration in `frontend/src/components/molecular/` behind a narrow
controller; workflow components must not manipulate Mol* internals.

Proposed `MolecularViewer` inputs: structure descriptors, chosen sample/model/
chain, residue map, optional mutation, confidence descriptor and optional NF-06
transform. Outputs: ready/error events and serializable residue selection events.
An internal `ViewerController` exposes load, select, highlight, color, apply
display transform, reset and dispose. It owns Mol* state and subscriptions.

Use a dynamically loaded viewer module and one managed plugin instance per
mounted canvas. React cleanup aborts loads, unsubscribes listeners, revokes object
URLs and disposes the instance. Generation tokens discard late loads after a
structure switch. Handle React strict-mode mount/unmount and WebGL context loss.
Mol* documents instance lifecycle in its
[plugin guide](https://molstar.org/docs/v5/plugin/instance/).

Fetch approved bytes from backend artifact IDs via HTTP, with size/type checks and
abort signals; never accept a local Python path. Disable unused remote behaviors
and validate that default viewer controls do not trigger undisclosed fetches.
Scientific metadata remains accessible as text if WebGL is unavailable.

## 5. Data models and API contracts

No new backend inference API is needed. Consume NF-02 `GET /v1/structures/{id}`,
`GET /v1/artifacts/{id}` and NF-04 job results. All public links resolve through
the configured API origin, including the existing `/api` development prefix.

`ResidueSelection` contains structure ID/hash, model ID, entity ID, label/auth
chain, label sequence ID, auth sequence ID, insertion code, assembly operator,
optional reference ID/position and mapping status. Send this plain object to the
workflow; Mol*'s in-memory selection objects stay internal. Selection creation and
events should follow the documented [Mol* selection interface](https://molstar.org/docs/v5/plugin/selections/).

`ConfidenceDescriptor` contains metric name/definition/version, source artifact,
raw field and scale/range, units, scope (sample/residue/token/pair), direction,
normalization formula if any, token/residue map and missing-data mask. Use exact
adapter metadata, not file extension or value heuristics. A confidence scale can
be 0–1 or 0–100; it must be declared before using a palette. Experimental
temperature factors are not automatically pLDDT. Unsupported metrics receive a
textual unavailable reason. PAE/PDE are pairwise metrics, not arbitrary scalar
residue colors.

`DisplayState` records structure/sample IDs, model/chain/assembly choice, style,
color mode, visible selections and optional comparison ID/transform. Any future
saved camera matrix must be finite and versioned. Display transformations never
alter the raw coordinate artifact or replace the scientific comparison record.

Mutation highlighting maps NF-03's reference position through NF-02's residue
map. Only unambiguous coordinate-present mappings produce an atom selection. Show
`not resolved`, `outside construct`, `ambiguous`, or `residue differs` as applicable;
never substitute the nearest visible residue. Multiple assembly copies require
an explicit operator/copy choice, or a clearly labeled all-copies selection.

## 6. Implementation milestones

1. **M1 — Viewer lifecycle:** lock compatible Mol*, isolate controller, load a
   tiny synthetic mmCIF, implement cleanup and unsupported-WebGL fallback.
2. **M2 — Experimental inspection:** connect registered artifacts/descriptors,
   model/chain controls, metadata, sequence-to-viewer and viewer-to-sequence
   selection, and mapped mutation highlighting.
3. **M3 — Prediction display:** handle NF-04 samples, explicit evidence badges,
   confidence mapping/legend/missing values and artifact failures.
4. **M4 — Comparison display:** accept NF-06 transforms and paired selections;
   keep raw structures intact and show alignment provenance.

## 7. Acceptance criteria

- Experimental and predicted/synthetic artifacts load using one HTTP-facing
  component boundary, with origin/model/sample/chain identity always visible.
- Rotation, zoom, reset and residue selection work. Reference selections and
  canvas selections round-trip through the same mapping contract.
- Mutation highlights respect missing residues, insertion codes and chain/operator
  identity. Missing or ambiguous sites produce explanations, not wrong highlights.
- Confidence colors include a readable metric/scale legend and unavailable state;
  experimental B-factors are not mislabeled as predicted confidence.
- Switching artifacts cancels/discards prior loads; unmounting releases resources.
  Failed downloads, invalid mmCIF and WebGL failure preserve accessible metadata.
- Applying an overlay does not modify source bytes or recalculate scientific
  metrics using an undocumented browser algorithm.

## 8. Automated testing requirements

Add component interaction tests with a fake controller for load/error states,
unmount/dispose, strict-mode remount, stale responses, sample/chain controls,
selection events, missing mutation mapping, confidence legends and text fallback.
Use the frontend testing toolchain established with NF-09 M1 and lock dependencies.

Browser tests with actual Mol* and tiny synthetic mmCIF cover initialization,
selection, mutation highlighting, structure switching and overlays. Use a stable
software-rendered CI WebGL configuration where possible; assert controller/state
and selected identifiers rather than relying solely on screenshots. Explicitly
test the no-WebGL fallback. Mark WebGL test environment failures separately from
scientific or application failures. No remote downloads or model execution.

## 9. Scientific validity and reproducibility

A rendered structure is a model even when experimentally derived. Show method,
construct, model/assembly, source revision, mapped coverage and missing coordinates.
Predicted structures include model/profile and manifest links; fake outputs carry
a persistent synthetic label. Confidence estimates are model-specific and do not
establish correctness, pathogenicity or statistical significance of a mutation.

Preserve units and coordinate frames in overlays. Record sample/selection/color
choices in the exportable display state where meaningful, separately from raw
data. Avoid color-only communication and provide a sequence/table alternative.

## 10. Risks and unresolved decisions

- **Mol* compatibility/bundle size:** select and smoke-test a release with current
  React/TypeScript/Vite before M1; measure lazy-load behavior with representative
  sizes and define explicit limits rather than silently reducing structures.
- **WebGL support:** establish browser/CI support in M1 and document fallback;
  accessibility cannot depend on an interactive canvas alone.
- **Confidence normalization:** pin metric-specific conversion/mapping in NF-04
  and NF-08 before M3. Unknown scales stay unavailable.
- **Assembly selection:** use the shared model/chain/operator contract; broader
  multi-chain comparisons need an explicit later scientific scope decision.
