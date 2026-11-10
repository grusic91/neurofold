# Scientific review protocol

This is a review procedure for future NF-09 M4/M5, not evidence that inference or
comparison exists. No target panel, model version, weights, hardware limits or
numerical tolerances are approved at M1. Record reviews with the
[evidence template](evidence-template.md); unresolved requirements stay incomplete.

## Release gates and current plan

The NF-02 operational probe is deployment/upstream compatibility evidence only.
Independent scientific validation remains **incomplete**. A domain reviewer and
run operator are **unassigned**; appoint and record them before the relevant gate.
No real prediction/comparison result may be accepted while its required gate is
incomplete. The implementing agent cannot supply independent scientific sign-off.

| Gate | Required review and acceptance evidence | Timing |
| --- | --- | --- |
| Biological foundation | Independent inspection of a predeclared public panel, canonical/isoform/taxon identities, source versions, experimental method/context, chain/model/copy selection, modifications/unknowns, insertion/gap/alternate-location handling and all mapping/coverage denominators. Include poorly covered/disordered cases and disagreement handling; retain an independently checked mapping/identity worksheet. | Before using imported structures/maps to accept real prediction or comparison results; revisit at NF-02 scientific release. |
| NF-04 real prediction | Reviewer accepts panel and protocol before execution; verify model/weights/licenses, complete successful provenance, measured hardware limits, replicates and nondeterminism. Review all attempted outputs and uncertainty. | Before real prediction acceptance or release. |
| NF-06 real comparison | Independently verify atom correspondences, declared fit/evaluation selections, transformations/units, analytic controls, numerical tolerances and coverage; assess applicability before interpreting differences. | Before real comparison acceptance or release. |
| NF-08/NF-09 scientific release | Independent offline export verification, complete attempted-target inventory, reviewed interpretation/limitations, resolved comments and named dated decisions for every applicable gate. | Before scientific release; reopen on relevant input/method/runtime/schema changes. |

For each gate, the operator assembles the protocol and immutable evidence, the
independent domain reviewer records `pass`, `fail` or `incomplete` with reasons,
and the release owner verifies that all required reviews are complete. Numerical
tolerances and panel selection remain to be justified and approved; this plan
does not invent thresholds or imply completed review. Pure NF-03 domain logic
may proceed, but downstream acceptance remains subject to these gates.

## Before any real run

Name a run operator and a domain reviewer, recording their roles, dates and any
overlap/conflicts. The reviewer must explicitly accept the panel, protocol and
interpretation before real scientific release; self-run software checks alone
cannot satisfy this gate. Resolve comments with linked evidence and re-review
changes to methods, input selection or numerical tolerances.

Predeclare a public canonical monomer panel with explicit reference/variant
pairs, accession/isoform/taxon and sequence/entry versions, immutable snapshot IDs,
sequence/raw hashes and exact substitutions. Include documented experimental
context and a disordered or poorly covered case. Justify inclusion/exclusion and
applicability limits; record every attempted target, not only favorable outputs.
Do not select targets or infer causal disease effects from appealing overlays.

Review each independent code/model/weight/data license and redistribution basis.
Pin model release/source revision, adapter/profile, weights/checksums, MSA and
auxiliary input artifacts, dependency locks and runtime image. Disclose outbound
MSA submission and obtain explicit opt-in before any network MSA generation;
prefer captured local inputs. No private sequences or patient data belong here.

Predeclare matched reference/variant protocols, seeds/sample counts/order,
preprocessing, sequence/sample/time/memory limits and failure policy. Measure
limits on the named Linux/NVIDIA host; do not guess capacity. Record hardware,
OS, GPU/driver/CUDA/library versions and known nondeterminism. Define replicate
strategy and within-protocol variation reporting. A fixed seed is not a claim of
identical GPU output.

For comparisons, predeclare ordered inputs, model/chain/assembly operators,
mapping/method/version, atom pairs, fit versus evaluation selections, coverage
denominators, alternate locations/insertion codes/gaps, units and coordinate
conventions. Define sample selection without post hoc cherry-picking. Report
unfiltered results; filtered confidence thresholds need declared metric/scale,
justification and separate results. Set tolerances from analytic fixtures and
reviewed numeric precision/replicates; never choose a threshold simply to pass.

## Execute and preserve

Capture provenance using NF-08 contracts and future task-owned complete schemas:
exact inputs/source receipts, normalization/transformation history, adapter/model/
weight identity, fully resolved parameters, locks/revision/runtime, timings,
attempts and raw artifacts with byte hashes. Preserve originals. NF-08 M1
`ProvenanceRecord` is a skeleton with no successful prediction status; it cannot
certify a future successful run without the NF-04 completeness contract.

Retain failed/interrupted attempts, absent confidence/mappings/metrics and all
warnings. Use `unavailable` or `not_applicable` with explicit reasons; missing
metrics are not zero. Synthetic artifacts remain `synthetic` throughout UI and
exports; they are never real predictions or experimental observations.
Interpretations/hypotheses remain separately labeled. Repeat/compare runs using
the predeclared tolerance and retain observed nondeterminism and deviations.

Keep real validation artifacts in ignored local storage, outside source control.
The evidence record holds immutable IDs, checksums, controlled locations and
access/retention instructions. Independently verify future exported bytes and
manifests without upstream services, including license-authorized inclusions and
explicit omission inventory. Do not commit runtime logs containing secrets.

## Review and gate decision

Review software correctness, scientific applicability and operational readiness
separately. Analytic tests validate a declared calculation; smoke runs validate
execution/provenance on named inputs. Neither proves general protein prediction
accuracy, stability, aggregation, pathogenicity, disease causation or clinical
utility. Assess disorder, incomplete experimental structures, assemblies,
mapping coverage and confidence limits before interpreting differences.

Record reviewer/date, protocol revision, evidence references/checksums, observed
results, deviations, uncertainty, comments/resolutions and each gate outcome.
Use `pass`, `fail`, `incomplete` or `not_applicable` with rationale; a required
unavailable gate is incomplete, not waived as not applicable. Unreviewed models,
missing provenance, unresolved licenses, unmeasured limits or absent domain
review block real scientific acceptance. A synthetic software preview may be
reviewed separately but must retain that label. Reopen affected gates after
input, model, weights, protocol, dependency, runtime or schema changes.

Release review authorizes no push, publication, deployment or PR. Those require
separate user authorization.


NF-04 M1 now supplies a separately versioned complete successful-provenance
contract and pure completeness/publication validators. The authored synthetic and
conditional real-proposal tests establish supplied-record/byte consistency only.
They do not establish runtime truth, molecular validity, model/weight rights
approval or independent scientific acceptance. All gates above remain required;
M2 transactional fencing, M3 synthetic execution and M4/M5 reviewed real runtime
evidence are separate from this contract checkpoint.
