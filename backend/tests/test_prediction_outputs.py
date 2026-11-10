"""Authored byte/inventory/provenance checks; no prediction execution or parsing."""

from dataclasses import replace
from typing import Any

import pytest
from prediction_examples import ENDED, NA, Example, example, raw_hash, ref
from test_prediction_jobs import state_record

from neurofold.core.prediction_base import (
    PredictionError,
    SoftwareIdentity,
)
from neurofold.core.prediction_base import (
    PredictionErrorCode as E,
)
from neurofold.core.prediction_inputs import (
    CodeIdentity,
    ParameterValue,
    PredictionSpec,
)
from neurofold.core.prediction_outputs import (
    ConfidenceDescriptor,
    ModelProvenance,
    PredictionResult,
    SuccessfulPredictionProvenance,
    WeightIdentity,
    validate_completeness,
    validate_publication,
)
from neurofold.core.provenance import (
    EvidenceKind,
    HashEncoding,
    Metadata,
    MetadataState,
)


def publish(e: Example, **changes: Any) -> None:
    arguments: dict[str, Any] = dict(
        job=e.job,
        result=e.result,
        manifest=e.manifest,
        reference=e.reference,
        variant=None,
        profile=e.job.spec.profile,
        resolver=e.resolver,
        expected_version=e.job.version,
        attempt_id="attempt-1",
        fence=1,
        now=ENDED,
    )
    arguments.update(changes)
    validate_publication(**arguments)


def changed_manifest(e: Example, **changes: Any) -> Example:
    manifest = replace(e.manifest, **changes)
    return replace(
        e,
        manifest=manifest,
        result=replace(
            e.result, manifest=ref(manifest.manifest_id, manifest.content_hash)
        ),
    )


def test_complete_synthetic_publication_is_pure_and_cycle_free() -> None:
    e = example()
    before = (
        e.job.to_json(),
        e.result.to_json(),
        e.manifest.to_json(),
        dict(e.resolver.data),
    )
    validate_completeness(e.manifest)
    publish(e)
    assert before == (
        e.job.to_json(),
        e.result.to_json(),
        e.manifest.to_json(),
        dict(e.resolver.data),
    )
    assert (
        "result_id" in e.manifest.to_dict()
        and "result_hash" not in e.manifest.to_dict()
    )
    assert e.result.manifest.content_hash == e.manifest.content_hash
    assert e.result.manifest.content_hash.encoding is HashEncoding.CANONICAL_JSON
    assert e.manifest.source_receipt == e.reference.protein.source_receipt
    assert e.result.samples[0].confidence[0].scale_min == "0"


@pytest.mark.parametrize(
    "field",
    [
        "model",
        "environment",
        "execution",
        "preprocessing",
        "source_receipt",
        "samples",
        "artifacts",
        "spec",
        "raw_artifacts",
        "known_nondeterminism",
        "interpretation_limits",
        "returned_sample_ids",
    ],
)
def test_each_required_provenance_section_cannot_be_missing_or_generic(
    field: str,
) -> None:
    data = example().manifest.to_dict()
    data.pop(field)
    with pytest.raises(PredictionError):
        SuccessfulPredictionProvenance.from_dict(data)
    for invalid in (
        None,
        {},
        {"state": "unavailable", "value": None, "reason": "unknown"},
    ):
        with pytest.raises(PredictionError):
            SuccessfulPredictionProvenance.from_dict(
                example().manifest.to_dict() | {field: invalid}
            )


@pytest.mark.parametrize(
    "field",
    ["runtime", "operating_system", "hardware", "libraries", "dependency_locks"],
)
def test_required_environment_identity_cannot_be_absent(field: str) -> None:
    data = example().manifest.environment.to_dict() | {field: None}
    with pytest.raises(PredictionError):
        type(example().manifest.environment).from_dict(data)


