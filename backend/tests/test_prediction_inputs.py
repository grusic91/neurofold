"""Strict authored input/capability contracts, exact NF-02/03 linkage and identities."""

import hashlib
import inspect
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest
from prediction_examples import absence, example, raw_hash, ref, spec_for
from test_variants import snapshot

from neurofold.core.canonical import MAX_SAFE_INTEGER, CanonicalObject
from neurofold.core.prediction import (
    PredictionAdapter,
    PredictionRequest,
    PredictionSpec,
)
from neurofold.core.prediction_base import PredictionError
from neurofold.core.prediction_base import PredictionErrorCode as E
from neurofold.core.prediction_inputs import (
    AdapterCapability,
    AuxiliaryInput,
    CodeIdentity,
    ParameterDefinition,
    ParameterRequirement,
    ParameterValue,
    PredictionProfile,
    ResourceLimits,
    capabilities,
    resolve_parameters,
    synthetic_profile,
    validate_inputs,
)
from neurofold.core.provenance import ContentHash, HashEncoding, MetadataState
from neurofold.core.variants import define_variant, parse_substitution

FIXTURES = Path(__file__).parent / "fixtures"


def test_one_authoritative_request_and_synchronous_worker_seam() -> None:
    assert PredictionRequest is PredictionSpec
    signature = inspect.signature(PredictionAdapter.predict)
    assert list(signature.parameters) == ["self", "request", "output_dir"]
    assert signature.parameters["output_dir"].kind is inspect.Parameter.KEYWORD_ONLY
    assert not inspect.iscoroutinefunction(PredictionAdapter.predict)
    with pytest.raises(TypeError):
        PredictionRequest("MACAG", 0)  # type: ignore[call-arg, misc, arg-type]
    e = example()
    with pytest.raises(FrozenInstanceError):
        e.job.spec.seed = 3  # type: ignore[misc]
    assert b"path" not in e.result.to_json()


def test_resolved_defaults_and_independent_full_spec_golden() -> None:
    spec = spec_for()
    fixture: dict[str, Any] = json.loads((FIXTURES / "prediction-v1.json").read_bytes())
    expected_bytes = fixture["spec_canonical"].encode("utf-8")
    # Independent spelling and digest are frozen in the authored exchange fixture.
    assert spec.to_json() == expected_bytes
    assert spec.content_hash.sha256 == fixture["spec_sha256"]
    assert hashlib.sha256(expected_bytes).hexdigest() == fixture["spec_sha256"]
    assert spec.content_hash.encoding is HashEncoding.CANONICAL_JSON
    assert set(spec.to_dict()) == {
        "schema_version",
        "reference",
        "reference_sequence_hash",
        "variant",
        "sequence",
        "sequence_hash",
        "profile",
        "parameters",
        "seed",
        "msa",
        "templates",
        "constraints",
        "code",
        "transformations",
    }
    assert resolve_parameters(spec.profile, {}) == resolve_parameters(
        spec.profile, {"samples": 1}
    )
    assert (
        replace(
            spec, parameters=resolve_parameters(spec.profile, {"samples": 1})
        ).content_hash
        == spec.content_hash
    )
    assert replace(spec, seed=1).content_hash != spec.content_hash
    assert (
        replace(
            spec, transformations=("Recorded identity transformation.",)
        ).content_hash
        != spec.content_hash
    )
    assert (
        replace(
            spec, code=CodeIdentity(revision="other-v1", dirty=False, patch=None)
        ).content_hash
        != spec.content_hash
    )


@pytest.mark.parametrize(
    "bad", [None, [], (), True, CanonicalObject.from_value({}), "samples"]
)
def test_parameter_container_cannot_bypass_profile(bad: object) -> None:
    with pytest.raises(PredictionError) as error:
        resolve_parameters(synthetic_profile(), bad)
    assert error.value.code is E.INVALID_REPRESENTATION


@pytest.mark.parametrize(
    "bad", [True, False, "1", 0, 3, 1.0, None, [], {}, MAX_SAFE_INTEGER + 1]
)
def test_parameter_exact_types_and_bounds(bad: object) -> None:
    with pytest.raises(PredictionError) as error:
        resolve_parameters(synthetic_profile(), {"samples": bad})
    assert error.value.code is E.UNSUPPORTED_PARAMETER


