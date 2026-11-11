# NF-04 M1 prediction contracts

Decision record, 2026-11-10. This guide defines the contracts before dependent
implementation. M1 supplies pure records/validation. [M2 orchestration](prediction-orchestration.md)
now supplies durable storage, supervision, publication and HTTP without inference.

## Authoritative interfaces and versions

`core/prediction.py` exports `PredictionRequest` (the same class as
`PredictionSpec`), `PredictionResult`, and the synchronous worker protocol
`PredictionAdapter.predict(request, *, output_dir) -> PredictionResult`.
NF-01's `(sequence, seed)` and path-only result constructors are deliberately
removed: they cannot identify sources, profiles or complete samples. There are
no existing executable callers. Callers must build a verified resolved spec and
return registered identities; no compatibility constructor invents provenance.
Worker staging paths exist only inside `output_dir`. Later workers must allocate
registered IDs before constructing results, retain staged bytes until verified
registration, and leave failed/partial staging outside successful records.

Capabilities, profiles, parameter definitions/values, limits, auxiliary inputs,
code identity and specs use `neurofold-prediction/1`. Jobs/attempts use
`neurofold-prediction-job/1`. Samples, mappings, confidence and results use
`neurofold-prediction-result/1`. Successful manifests and their typed sections use
`neurofold-prediction-provenance/1`; this is separate from the unchanged NF-08
`ProvenanceRecord` skeleton, which still cannot certify prediction success.
All fields, including defaults and explicit nulls, are required on the wire;
unknown fields/versions, coercion, floats, unsafe integers and duplicate keys fail.
Collections are immutable tuples; canonical JSON uses NF-08's exact encoding.

## Inputs, profiles and identities

A spec embeds its immutable profile, pinned reference ID/full-record canonical
hash and exact sequence hash, optional variant canonical reference, exact input
sequence/hash, resolved sorted parameter values, seed, three auxiliary modes,
code identity and ordered transformations. Profile identity includes adapter and
profile versions, alphabet, molecule type, parameters, compatibility requirements,
seed range and resource limits. Version labels must change when behavior changes.
The embedded profile prevents unchecked dictionaries from bypassing validation.
Validate against an independently supplied verified profile to prevent replacing
its declarations. Availability is declarative: available, unavailable or
contract_only, with reasons for the latter two. It performs no runtime probe.
An authored synthetic contract-only profile defines small test bounds; these are
not measured runtime capacities. Boltz-2 has no selected version, profiles,
reviewed weights or measured limits and is unavailable with an explicit reason.

Parameter types are integer, boolean or enumerated string. Integer ranges are
inclusive, bool is never an integer. Defaults are validated and resolved before
spec construction/hashing. Requirements are explicit parameter/value implications.
Unknown names precede value validation; names/values are checked in sorted order,
then compatibility, seed, alphabet, sequence/sample limits and input modes.
Modes are none, local or remote; local needs raw artifact references; none/remote
need an explicit reason and no artifacts. Remote describes a future policy, not
permission to execute network generation. Templates/constraints use the same
explicit typed envelope and independently declared supported modes.
Units are residues, samples, seconds and bytes. A spec's sample count is the
required integer `samples` parameter. Time/memory/output bounds constrain future
execution; M1 cannot enforce actual process usage. Exact sequence hashes are
independently recomputed without normalization. `validate_inputs` checks reference
ID, full hash and sequence hash first, then calls NF-03's `validate_reference` for
a supplied variant and compares its ID/hash and exact sequence. It never
reimplements substitution or trusts an ID alone.

The spec hash is SHA-256 of its entire canonical `to_json()`, domain
`neurofold-json/1`; no hidden prefix or ScientificInput envelope. It includes all
fields above and the schema version; excludes operational job/attempt IDs,
timestamps, idempotency keys and retries. Code revision/dirty state is explicit;
a dirty source requires a patch hash. Source receipt capture time is indirectly
pinned by the reference full-record hash, never substituted for input identity.
Reference and variant specs are independent. Inspect complete profile/parameters,
auxiliary inputs, transformations and environment when matching protocols.
A common seed guarantees neither GPU determinism nor causal isolation.