@pytest.mark.parametrize("field", ["accelerator", "driver", "cuda"])
def test_synthetic_required_inapplicability_is_not_arbitrary_unavailability(
    field: str,
) -> None:
    e = example()
    environment = type(e.manifest.environment).from_dict(
        e.manifest.environment.to_dict()
        | {
            field: Metadata(
                state=MetadataState.UNAVAILABLE, value=None, reason="Not captured."
            ).to_dict()
        }
    )
    with pytest.raises(PredictionError) as error:
        validate_completeness(replace(e.manifest, environment=environment))
    assert error.value.code is E.INCOMPLETE_PROVENANCE


def predicted_example(*, accelerator: bool = False) -> Example:
    """A conditional contract proposal, never a configured real model profile/run."""
    e = example()
    profile = replace(
        e.job.spec.profile,
        evidence=EvidenceKind.PREDICTED,
        availability="available",
        availability_reason=None,
    )
    spec = replace(e.job.spec, profile=profile)
    job = replace(e.job, spec=spec, spec_hash=spec.content_hash)
    sample = e.result.samples[0]
    mapping = replace(sample.mapping, spec_hash=spec.content_hash)
    confidence = replace(
        sample.confidence[0], mapping=ref(mapping.mapping_id, mapping.content_hash)
    )
    sample = replace(
        sample,
        evidence=EvidenceKind.PREDICTED,
        mapping=mapping,
        confidence=(confidence,),
    )
    artifacts = tuple(
        replace(item, evidence=EvidenceKind.PREDICTED) for item in e.manifest.artifacts
    )
    e.resolver.descriptors.update({item.artifact_id: item for item in artifacts})
    lock = e.resolver.descriptors["lock-1"]
    weight_bytes = b"authored weight identity placeholder"
    weight = replace(
        lock,
        artifact_id="weight-1",
        content_hash=raw_hash(weight_bytes),
        byte_size=len(weight_bytes),
    )
    e.resolver.descriptors[weight.artifact_id] = weight
    e.resolver.data[weight.artifact_id] = weight_bytes
    model = ModelProvenance(
        model_state=MetadataState.PRESENT,
        weights_state=MetadataState.PRESENT,
        model=SoftwareIdentity(name="authored-real-proposal", version="unreviewed-1"),
        model_absence_reason=None,
        weights=(
            WeightIdentity(
                identity=SoftwareIdentity(name="authored-weights", version="1"),
                artifact=ref(weight.artifact_id, weight.content_hash),
                rights=weight.rights,
            ),
        ),
        weights_absence_reason=None,
    )
    present = Metadata(
        state=MetadataState.PRESENT,
        value="Authored conditional identity, not runtime observation.",
        reason=None,
    )
    environment = replace(
        e.manifest.environment,
        processor_kind="accelerator" if accelerator else "cpu",
        accelerator=present if accelerator else NA,
        driver=present if accelerator else NA,
        cuda=present if accelerator else NA,
    )
    manifest = replace(
        e.manifest,
        spec=spec,
        evidence=EvidenceKind.PREDICTED,
        model=model,
        environment=environment,
        samples=(sample,),
        artifacts=artifacts,
    )
    result = replace(
        e.result,
        spec_hash=spec.content_hash,
        evidence=EvidenceKind.PREDICTED,
        samples=(sample,),
        manifest=ref(manifest.manifest_id, manifest.content_hash),
    )
    return replace(e, job=job, result=result, manifest=manifest)


@pytest.mark.parametrize("accelerator", [False, True])
def test_real_conditional_completeness_uses_declared_weights_rights_and_runtime(
    accelerator: bool,
) -> None:
    e = predicted_example(accelerator=accelerator)
    validate_completeness(e.manifest)
    publish(e)
    with pytest.raises(PredictionError):
        validate_completeness(replace(e.manifest, model=example().manifest.model))
    with pytest.raises(PredictionError):
        validate_completeness(replace(e.manifest, evidence=EvidenceKind.EXPERIMENTAL))
    assert e.manifest.model.model is not None
    assert "boltz" not in e.manifest.model.model.name