def extended_profile() -> PredictionProfile:
    p = synthetic_profile()
    return replace(
        p,
        parameters=(
            ParameterDefinition(
                name="enabled",
                kind="boolean",
                default=False,
                minimum=None,
                maximum=None,
                choices=(),
            ),
            ParameterDefinition(
                name="mode",
                kind="choice",
                default="plain",
                minimum=None,
                maximum=None,
                choices=("plain", "special"),
            ),
            *p.parameters,
        ),
        requirements=(
            ParameterRequirement(
                when=ParameterValue(name="mode", value="special"),
                requires=ParameterValue(name="enabled", value=True),
            ),
        ),
    )


def test_compatibility_validation_and_deterministic_precedence() -> None:
    p = extended_profile()
    assert [
        v.value for v in resolve_parameters(p, {"mode": "special", "enabled": True})
    ] == [True, "special", 1]
    for supplied in (
        {"mode": "special"},
        {"enabled": 1},
        {"mode": "unknown"},
        {"samples": True, "unrecognized": 1},
        {1: 1},
    ):
        with pytest.raises(PredictionError) as error:
            resolve_parameters(p, supplied)
        assert error.value.code is E.UNSUPPORTED_PARAMETER
        assert error.value.details == {"stage": "parameters"}
    with pytest.raises(PredictionError):
        replace(p, parameters=tuple(reversed(p.parameters)))
    with pytest.raises(PredictionError):
        replace(
            p,
            requirements=(
                ParameterRequirement(
                    when=ParameterValue(name="missing", value=True),
                    requires=ParameterValue(name="enabled", value=True),
                ),
            ),
        )
    with pytest.raises(PredictionError):
        replace(
            p,
            parameters=(
                replace(p.parameters[0], default=True),
                replace(p.parameters[1], default="special"),
                *p.parameters[2:],
            ),
            requirements=(
                ParameterRequirement(
                    when=ParameterValue(name="mode", value="special"),
                    requires=ParameterValue(name="enabled", value=False),
                ),
            ),
        )


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "integer", "minimum": None},
        {"maximum": 0},
        {"choices": ("bad",)},
        {"default": True},
        {"name": "../../secret"},
        {"minimum": -MAX_SAFE_INTEGER - 1},
    ],
)
def test_invalid_parameter_declarations(change: dict[str, object]) -> None:
    data = synthetic_profile().parameters[0].to_dict() | change
    with pytest.raises(PredictionError):
        ParameterDefinition.from_dict(data)


@pytest.mark.parametrize("seed", [0, 2**32 - 1])
def test_seed_inclusive_boundaries(seed: int) -> None:
    assert replace(spec_for(), seed=seed).seed == seed


@pytest.mark.parametrize("seed", [-1, 2**32, True, 1.0, "0", MAX_SAFE_INTEGER + 1])
def test_invalid_seed(seed: object) -> None:
    with pytest.raises(PredictionError):
        PredictionSpec.from_dict(spec_for().to_dict() | {"seed": seed})


@pytest.mark.parametrize("sequence", ["A", "A" * 32])
def test_sequence_limit_boundaries(sequence: str) -> None:
    spec = spec_for(snapshot(sequence))
    validate_inputs(
        spec, reference=snapshot(sequence), variant=None, profile=spec.profile
    )


@pytest.mark.parametrize(
    "sequence, code",
    [
        ("A" * 33, E.RESOURCE_LIMIT),
        ("MAXAG", E.UNSUPPORTED_CAPABILITY),
        ("MA*AG", E.UNSUPPORTED_CAPABILITY),
    ],
)
def test_sequence_limit_and_alphabet(sequence: str, code: E) -> None:
    with pytest.raises(PredictionError) as error:
        spec_for(snapshot(sequence))
    assert error.value.code is code


def test_exact_reference_variant_linkage_no_substitution_reimplementation() -> None:
    reference = snapshot()
    variant = define_variant(reference, parse_substitution("A4V"))
    spec = replace(
        spec_for(reference),
        variant=ref(
            variant.variant_id,
            ContentHash(
                sha256=hashlib.sha256(variant.to_json()).hexdigest(),
                encoding=HashEncoding.CANONICAL_JSON,
            ),
        ),
        sequence=variant.sequence,
        sequence_hash=variant.sequence_hash,
    )
    validate_inputs(spec, reference=reference, variant=variant, profile=spec.profile)
    assert spec.sequence == "MACVG"
    assert (
        spec.sequence_hash.sha256
        == "938b2b382d01f18f15d8d909f926f1b02c94bd5ad7527a057a91733787060315"
    )
    assert (
        spec.reference_sequence_hash.sha256
        == "c88582ee0f845de56779787b8447097ae3330a816d1656b2808e0d439206226e"
    )
    assert spec.variant is not None
    for candidate, supplied_reference, supplied_variant in (
        (spec, snapshot("MACAA"), variant),
        (spec, reference, None),
        (spec_for(reference), reference, variant),
        (
            replace(
                spec,
                sequence=reference.protein.sequence,
                sequence_hash=reference.protein.sequence_hash,
            ),
            reference,
            variant,
        ),
        (spec, reference, replace(variant, reference_accession="OTHER")),
        (
            replace(spec, variant=ref("other-variant", spec.variant.content_hash)),
            reference,
            variant,
        ),
    ):
        with pytest.raises(PredictionError) as error:
            validate_inputs(
                candidate,
                reference=supplied_reference,
                variant=supplied_variant,
                profile=spec.profile,
            )
        assert error.value.code is E.INCONSISTENT_INPUT
    with pytest.raises(PredictionError) as error:
        validate_inputs(
            spec,
            reference=reference,
            variant=variant,
            profile=replace(spec.profile, seed_max=100),
        )
    assert error.value.code is E.UNSUPPORTED_CAPABILITY
    with pytest.raises(PredictionError):
        replace(spec, sequence_hash=spec.reference_sequence_hash)