## Lifecycle and concurrency boundary

Jobs retain immutable specs/hashes and explicit nullable start/end, attempt,
failure and result/manifest references. States/edges are queued → running or
cancelled; running → cancelling, succeeded or failed; cancelling → cancelled or
failed. Terminal records never transition, including to themselves. A retry uses
a distinct new queued job with `retry_of_job_id`; it never rewrites an attempt.
Queued cancellation confirms no execution began. Running cancellation requires
confirmed termination before cancelled; worker loss may instead fail. Progress
is null when unknown, otherwise integer basis points (0–10000), never fabricated.

Transition proposals require expected job version and matching active attempt
ID/fencing token. Attempts retain worker ID, lease ID, positive fence, start,
heartbeat and lease expiry. Heartbeats must be monotonic; lease renewal retains
identity/fence/start. Expired/fenced attempts cannot succeed. No success from
cancelling. Success needs both result and manifest references. M1 checks proposals
against supplied current records/time only. M2 must compare version, state, lease
and fence atomically with its transactional success commit; pure tests establish
no database atomicity, worker termination or actual race winner.

## Samples, manifests and publication

Every sample has a unique ID, unique positive returned rank with a shared explicit
ranking definition, one structure artifact, a canonical predicted mapping, typed
confidence descriptors, raw artifacts, warnings and explicit absence reasons.
Mapping rows identify chain, zero-based token, complete-input 1-based residue and
coordinate numbering as text; they cover the exact input once. Coordinates are
Cartesian angstroms with explicit transformations. Predicted maps are distinct
from NF-02 experimental maps. Confidence needs source field, definition, decimal
scale/units, scope and map/artifact links, or a reasoned unavailable/inapplicable
state. Generic B-factors/magnitude never imply confidence; missing is not zero.
Ranking is producer ordering, not biological accuracy. Raw inventories must match
the supplied returned-sample inventory; later runtime inspection must establish
that the adapter did not hide emitted files or samples.

Result canonical hashes include its manifest reference. The manifest hashes its
whole canonical document but references the result by ID only, never result hash:
manifest → spec/job/attempt/samples/artifacts; result → manifest hash. There is no
self checksum or result/manifest checksum cycle. The manifest duplicates sample
and raw inventories for strict equality checks and preserves artifact descriptors.
All artifact references use raw hashes; spec/result/manifest/map references use
canonical hashes. No scientific contract carries local paths or public URLs.

Successful provenance requires exact spec/source linkage, execution ID/timing,
adapter/profile via spec, model identity/version, independent weights/rights,
code/dirty patch, dependency locks, software/runtime/OS/hardware identities,
accelerator/driver/CUDA/libraries, preprocessing, auxiliary inputs, complete
sample/artifact inventories, mappings, confidence, transformations, warnings,
known nondeterminism and interpretation limits. Typed sections cannot be replaced
by generic CanonicalObject payloads. Synthetic manifests require synthetic outputs,
explicit inapplicability of model/weights/accelerator/driver/CUDA and a synthetic
limitation. Real predicted manifests require identified model/version, at least
one raw-checksummed weight with identified license/attribution/decision basis,
and present accelerator/driver/CUDA details or justified CPU inapplicability.
Unavailable required metadata blocks publication; synthetic software/inputs and
lock/code/runtime identities remain mandatory. This records rights declarations;
it does not independently approve a license or authenticate runtime claims.

`validate_publication` checks representation, input/profile linkage, eligible
running job/current unexpired attempt/version/fence, manifest/result/spec/attempt
identity, timing, complete provenance, all samples/maps/confidence, inventory
closure, evidence and every supplied artifact byte/hash/size using a narrow
injected resolver. Resolver KeyError means missing artifact; arbitrary exceptions
are not classified by message. Error precedence follows that order. Errors have
stable typed codes, static messages and allowlisted stage details only; no source
sequence, path, subprocess output, credential or exception string is copied.
Metadata/byte validation proves consistency of supplied records only. It is not
molecular parsing, scientific validation, exhaustive runtime capture, GPU evidence,
actual publication or a transactional success commit. M2 must repeat final state
and fencing checks atomically. M3 implements synthetic execution; M4 pins and
reviews real runtime/licenses/limits; M5 integrates Boltz-2 and requires independent
scientific review before relevant prediction/comparison acceptance.