@pytest.mark.parametrize("field", ["license", "attribution"])
def test_real_weights_need_independently_recorded_rights(field: str) -> None:
    e = predicted_example()
    weight = e.manifest.model.weights[0]
    rights = type(weight.rights).from_dict(
        weight.rights.to_dict()
        | {
            "redistribution": "unknown",
            field: Metadata(
                state=MetadataState.UNAVAILABLE, value=None, reason="Unreviewed."
            ).to_dict(),
        }
    )
    model = replace(e.manifest.model, weights=(replace(weight, rights=rights),))
    with pytest.raises(PredictionError) as error:
        validate_completeness(replace(e.manifest, model=model))
    assert error.value.code is E.INCOMPLETE_PROVENANCE


@pytest.mark.parametrize("field", ["accelerator", "driver", "cuda"])
@pytest.mark.parametrize(
    "state", [MetadataState.UNAVAILABLE, MetadataState.NOT_APPLICABLE]
)
def test_real_accelerator_runtime_cannot_be_unknown(
    field: str, state: MetadataState
) -> None:
    e = predicted_example(accelerator=True)
    environment = type(e.manifest.environment).from_dict(
        e.manifest.environment.to_dict()
        | {
            field: Metadata(
                state=state, value=None, reason="Missing required runtime identity."
            ).to_dict()
        }
    )
    with pytest.raises(PredictionError):
        validate_completeness(replace(e.manifest, environment=environment))


def test_synthetic_model_and_evidence_cannot_be_promoted() -> None:
    e = example()
    for manifest in (
        replace(e.manifest, model=predicted_example().manifest.model),
        replace(e.manifest, evidence=EvidenceKind.PREDICTED),
        replace(e.manifest, artifacts=predicted_example().manifest.artifacts),
        replace(
            e.manifest,
            preprocessing=replace(
                e.manifest.preprocessing,
                steps=("undisclosed transformation",),
                no_steps_reason=None,
            ),
        ),
    ):
        with pytest.raises(PredictionError):
            validate_completeness(manifest)


@pytest.mark.parametrize(
    "field,value",
    [
        ("returned_rank", 0),
        ("returned_rank", True),
        ("ranking_definition", " "),
        ("confidence", []),
        ("raw_artifacts", []),
        ("sample_id", "/private/path"),
    ],
)
def test_sample_invariants(field: str, value: object) -> None:
    sample = example().result.samples[0]
    with pytest.raises(PredictionError):
        type(sample).from_dict(sample.to_dict() | {field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("reason", "contradiction"),
        ("source_field", None),
        ("definition", None),
        ("units", None),
        ("scale_min", "1"),
        ("scale_min", "0.0"),
        ("scale_max", "NaN"),
        ("artifact", None),
        ("mapping", None),
    ],
)
def test_confidence_needs_explicit_definitions_scale_source_and_mapping(
    field: str, value: object
) -> None:
    confidence = example().result.samples[0].confidence[0]
    with pytest.raises(PredictionError):
        ConfidenceDescriptor.from_dict(confidence.to_dict() | {field: value})


@pytest.mark.parametrize(
    "state", [MetadataState.UNAVAILABLE, MetadataState.NOT_APPLICABLE]
)
def test_absent_confidence_is_explicit_not_zero(state: MetadataState) -> None:
    confidence = ConfidenceDescriptor(
        name="confidence",
        state=state,
        reason="No metric reported for this sample.",
        source_field=None,
        definition=None,
        units=None,
        scale_min=None,
        scale_max=None,
        scope="residue",
        artifact=None,
        mapping=None,
    )
    assert ConfidenceDescriptor.from_json(confidence.to_json()) == confidence
    sample = example().result.samples[0]
    assert replace(sample, confidence=(confidence,)).confidence[0].artifact is None
    with pytest.raises(PredictionError):
        replace(confidence, reason=None)
    with pytest.raises(PredictionError):
        replace(confidence, scale_min="0")