def test_auxiliary_modes_query_hashes_and_explicit_absence() -> None:
    s = spec_for()
    local = AuxiliaryInput(
        mode="local",
        artifacts=(ref("msa-1", raw_hash(b"msa")),),
        reason=None,
        query_sequence_hash=s.sequence_hash,
        transformation="Recorded query-row identity; no substitution.",
    )
    profile = replace(s.profile, msa_modes=("none", "local", "remote"))
    assert replace(s, profile=profile, msa=local).msa == local
    with pytest.raises(PredictionError) as error:
        replace(s, msa=local)
    assert error.value.code is E.UNSUPPORTED_CAPABILITY
    with pytest.raises(PredictionError) as error:
        replace(
            s,
            profile=profile,
            msa=replace(
                local, query_sequence_hash=snapshot("AAA").protein.sequence_hash
            ),
        )
    assert error.value.code is E.INCONSISTENT_INPUT
    remote = AuxiliaryInput(
        mode="remote",
        artifacts=(),
        reason="Future declared remote policy only.",
        query_sequence_hash=None,
        transformation=None,
    )
    assert replace(s, profile=profile, msa=remote).msa.mode == "remote"
    changes: tuple[dict[str, object], ...] = (
        {"artifacts": [local.artifacts[0].to_dict()]},
        {"reason": None},
        {"query_sequence_hash": s.sequence_hash.to_dict()},
        {"transformation": "unexpected"},
    )
    for change in changes:
        with pytest.raises(PredictionError):
            AuxiliaryInput.from_dict(absence().to_dict() | change)
    with pytest.raises(PredictionError):
        replace(local, artifacts=())
    with pytest.raises(PredictionError):
        replace(local, artifacts=local.artifacts * 2)
    with pytest.raises(PredictionError):
        replace(local, reason="contradiction")
    patch = ref("patch-1", raw_hash(b"patch"))
    assert CodeIdentity(revision="r1", dirty=True, patch=patch).patch == patch
    with pytest.raises(PredictionError):
        CodeIdentity(revision="r1", dirty=False, patch=patch)


def test_capabilities_are_declarative_and_real_target_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    original = builtins.__import__

    def guarded(name: str, *args: Any, **kwargs: Any) -> Any:
        assert name.split(".")[0] not in {
            "torch",
            "boltz",
            "jax",
            "numpy",
            "httpx",
            "subprocess",
            "socket",
        }
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    synthetic, boltz = capabilities()
    assert synthetic.availability == "contract_only"
    assert boltz.availability == "unavailable" and boltz.profiles == ()
    assert boltz.adapter_version.state is MetadataState.UNAVAILABLE
    assert AdapterCapability.from_json(boltz.to_json()) == boltz
    assert (
        replace(
            synthetic.profiles[0], availability="available", availability_reason=None
        ).availability
        == "available"
    )
    with pytest.raises(PredictionError):
        replace(synthetic, availability="available", reason=None)
    with pytest.raises(PredictionError):
        replace(boltz, availability="available", reason=None)
    with pytest.raises(PredictionError):
        replace(boltz, reason=" ")
    with pytest.raises(PredictionError):
        replace(synthetic.profiles[0], availability="available")


@pytest.mark.parametrize(
    "field",
    [
        "min_residues",
        "max_residues",
        "max_samples",
        "max_seconds",
        "max_memory_bytes",
        "max_output_bytes",
    ],
)
def test_resource_limits_strict_and_positive(field: str) -> None:
    for bad in (0, -1, True, "1", MAX_SAFE_INTEGER + 1):
        with pytest.raises(PredictionError):
            ResourceLimits.from_dict(
                synthetic_profile().limits.to_dict() | {field: bad}
            )


