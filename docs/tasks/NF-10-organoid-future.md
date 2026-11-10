# NF-10 — Future Organoid Research Integration

Status: future research direction; explicitly outside the Protein Variant Explorer
MVP. This document specifies discovery work only and authorizes no implementation.
Parent: [NF-EPIC-001](../EPIC.md).

## 1. Objective and scientific motivation

Investigate whether NeuroFold can connect molecular research records to organoid
experiments and imaging-derived observations. Possible questions concern how
defined experimental conditions and cellular models relate to measured phenotypes,
with molecular predictions retained as hypotheses rather than explanations proved
by an image or correlation.

## 2. Scope and non-goals

Potential future capabilities, subject to a new approved research scope:

- Ingest microscopy dataset references and instrument/acquisition metadata.
- Analyze fluorescence images with declared preprocessing, segmentation and
  measurement definitions.
- Describe organoid experiments, specimen/condition/batch lineage and controls.
- Track time series and imaging-derived measurements with units and uncertainty.
- Link experiments/observations to molecular records through explicit, reviewed
  identifiers and evidence relationships.

This task's deliverable is a feasibility/protocol specification and decision
record, not a working ingestion pipeline. No image processing dependency, dataset,
storage service, patient/donor registry, UI, API, queue or model is added to the
MVP. Exclude clinical interpretation, automated causal attribution, unconsented
human data, patient reidentification and direct experimental control.

## 3. Dependencies

- A completed NF-EPIC-001 MVP and stable NF-08 provenance/export identities provide
  candidate integration seams, not sufficient scientific validation.
- A new, approved research question with domain collaborators, experimental
  protocol, controls, quantitative endpoints and data/ethics governance.
- Independent licensing/privacy review for each future dataset and method;
  acquisition permission cannot be inferred from repository access.
- Imaging format, size, retention and compute feasibility assessment before any
  infrastructure choice. No MVP task depends on NF-10.

## 4. Proposed architecture and interfaces

If a later project is approved, define a separate imaging/experiment domain with
standard-library records/protocols in core and optional ingestion/measurement
adapters. A proposed application service can coordinate those adapters and link
immutable molecular record IDs. API concerns remain in `api/`; frontend
visualization remains behind components and HTTP. Do not couple organoid metadata
to `PredictionAdapter.predict` or force image records into sequence schemas.

Large image storage and processing may justify dedicated artifact/compute adapters,
but actual dataset sizes and access patterns must drive that decision. Treat
candidate formats such as OME-TIFF/OME-Zarr as options requiring primary-spec
review during discovery, not promised support or current dependencies.

## 5. Candidate data models and API contracts

These are research concepts, not committed public schemas or endpoints:

| Concept | Information to resolve in future discovery |
| --- | --- |
| Experiment record | opaque experiment ID, protocol/version, model/specimen lineage, conditions, controls, batches/replicates, acquisition references, governance |
| Imaging dataset | immutable dataset ID, source manifest/hash inventory, format/version, dimensions/axis order, channel definitions, physical pixel/voxel units, time base, acquisition/calibration metadata and license |
| Analysis run | input IDs/hashes, preprocessing/segmentation/measurement method versions, parameters, environment/model weights if any, transforms and QC |
| Measurement | defined quantity, units, time/region/specimen identity, uncertainty, missingness/exclusion reasons, analysis-run lineage |
| Molecular relationship | molecular record ID, experiment/measurement ID, relationship type, evidence source, reviewer and hypothesis/observation distinction |

Future API contracts require a separate review of pagination/large objects,
immutable identity, provenance, error semantics and access control. Do not reserve
MVP `/v1` routes or imply that molecular record association is evidence of a causal
relationship. Retain acquisition originals and version all image transformations.

## 6. Future implementation milestones

1. **M1 — Research discovery only:** choose one question and measurement endpoint;
   document biological system, controls, technical/biological replicates, relevant
   confounders and the meaning of a molecular-to-experiment link.
2. **M2 — Governance/format feasibility:** review permissible synthetic/public
   inputs, rights/privacy, metadata completeness, candidate standards, dataset
   sizes, calibration and compute/storage requirements; make a go/no-go decision.
3. **M3 — New roadmap:** if approved, create a separate epic with validated
   schema/API proposals, adapter boundaries, resource budgets and test plan.
4. **M4 — Conditional future work:** only under that new scope, implement a small
   licensed/synthetic vertical slice and validate measurements before real-data
   ingestion or interpretation. This milestone is not authorized here.

## 7. Acceptance criteria

For this documentation-only direction, acceptance means a clearly deferred scope,
candidate capabilities, dependencies, scientific/governance questions and no MVP
runtime changes. NF-EPIC-001 can ship without NF-10 implementation.

For future discovery, a go/no-go record must name the question, data permissions,
measurement definitions/units, controls, metadata standards under review, expected
resources, privacy boundaries and validation protocol. A no-go result is valid;
discovery must not assume a platform expansion is scientifically justified.

## 8. Automated testing requirements

No new application tests are added for this planning-only direction. A future
implementation plan must require tiny synthetic images with known geometry,
intensity, channels and time points; tests for axis/unit/calibration errors,
missing frames, corrupt metadata and immutable originals; known-answer measurement
checks; provenance/relationship contracts; and frontend selection/error behavior.

Deterministic preprocessing should use exact fixtures where appropriate; floating
point or learned measurement methods need justified tolerances and independent
validation. Tests must not require patient data, large image collections, external
services or model weights in ordinary CI. Real measurement validation is a
separate evidence gate, not replaced by synthetic pipeline tests.

## 9. Scientific validity and reproducibility

Distinguish raw microscopy observations, processed representations,
algorithm-derived measurements and biological interpretations. Preserve channel
semantics, spatial/temporal units, calibration, thresholds, masks, segmentation/QC,
excluded observations and every coordinate/intensity transformation. Do not equate
fluorescence intensity with protein abundance without a validated measurement
model, or imaging association with mutation causality.

Record experimental lineage, batch effects, temporal sampling, technical versus
biological replicates and uncertainty. Any learned analysis method requires exact
model/weight identity, independent licensing and a validation set appropriate to
the declared endpoint. Human-derived material and microscopy metadata may carry
sensitive information even when obvious identifiers are removed; establish actual
governance before data access, not by assuming molecular MVP rules are sufficient.

## 10. Risks and unresolved decisions

- Which experimental system and outcome warrant molecular integration, and who
  defines/validates that endpoint?
- What data access, consent, licensing and metadata permissions apply?
- Which format/metadata standards fit acquisition and analysis without losing
  channel, axis, physical-unit or temporal information?
- How are experiment/measurement identities linked to sequence/variant records,
  and who verifies those relationships?
- What dataset volume, retention, calibration/QC and compute model are necessary?
- What controls and independent measurements can test conclusions while accounting
  for batch effects, segmentation error and pseudoreplication?

Resolve these in a later research proposal. None authorizes organoid functionality
or extra infrastructure in the current MVP.