def test_mapping_numbering_and_sample_confidence_linkage() -> None:
    sample = example().result.samples[0]
    mapping = sample.mapping
    for change in (
        {"token_index": -1},
        {"token_index": True},
        {"input_position": 0},
        {"coordinate_residue_id": ""},
    ):
        with pytest.raises(PredictionError):
            type(mapping.rows[0]).from_dict(mapping.rows[0].to_dict() | change)
    for rows in (
        (),
        tuple(reversed(mapping.rows)),
        (mapping.rows[0],) * 5,
        (mapping.rows[0], replace(mapping.rows[1], token_index=0), *mapping.rows[2:]),
        (
            mapping.rows[0],
            replace(mapping.rows[1], coordinate_residue_id="1"),
            *mapping.rows[2:],
        ),
    ):
        with pytest.raises(PredictionError):
            replace(mapping, rows=rows)
    with pytest.raises(PredictionError):
        replace(sample, mapping=replace(mapping, sample_id="other"))
    with pytest.raises(PredictionError):
        replace(
            sample,
            confidence=(
                replace(
                    sample.confidence[0], mapping=ref("other-map", mapping.content_hash)
                ),
            ),
        )
    with pytest.raises(PredictionError):
        replace(sample, raw_artifacts=sample.raw_artifacts[:1])


def test_duplicate_samples_ranks_maps_and_conflicting_artifact_references() -> None:
    e = example()
    sample = e.result.samples[0]
    with pytest.raises(PredictionError):
        replace(e.result, samples=(sample, sample))
    other_map = replace(sample.mapping, mapping_id="map-2", sample_id="sample-2")
    other = replace(
        sample,
        sample_id="sample-2",
        mapping=other_map,
        confidence=(
            replace(
                sample.confidence[0],
                mapping=ref(other_map.mapping_id, other_map.content_hash),
            ),
        ),
    )
    with pytest.raises(PredictionError):
        replace(e.result, samples=(sample, other))
    with pytest.raises(PredictionError):
        replace(
            e.result,
            samples=(
                sample,
                replace(other, returned_rank=2, ranking_definition="Other ordering."),
            ),
        )
    with pytest.raises(PredictionError):
        replace(
            e.result, raw_artifacts=(*e.result.raw_artifacts, e.result.raw_artifacts[0])
        )
    with pytest.raises(PredictionError):
        replace(e.result, raw_artifacts=e.result.raw_artifacts[:1])
    with pytest.raises(PredictionError):
        replace(e.manifest, artifacts=e.manifest.artifacts * 2)


@pytest.mark.parametrize(
    "artifact_id",
    ["structure-1", "confidence-1", "lock-1", "synthetic-variant-reference-raw"],
)
@pytest.mark.parametrize("corruption", ["missing", "bytes", "size", "id", "hash"])
def test_missing_or_corrupt_artifacts_never_publish(
    artifact_id: str, corruption: str
) -> None:
    e = example()
    descriptor = e.resolver.descriptors[artifact_id]
    if corruption == "missing":
        del e.resolver.data[artifact_id]
    elif corruption == "bytes":
        e.resolver.data[artifact_id] += b"corruption"
    elif corruption == "size":
        e.resolver.descriptors[artifact_id] = replace(
            descriptor, byte_size=descriptor.byte_size + 1
        )
    elif corruption == "id":
        e.resolver.descriptors[artifact_id] = replace(descriptor, artifact_id="other")
    else:
        e.resolver.descriptors[artifact_id] = replace(
            descriptor, content_hash=raw_hash(b"other")
        )
    with pytest.raises(PredictionError) as error:
        publish(e)
    assert error.value.code is E.PUBLICATION_INTEGRITY
    assert error.value.details == {"stage": "artifacts"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("result_id", "other"),
        ("job_id", "other"),
        ("attempt_id", "other"),
        ("warnings", ("Unmatched warning.",)),
    ],
)
def test_result_manifest_links_must_agree(field: str, value: object) -> None:
    e = example()
    result = PredictionResult.from_dict(
        e.result.to_dict() | {field: list(value) if isinstance(value, tuple) else value}
    )
    with pytest.raises(PredictionError):
        publish(e, result=result)


