# NF-06 — Scientific Structure Comparison

Status: proposed. Parent: [NF-EPIC-001](../EPIC.md).

## 1. Objective and scientific motivation

Compare structures associated with a pinned reference and its single-substitution
variant using explicit residue correspondence, reproducible rigid alignment and
clearly defined metrics. The result should explain which atoms were compared and
what the numbers can support, rather than present structural distance as a
biological effect score.

## 2. Scope and non-goals

Support single-chain reference-prediction versus variant-prediction comparisons,
and optional experimental-versus-predicted context. Require explicit sample,
model, chain and assembly/operator selection. Include sequence/residue mapping,
C-alpha rigid alignment, RMSD, per-residue displacement, coverage and confidence
summaries. Distinguish all evidence origins, including synthetic fixtures.

Exclude automated homolog discovery, multi-chain permutation matching, flexible
alignment, energy/stability/aggregation/affinity predictions, disease-causality
inference and undocumented composite scores. TM-score, lDDT and other advanced
metrics may be designed later; they are not required implementations for this
MVP. pTM/pLDDT confidence outputs are not measured structural similarity scores.

## 3. Dependencies

- NF-02 structure descriptors, source sequences, mmCIF and initial residue maps.
- NF-03 shared canonical numbering and immutable variant definitions.
- NF-04 exact predicted samples and confidence descriptors.
- [NF-08 M1](NF-08-reproducibility.md) method/transform/artifact provenance.
- NF-05 is needed for visual overlays, not for implementing the numerical service.
  Synthetic analytic fixtures precede any real-model interpretation.

## 4. Proposed architecture and interfaces

Core defines frozen `ComparisonRequest`, `ResidueCorrespondence`,
`AlignmentTransform`, `ComparisonMetric`, `ComparisonResult` and
`StructureComparisonEngine`/repository protocols using standard-library types.
Core owns validation/selection policy; a numerical adapter owns parsing, arrays,
sequence alignment and fitting. No NumPy, parser or model import enters core.

An application `ComparisonService` loads verified registered structures and
reference maps, checks compatibility, delegates numerical work, and atomically
stores an immutable result/manifest. It must not call inference. Use a bounded
CPU service invocation outside the async event loop (for example a synchronous
FastAPI route delegated through its thread pool), with measured coordinate limits
and timeout/admission bounds. If measured workloads cannot meet the interactive
budget, adopt the NF-04 job seam explicitly rather than blocking indefinitely.
No extra broker is needed for the bounded MVP comparison.

NF-05 consumes the stored transform and correspondence. Browser camera/display
operations do not define or alter scientific metrics.

## 5. Data models and API contracts

Proposed `POST /v1/comparisons` accepts the ordered `reference_structure_id`,
`variant_structure_id`, `reference_id`, `variant_id`, explicit model/chain/operator
selections for each, and versioned `method_profile_id`, optional fit/evaluation
reference-position ranges and optional confidence-filter policy. Return 201 with
immutable result and `Location`; an identical canonical request against the same
artifact hashes may return 200 and the stored result. `GET /v1/comparisons/{id}`
returns 200 or 404. A reference-prediction must match the reference sequence; a
variant-prediction must match the specified variant. An experimental contextual
comparison declares its role and records sequence mismatches rather than claiming
it is an exact unmodified control.

422 errors include `INCOMPATIBLE_REFERENCE`, `AMBIGUOUS_MAPPING`,
`INSUFFICIENT_ATOMS`, `DEGENERATE_FIT`, `UNSUPPORTED_STRUCTURE`, and
`INVALID_SELECTION`. 413 rejects size bounds; 429 rejects excess local capacity;
504 reports a comparison execution timeout with a retry hint. No invalid
comparison produces a numeric zero. Unknown or missing source artifacts yield
404 or an explicit integrity error, respectively.

Required output:

- Input IDs/hashes, evidence kinds, sequence/construct differences, selected
  sample/model/chain/operator and source manifests.
- Full correspondence table linking reference positions to both structure residue
  keys, with included/excluded status and reason.
- Mapping method/version, sequence alignment and score/tie status; sequence
  identity numerator/denominator; coverage counts; atom/alternate-location policy.
- Fit and evaluation atom-pair lists, transform, metric definitions/units,
  nullable confidence, warnings and method/environment provenance.
- Canonical request hash, immutable comparison ID and manifest/artifact links.

### Correspondence and atom selection policy

1. For NF-04 matched predictions, map chains to their exact input sequence using
   the recorded token/residue map; verify the expected single substitution.
2. For experimental context, reuse a verified NF-02 map tied to the same reference
   and structure hashes. Provider mapping or sequence alignment must include its
   method/version. If alignment is needed, proposed default is affine semiglobal
   alignment of the full polymer sequence to the reference, with free reference
   terminal overhangs, match +2, mismatch -1, gap-open penalty 10 and extension
   penalty 0.5. Define a length-k gap cost as `10 + 0.5*(k-1)`. Pin this policy
   and test ties before use; equally valid repeated-domain mappings return
   ambiguity rather than choosing the first occurrence.
3. Establish correspondences through reference positions, not equal author residue
   numbers or spatial nearest neighbors. A documented expected substitution remains
   a valid C-alpha correspondence; unexpected mismatches are reported and excluded
   by default unless a reviewed profile explicitly permits them.
4. Use one selected model/chain/operator and C-alpha atoms only. Exclude missing
   coordinates, waters, ligands and unsupported modified residues, recording each
   reason. For alternate locations use the highest occupancy; ties choose blank,
   then lexicographic alternate ID. Exclude nonfinite coordinates and report the
   invalid input; do not feed NaN into a metric. Do not average NMR models.
