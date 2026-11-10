# Validation evidence template

Copy for a milestone or release review. This document is a human review record,
not a `neurofold-research/1` manifest and not a successful prediction contract.
Leave required missing evidence explicitly `incomplete`, with reason/owner/next
action. Use NF-08 `present`/`unavailable`/`not_applicable` metadata and reasons
when referencing scientific records. Never substitute fabricated values or zero
for absence. Link real artifacts stored outside Git; do not paste research data.

## Identity and scope

- Evidence ID, date/time (UTC), author, operator and reviewer/roles:
- Requested milestone / gate: foundation, synthetic preview or real scientific MVP:
- Code revision **and working-tree diff identity** if uncommitted:
- API/frontend package versions, HTTP/OpenAPI and manifest schema versions:
- Canonicalization/input/comparison schema versions; unsupported versions:
- `backend/uv.lock` and `frontend/package-lock.json` exact raw SHA-256:
- CI run URLs/IDs and revision tested, or `unavailable` with reason (never imply a local run is CI):
- Host OS/architecture, Python/Node/npm/uv versions, test browser version:
- Container daemon availability, image IDs/digests/build platform, or explicit unavailable reason:
- Declared supported targets/profiles/browsers/topology; known exclusions:

## Software checks

| Check / environment | Command / evidence reference | Result and counts | Limitations / follow-up |
| --- | --- | --- | --- |
| Locked Python install | `uv sync --locked` | incomplete | |
| Backend lint/format/types | Required Ruff/mypy commands | incomplete | |
| Backend behavior/coverage | `uv run --locked pytest` | incomplete | |
| Locked frontend install | `npm ci` | incomplete | |
| Frontend lint/types/build | Required npm commands | incomplete | |
| Component behavior and guards | `npm run test` | incomplete | |
| Browser behavior and guards | `npm run test:browser` | incomplete | |
| Container configuration | `docker compose config --quiet` | incomplete | |
| Container builds/services/proxy | Infra smoke commands; image identities | incomplete | |
| Integrated synthetic preview/export | Future M3 evidence | incomplete | |

Include failures, skipped/unavailable checks, retry reasons and raw log references
with checksums where retained. State fixture inventory revision/hash and what
network guards cover. Record Python 3.12/3.13 CI separately from local execution.

## Scientific protocol and artifacts

- Predeclared protocol ID/revision/hash and domain review approval/date:
- Public panel inclusion/exclusion rationale, disorder/coverage case and limits:
- Input snapshot/receipt IDs, sequence/raw hashes, exact substitutions and versions:
- Model/adapter/profile/source revision; weights SHA-256/license/review basis:
- Independent source/model/weights/data/derivative licenses, citations and redistribution decisions:
- MSA/auxiliary artifacts and checksums, disclosure/opt-in receipt or reasoned absence:
- Fully resolved parameters, seeds/replicates/sample selection, preprocessing:
- Runtime image digest, locks, code revision, hardware/OS/GPU/driver/CUDA/libraries:
- Measured sequence/sample/time/memory limits and measurements:
- Ordered comparison inputs, mapping/atom pairs/fit/evaluation selections and coverage:
- Units, conventions/transforms, confidence definition/scale/threshold and missing-data policy:
- Numerical precision, predeclared tolerances/justification, observed variation/nondeterminism:
- Every attempt/status, raw artifact/manifest IDs and byte checksums, warnings and deviations:
- External artifact locations, access/retention instructions and checksum verification:
- Offline export verification, omission/license inventory and independent verifier evidence:
- Results, uncertainty, applicability and interpretation limits; no causal/clinical claim:

## Gate review

| Gate from NF-09 | Outcome | Evidence / rationale / unresolved owner and next action |
| --- | --- | --- |
| Foundation | incomplete | |
| Biological integration | incomplete | |
| Variants | incomplete | |
| Jobs | incomplete | |
| Visualization/workflow | incomplete | |
| Comparison | incomplete | |
| Reproducibility/export | incomplete | |
| Real scientific runtime | incomplete | |
| Documentation | incomplete | |
| Operational scope | incomplete | |

For each gate use `pass`, `fail`, `incomplete` or justified `not_applicable`.
Scope a foundation pass precisely; future required MVP gates remain incomplete.
Record reviewer name/role/date, comments/resolutions, deviations accepted or
rejected, residual risks, and final decision for the named scope. A real-runtime
gate cannot pass using synthetic results. No scientific approval is implied by
unfilled fields or passing code checks. Publication authorization is separate.