def test_cross_record_inventory_completeness_and_state_precedence() -> None:
    e = example()
    cases = (
        changed_manifest(e, result_id="other"),
        changed_manifest(e, returned_sample_ids=("other",)),
        changed_manifest(e, raw_artifacts=e.manifest.raw_artifacts[:1]),
        changed_manifest(e, artifacts=e.manifest.artifacts[:1]),
        changed_manifest(
            e, source_receipt=replace(e.manifest.source_receipt, receipt_id="other")
        ),
        changed_manifest(
            e, execution=replace(e.manifest.execution, ended_at="2026-11-10T10:00:03Z")
        ),
    )
    for case in cases:
        with pytest.raises(PredictionError):
            publish(case)
    # Stale lifecycle wins over corrupt bytes and incomplete provenance.
    del e.resolver.data["structure-1"]
    with pytest.raises(PredictionError) as error:
        publish(e, job=state_record("cancelling"))
    assert error.value.code is E.ILLEGAL_TRANSITION
    with pytest.raises(PredictionError) as error:
        publish(e, expected_version=0)
    assert error.value.code is E.ILLEGAL_TRANSITION


def test_sample_count_mapping_length_output_limits_and_dirty_patch() -> None:
    e = example()
    spec = replace(e.job.spec, parameters=(ParameterValue(name="samples", value=2),))
    manifest = replace(e.manifest, spec=spec)
    # Rebuild dependent hashes to reach the sample-count check, not stale identities.
    mapping = replace(e.result.samples[0].mapping, spec_hash=spec.content_hash)
    sample = replace(
        e.result.samples[0],
        mapping=mapping,
        confidence=(
            replace(
                e.result.samples[0].confidence[0],
                mapping=ref(mapping.mapping_id, mapping.content_hash),
            ),
        ),
    )
    manifest = replace(manifest, samples=(sample,))
    case = replace(
        e,
        job=replace(e.job, spec=spec, spec_hash=spec.content_hash),
        manifest=manifest,
        result=replace(
            e.result,
            spec_hash=spec.content_hash,
            samples=(sample,),
            manifest=ref(manifest.manifest_id, manifest.content_hash),
        ),
    )
    with pytest.raises(PredictionError):
        publish(case)
    e = example()
    mapping = replace(
        e.result.samples[0].mapping, rows=e.result.samples[0].mapping.rows[:-1]
    )
    sample = replace(
        e.result.samples[0],
        mapping=mapping,
        confidence=(
            replace(
                e.result.samples[0].confidence[0],
                mapping=ref(mapping.mapping_id, mapping.content_hash),
            ),
        ),
    )
    case = changed_manifest(e, samples=(sample,))
    case = replace(case, result=replace(case.result, samples=(sample,)))
    with pytest.raises(PredictionError):
        publish(case)
    # Dirty source patch is explicitly registered, never a host path.
    patch = e.resolver.descriptors["lock-1"]
    code = CodeIdentity(
        revision="authored-source-v1",
        dirty=True,
        patch=ref(patch.artifact_id, patch.content_hash),
    )
    assert code.patch is not None


def test_real_weight_rights_must_match_the_resolved_artifact() -> None:
    e = predicted_example()
    weight = e.resolver.descriptors["weight-1"]
    e.resolver.descriptors["weight-1"] = replace(
        weight, rights=replace(weight.rights, basis="A conflicting rights declaration.")
    )
    with pytest.raises(PredictionError):
        publish(e)


def rebound_spec(e: Example, spec: PredictionSpec) -> Example:
    """Rebind test proposals consistently so failures reach their intended invariant."""
    sample = e.result.samples[0]
    mapping = replace(
        sample.mapping, spec_hash=spec.content_hash, sequence_hash=spec.sequence_hash
    )
    sample = replace(
        sample,
        mapping=mapping,
        confidence=(
            replace(
                sample.confidence[0],
                mapping=ref(mapping.mapping_id, mapping.content_hash),
            ),
        ),
    )
    manifest = replace(e.manifest, spec=spec, samples=(sample,))
    return replace(
        e,
        job=replace(e.job, spec=spec, spec_hash=spec.content_hash),
        manifest=manifest,
        result=replace(
            e.result,
            samples=(sample,),
            spec_hash=spec.content_hash,
            manifest=ref(manifest.manifest_id, manifest.content_hash),
        ),
    )