5. Require at least three noncollinear matched fit points. Check rank with a
   documented numerical tolerance; insufficient/degenerate sets fail explicitly.

### Alignment and metrics

Use a proper rigid least-squares rotation and translation (no reflection, no
scaling), following [Kabsch](https://doi.org/10.1107/S0567739476001873). Store float64
rotation `R` and translation `t` in angstroms, with the exact column-vector
convention `aligned_variant = R * variant + t` in the reference coordinate frame;
`det(R)=+1`. Preserve original coordinates. Any assembly operation applied before
the fit must be recorded separately and composed in a declared order.

For evaluation pairs `(x_i, y_i)`, report:

```text
d_i = ||x_i - (R*y_i + t)||       [angstrom]
RMSD = sqrt(sum(d_i^2) / N)      [angstrom]
```

Default fit/evaluation sets are the same intersection of eligible mapped C-alpha
atoms, including the mutation site if available; no outlier trimming. If a user
chooses separate fit/evaluation ranges, persist both exact sets and label the
result accordingly. A local window of reference positions `p-5` through `p+5`
(clipped to bounds) may report displacement after the global fit, with counts and
missing positions; it is not a separately refitted local RMSD unless explicitly
requested under another method profile.

Report coverage as paired coordinate-present reference positions divided by the
full reference length, plus paired/eligible/selected counts for each chain and
evaluation range. Report sequence identity on aligned residue pairs excluding gaps,
with numerator and denominator; coverage and identity answer different questions.

Report raw unfiltered metrics first. An optional confidence-filtered metric names
the metric/scale, threshold, side(s) filtered and resulting atom counts. If both
structures have comparable confidence, apply the declared policy to both; an
experimental structure is not assigned synthetic confidence. Missing confidence
is excluded from that filtered calculation with a reason, not interpreted as zero.
Do not silently replace raw RMSD with a more favorable filtered value.

## 6. Implementation milestones

1. **M1 — Policies/contracts:** pin correspondence, selection, units, transform
   convention, scoring/tie policy, errors and result schema with NF-08.
2. **M2 — Analytic engine:** implement adapter parsing/mapping, proper fitting,
   metrics/coverage, tolerances and immutable synthetic test results.
3. **M3 — Service/API:** compatibility validation, bounded execution, storage,
   manifests and route contracts using fake inference artifacts.
4. **M4 — Interpretation/UI:** integrate NF-05 overlays/NF-07 tables, raw/filtered
   confidence reporting and matched-protocol warnings; review public real examples.

## 7. Acceptance criteria

- Identical synthetic structures and known rigid transforms recover near-zero
  RMSD within justified tolerance; the stored transform reproduces the result.
- A known nonrigid perturbation produces the expected analytic displacement;
  mirrored inputs are not fitted by reflection to an artificial zero.
- The report identifies every included pair and excluded/missing residue, mapping
  coverage, exact metric definition and both selection sets.
- Reference/variant mismatch, repeated-domain ambiguity, missing mutation sites,
  unsupported atom sets and degenerate fits yield tested errors or unavailable
  local metrics with reasons, never invented coordinates.
- Experimental/predicted/synthetic origins and protocol differences remain visible
  in UI and export. Raw artifacts remain unchanged by fitting.

## 8. Automated testing requirements

Use tiny synthetic coordinates with known translation/rotation, an independent
small analytic deformation, mirror images and near-degenerate sets. Test C-alpha
selection, alternate-location occupancy/ties, insertion codes, label/auth chain
differences, fragments, engineered mismatches, missing residues, repeated motifs,
different model IDs, assembly operators and nonfinite input rejection.

Assert RMSD denominators, coverage/identity fractions, fit-versus-evaluation
differences, transform orientation/composition, tolerance behavior and confidence
filter/missingness rules. Verify mutation mismatches remain mapped. API/storage
tests cover compatibility/errors, duplicate content identity, immutable outputs,
timeouts and manifests. NF-05/07 interaction tests confirm paired selection and
overlays use stored mapping/transforms. No weights, GPU, live PDB or research data.

## 9. Scientific validity and reproducibility

RMSD depends on correspondence, coordinate coverage, fitted atoms, conformational
state and length. A global fit can obscure local changes; local displacement after
that fit is not independent evidence of a mechanism. Experimental constructs,
conditions, missing residues and model uncertainty can dominate differences.

A reference/variant prediction pair is one computational comparison. Where
multiple samples/seeds exist, report their distributions and paired protocol,
not a significance claim derived from one pair. Confidence differences are not
calibrated mutation-effect probabilities. Discuss disordered regions and missing
partners. Predicted structural differences do not establish disease causality.

Record algorithm/library versions, scoring and numerical tolerances, all mappings,
coordinate units/conventions, filters, transforms and input hashes. Raw coordinates
are immutable; aligned views/reports are derived artifacts with their own hashes.

## 10. Risks and unresolved decisions

- **Numerical/parser dependency:** select/license-review a maintained optional
  adapter library before M2; define an SVD rank tolerance with synthetic and
  representative inputs rather than assuming every set fits reliably.
- **Mapping ties:** difficult constructs or repeated domains may be unsupported;
  later manual mapping needs a recorded review interface, not an implicit fallback.
- **Confidence thresholds:** science review must pin metric-specific filtering
  defaults before M4; unfiltered results always remain available.
- **Performance:** measure the bounded synchronous CPU path in M3; if inadequate,
  add explicit asynchronous comparison jobs before extending size limits.
- **Additional metrics:** TM-score/lDDT require separate definitions, normalization,
  reference choice, licensing and analytic validation. They are not aliases for
  existing model confidence fields.