@pytest.mark.parametrize(
    "change",
    [
        {"alphabet": "AA"},
        {"alphabet": "X"},
        {"seed_min": -1},
        {"seed_max": MAX_SAFE_INTEGER + 1},
        {"msa_modes": []},
        {"molecule_types": []},
        {"parameters": []},
    ],
)
def test_invalid_profiles(change: dict[str, object]) -> None:
    with pytest.raises(PredictionError):
        PredictionProfile.from_dict(synthetic_profile().to_dict() | change)


def test_profile_parameters_cannot_be_omitted_unresolved_or_reordered() -> None:
    s = spec_for()
    for values in (
        [],
        [ParameterValue(name="unknown", value=1).to_dict()],
        [s.parameters[0].to_dict()] * 2,
    ):
        with pytest.raises(PredictionError):
            PredictionSpec.from_dict(s.to_dict() | {"parameters": values})


@pytest.mark.parametrize(
    "data",
    [
        b'{"sequence":"SECRET", "sequence":"secret"}',
        b"{}",
        b"[]",
        b"\xff",
        b'{"x":NaN}',
        b'{"x":1.0}',
        b'{"x":9007199254740992}',
    ],
)
def test_bad_wire_errors_are_safe_and_never_message_classified(data: bytes) -> None:
    with pytest.raises(PredictionError) as error:
        PredictionSpec.from_json(data)
    assert str(error.value) == "INVALID_REPRESENTATION"
    assert error.value.details == {"stage": "representation"}
    assert "SECRET" not in str(error.value)
    copy = error.value.details
    copy["secret"] = "/private/path"
    assert error.value.details == {"stage": "representation"}
    with pytest.raises(PredictionError):
        PredictionSpec.from_json("{}")  # type: ignore[arg-type]


def test_identity_document_from_independently_spelled_fields() -> None:
    """The expected document is authored from the guide, without record serializers."""
    version = "neurofold-prediction/1"
    sequence_hash = {
        "algorithm": "sha256",
        "encoding": "sequence-ascii/1",
        "sha256": "c88582ee0f845de56779787b8447097ae3330a816d1656b2808e0d439206226e",
    }
    none: dict[str, object] = {
        "schema_version": version,
        "mode": "none",
        "artifacts": [],
        "query_sequence_hash": None,
        "transformation": None,
        "reason": "Authored synthetic input without auxiliary data.",
    }
    expected = {
        "schema_version": version,
        "reference": {
            "record_id": "synthetic-variant-reference",
            "content_hash": {
                "algorithm": "sha256",
                "encoding": "neurofold-json/1",
                "sha256": (
                    "a36dc032d7baa24bf2d1a3a30f67491826fb4f702626b308df6d80c685a77bdb"
                ),
            },
        },
        "reference_sequence_hash": sequence_hash,
        "variant": None,
        "sequence": "MACAG",
        "sequence_hash": sequence_hash,
        "profile": {
            "schema_version": version,
            "adapter": {"name": "authored-synthetic", "version": "1"},
            "profile": {"name": "contract-monomer", "version": "1"},
            "evidence": "synthetic",
            "availability": "contract_only",
            "availability_reason": (
                "Authored contracts only; no executable adapter exists."
            ),
            "molecule_types": ["protein"],
            "alphabet": "ACDEFGHIKLMNPQRSTVWY",
            "parameters": [
                {
                    "schema_version": version,
                    "name": "samples",
                    "kind": "integer",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 2,
                    "choices": [],
                }
            ],
            "requirements": [],
            "seed_min": 0,
            "seed_max": 4294967295,
            "limits": {
                "schema_version": version,
                "min_residues": 1,
                "max_residues": 32,
                "max_samples": 2,
                "max_seconds": 10,
                "max_memory_bytes": 1048576,
                "max_output_bytes": 4096,
            },
            "msa_modes": ["none"],
            "template_modes": ["none"],
            "constraint_modes": ["none"],
        },
        "parameters": [{"schema_version": version, "name": "samples", "value": 1}],
        "seed": 0,
        "msa": none,
        "templates": none,
        "constraints": none,
        "code": {
            "schema_version": version,
            "revision": "authored-source-v1",
            "dirty": False,
            "patch": None,
        },
        "transformations": [],
    }
    spelled = json.dumps(
        expected, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    assert (
        hashlib.sha256(spelled).hexdigest()
        == "5eedf8b6a799e1350b343733265c13dabaa9f2d7d03af52189ab815701b1e8ce"
    )
    assert spec_for().to_json() == spelled