def test_declared_time_and_output_size_limits_at_publication() -> None:
    e = example()
    size = sum(item.byte_size for item in e.manifest.artifacts)
    for bound, passes in ((size, True), (size - 1, False)):
        profile = replace(
            e.job.spec.profile,
            limits=replace(e.job.spec.profile.limits, max_output_bytes=bound),
        )
        case = rebound_spec(e, replace(e.job.spec, profile=profile))
        if passes:
            publish(case)
        else:
            with pytest.raises(PredictionError) as error:
                publish(case)
            assert error.value.code is E.RESOURCE_LIMIT
    profile = replace(
        e.job.spec.profile, limits=replace(e.job.spec.profile.limits, max_seconds=1)
    )
    publish(rebound_spec(e, replace(e.job.spec, profile=profile)))
    case = changed_manifest(
        rebound_spec(e, replace(e.job.spec, profile=profile)),
        execution=replace(e.manifest.execution, ended_at="2026-11-10T10:00:03Z"),
    )
    with pytest.raises(PredictionError) as error:
        publish(case, now="2026-11-10T10:00:03Z")
    assert error.value.code is E.RESOURCE_LIMIT


def test_dirty_patch_requires_registered_bytes() -> None:
    e = example()
    patch_data = b"authored source patch"
    patch = replace(
        e.resolver.descriptors["lock-1"],
        artifact_id="patch-1",
        content_hash=raw_hash(patch_data),
        byte_size=len(patch_data),
    )
    spec = replace(
        e.job.spec,
        code=CodeIdentity(
            revision="authored-source-v1",
            dirty=True,
            patch=ref(patch.artifact_id, patch.content_hash),
        ),
    )
    case = rebound_spec(e, spec)
    with pytest.raises(PredictionError):
        publish(case)
    case.resolver.descriptors[patch.artifact_id] = patch
    case.resolver.data[patch.artifact_id] = patch_data
    publish(case)
    case.resolver.data[patch.artifact_id] += b"corrupt"
    with pytest.raises(PredictionError):
        publish(case)


def test_remote_auxiliary_requires_captured_exact_query_artifacts() -> None:
    from prediction_examples import SOFTWARE, STARTED

    from neurofold.core.prediction_inputs import AuxiliaryInput
    from neurofold.core.prediction_outputs import AuxiliaryProvenance

    e = example()
    requested = AuxiliaryInput(
        mode="remote",
        artifacts=(),
        reason="Declared future remote policy; no network execution here.",
        query_sequence_hash=None,
        transformation=None,
    )
    profile = replace(e.job.spec.profile, msa_modes=("none", "remote"))
    case = rebound_spec(e, replace(e.job.spec, profile=profile, msa=requested))
    with pytest.raises(PredictionError) as error:
        publish(case)
    assert error.value.code is E.INCOMPLETE_PROVENANCE
    captured_data = b"authored MSA query MACAG"
    descriptor = replace(
        e.resolver.descriptors["lock-1"],
        artifact_id="msa-1",
        content_hash=raw_hash(captured_data),
        byte_size=len(captured_data),
    )
    captured = AuxiliaryInput(
        mode="local",
        artifacts=(ref(descriptor.artifact_id, descriptor.content_hash),),
        reason=None,
        query_sequence_hash=case.job.spec.sequence_hash,
        transformation=None,
    )
    provenance = AuxiliaryProvenance(
        resolved=captured, provider=SOFTWARE, obtained_at=STARTED
    )
    case = changed_manifest(case, msa=provenance)
    case.resolver.descriptors[descriptor.artifact_id] = descriptor
    case.resolver.data[descriptor.artifact_id] = captured_data
    publish(case)
    for changed in (
        replace(provenance, provider=None, obtained_at=None),
        replace(provenance, obtained_at="2026-11-10T09:00:00Z"),
    ):
        with pytest.raises(PredictionError):
            publish(changed_manifest(case, msa=changed))
    with pytest.raises(PredictionError):
        AuxiliaryProvenance(resolved=requested, provider=None, obtained_at=None)