## Exchange and compatibility

Draft 2020-12 schemas accompany strict codecs and tiny authored synthetic fixtures.
Schemas check shapes/types/versions; strict codecs additionally reject float/bool
coercion and duplicate JSON keys. Cross-record hashes, exact sequence derivation,
parameter implications, lifecycle/time/fence consistency, conditional completeness
and actual byte integrity require core validation. NF-02/NF-03/NF-08 schemas,
identity documents, fixture bytes and archive semantics remain frozen.

## Public record and validator inventory

All listed dataclasses are frozen and keyword-only. Strict `to_dict`, `to_json`,
`from_dict` and `from_json` are available. `content_hash` hashes complete canonical
record bytes. The checked-in schemas enumerate every required field and exact type:
[input/capability](schemas/neurofold-prediction-1.schema.json),
[job](schemas/neurofold-prediction-job-1.schema.json),
[result](schemas/neurofold-prediction-result-1.schema.json),
[successful provenance](schemas/neurofold-prediction-provenance-1.schema.json).

| Public record | Required content / absence policy |
| --- | --- |
| `SoftwareIdentity` | Nonempty bounded name/version identifiers; nested value type, no standalone exchange version |
| `AdapterCapability`, `PredictionProfile` | Versioned declaration fields described above; no missing release/version is invented for Boltz-2 |
| `ParameterDefinition`, `ParameterValue`, `ParameterRequirement` | Name/kind/default/min/max/choices; exact resolved scalar; typed when/requires implication |
| `ResourceLimits` | Positive min/max residues, samples, seconds, memory bytes, output bytes |
| `AuxiliaryInput`, `CodeIdentity` | Exact mode/artifacts/query hash/transformation/reason; revision/dirty and registered raw patch reference or null |
| `PredictionSpec` / `PredictionRequest` | Entire scientific input document, profile and resolved parameters; only one class/codec |
| `PredictionAttempt`, `PredictionFailure`, `PredictionJob` | Lease/worker/fence/times; stable code/stage/retryability; complete immutable state snapshot |
| `PredictionResidue`, `PredictionMapping` | Input/coordinate numbering, map/sample/spec/structure identities, method/version, ordered rows, units/convention and transformations |
| `ConfidenceDescriptor`, `PredictionSample`, `PredictionResult` | Explicit metric/absence, all ranked samples, complete raw refs, warnings and canonical manifest ref |
| `WeightIdentity`, `ModelProvenance` | Explicit model/weight states, name/version or reason; every weight identity/raw hash and independent rights, or explicit no-weights reason |
| `EnvironmentProvenance`, `ExecutionProvenance` | Runtime/OS/hardware, CPU/accelerator, driver/CUDA, libraries/locks; job/complete attempt/start/end |
| `PreprocessingProvenance`, `AuxiliaryProvenance` | Software and ordered steps or no-steps reason; actual resolved input with provider/version/time when remote generation was requested |
| `SuccessfulPredictionProvenance` | Full spec, original source receipt, typed sections, all samples/returned IDs/raw refs/descriptors, warnings, nondeterminism and interpretation limits |

`resolve_parameters(profile, supplied)` accepts a plain mapping only at validation
entry, rejects unknown names/types/values and returns sorted typed values. Specs
cannot omit defaults. `validate_inputs(spec, reference=..., variant=..., profile=...)`
requires verified supplied dependencies and compares their exact retained contents.
Profile declarations are authoritative only when the caller has verified their
origin/version; embedding a profile does not authenticate its issuer.