def test_every_returned_sample_can_be_published_including_identical_structures() -> (
    None
):
    e = example()
    spec = replace(e.job.spec, parameters=(ParameterValue(name="samples", value=2),))
    case = rebound_spec(e, spec)
    first = case.result.samples[0]
    mapping = replace(first.mapping, mapping_id="mapping-2", sample_id="sample-2")
    second = replace(
        first,
        sample_id="sample-2",
        returned_rank=2,
        mapping=mapping,
        confidence=(
            replace(
                first.confidence[0],
                mapping=ref(mapping.mapping_id, mapping.content_hash),
            ),
        ),
    )
    samples = (first, second)
    case = changed_manifest(
        case, samples=samples, returned_sample_ids=("sample-1", "sample-2")
    )
    case = replace(case, result=replace(case.result, samples=samples))
    publish(case)
    assert case.result.samples[0].structure == case.result.samples[1].structure
    # Equal coordinate bytes are allowed; separate sample identity/order is retained.
    with pytest.raises(PredictionError):
        publish(changed_manifest(case, returned_sample_ids=("sample-1",)))


def test_unavailable_profiles_and_wrong_hash_domains_cannot_publish() -> None:
    e = example()
    unavailable = replace(
        e.job.spec.profile,
        availability="unavailable",
        availability_reason="No runtime configured.",
    )
    with pytest.raises(PredictionError) as error:
        publish(rebound_spec(e, replace(e.job.spec, profile=unavailable)))
    assert error.value.code is E.INCOMPLETE_PROVENANCE
    for target, field in (
        (e.result, "spec_hash"),
        (e.result.samples[0].mapping, "sequence_hash"),
    ):
        data = target.to_dict()
        data[field] = raw_hash(b"wrong-domain").to_dict()
        with pytest.raises(PredictionError):
            type(target).from_dict(data)
    with pytest.raises(PredictionError):
        replace(e.result, manifest=ref("manifest-1", raw_hash(b"wrong-domain")))


def test_declared_artifact_lineage_is_closed_and_acyclic() -> None:
    e = example()
    original = e.manifest.artifacts
    present = Metadata(
        state=MetadataState.PRESENT,
        value="Authored derivative method/version; no molecular transformation.",
        reason=None,
    )
    derived = replace(
        original[0], parents=(e.job.spec.sequence_hash,), transformation=present
    )
    case = changed_manifest(e, artifacts=(derived, original[1]))
    case.resolver.descriptors[derived.artifact_id] = derived
    publish(case)
    missing = replace(derived, parents=(raw_hash(b"missing parent"),))
    case = changed_manifest(e, artifacts=(missing, original[1]))
    case.resolver.descriptors[missing.artifact_id] = missing
    with pytest.raises(PredictionError):
        publish(case)
    a = replace(
        original[0], parents=(original[1].content_hash,), transformation=present
    )
    b = replace(
        original[1], parents=(original[0].content_hash,), transformation=present
    )
    case = changed_manifest(e, artifacts=(a, b))
    case.resolver.descriptors.update({a.artifact_id: a, b.artifact_id: b})
    with pytest.raises(PredictionError):
        publish(case)


@pytest.mark.parametrize("field", ["model_state", "weights_state"])
def test_synthetic_model_absence_requires_not_applicable(field: str) -> None:
    e = example()
    model = type(e.manifest.model).from_dict(
        e.manifest.model.to_dict() | {field: "unavailable"}
    )
    with pytest.raises(PredictionError) as error:
        validate_completeness(replace(e.manifest, model=model))
    assert error.value.code is E.INCOMPLETE_PROVENANCE