`validate_transition(current, proposed, expected_version=..., attempt_id=...,
fence=..., now=...)`, `validate_heartbeat` and `validate_retry` are pure proposal
checks. A failure transition can monotonically fence its active attempt. Cancellation
requests remain recorded through later failure. `validate_success_eligibility`
checks only a running active unexpired attempt. `JobRepository` is a protocol for
M2 get/insert/transactional commit; it has no M1 implementation.

`validate_completeness(manifest)` requires every typed section; `validate_publication`
also receives the current job, result, verified reference/variant/profile, artifact
resolver, expected version/attempt/fence and explicit current UTC time. Spec/profile
validation precedes lifecycle, cross-record provenance, conditional completeness,
inventories and artifact bytes. Declared execution duration and total output sizes
are bounded; actual process time/memory enforcement remains M2. CPU executions mark
accelerator/driver/CUDA not applicable; accelerator profiles require these present.
No CUDA requirement is invented for a CPU run. Required text identities cannot use
an unavailable metadata envelope. Producers remain responsible for truthful text,
proper software/hardware detail and reviewed field definitions.

A requested remote mode is not complete provenance. `AuxiliaryProvenance` must
resolve it to captured local raw references with the exact input query hash,
provider identity/version and UTC capture time within the declared attempt. Local
and absent modes must exactly match the spec. All actual auxiliary bytes are
verified at publication. No network generation or provider is implemented here.
Future workers must also validate molecular/MSA syntax and query contents; M1
verifies the declared query identity and bytes, not their scientific semantics.

A synthetic contract-only profile can validate authored proposals. Real successful
proposals require an available supplied profile and all required model/weight/runtime
identities. This does not make any real profile available in the shipped capability
inventory. Unknown weight redistribution remains explicit and does not authorize
exports; identified weight licenses/attribution are mandatory. Later review must
establish permission and applicability independently.

Declared artifact lineage must close over supplied verified input/spec/map hashes
and resolved raw artifact inventories. Missing parent identities and cycles among
raw artifacts fail publication. This checks declared lineage; later capture must
establish that the declared transformations actually occurred.

Model and weight sections carry explicit present/unavailable/not_applicable states.
Synthetic completeness requires not_applicable with reasons; unavailable is not
a substitute. Real completeness requires present identities and weight inventory.


## M2 compatibility and operational envelopes

M1 scientific/job/result/provenance codec, schema, fixture and hash bytes remain
unchanged. The M1 `JobRepository` proposal interface is retained for compatibility;
production uses the narrower explicit `DurableJobs` operation protocol instead of
a general commit capable of bypassing publication. SQL and concrete process
launchers stay outside core and application services depend only on core seams.

Additive `neurofold-child-proposal/1` stages strict result/manifest/artifact-byte
proposals, and `neurofold-prediction-status/1` exposes `{schema_version, job,
operational_failure}`. This deliberate HTTP envelope preserves the M1 failure
enum: operational WORKER_LOST/TIMEOUT/SHUTDOWN/CHILD_FAILED/INVALID_OUTPUT/
PUBLICATION_FAILED/SUPERVISION_FAILED live in the nullable sidecar; the nested
unchanged M1 failure uses ILLEGAL_PREDICTION_TRANSITION/lifecycle. No existing
prediction HTTP consumer existed. Frozen biological/variant routes are unchanged.
See the orchestration guide for full schemas/statuses, sealing, resource bounds,
strict final transactions, filesystem registration and crash/restart policies.

The M2 independent-review hardening checkpoint adds the separately versioned,
immutable checksummed `neurofold-prediction-failure/1` extension bound to the terminal
job hash, attempt and time. New operational causes and explicit retry policy are
authoritative there; the unchanged M1 nested failure is a compatibility placeholder.
The status sidecar is verified against that extension. Historical failures are not
rewritten. Future exports must include the extension or explicitly state legacy
unavailability; the M1 placeholder alone is not a truthful operational cause. See
[compatibility decisions](prediction-orchestration.md#truthful-retained-operational-failures)
and [hardening evidence](testing/nf04-m2-hardening-evidence.md).
